"""PipeCat voice pipeline: mic in -> VAD -> Deepgram STT -> LLM context ->
Cerebras -> Cartesia TTS -> speaker out, over WebRTC.

Reuses interviewer.py's system-prompt composition unchanged - this is a new
transport/turn-taking layer in front of the same interview logic Phase 3
already verified over text. The pipeline holds its own turn history via
pipecat's LLMContext (fed by the STT/TTS turn-taking machinery instead of
interviewer.InterviewSession's manual history list), so the cross-questioning
instruction in BASE_INSTRUCTIONS works the same way it does in the text
harness: the model sees the whole conversation every turn.
"""

from __future__ import annotations

import logging

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame, LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.cerebras.llm import CerebrasLLMService
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from interview_agent import prompts
from interview_agent.config import settings
from interview_agent.interviewer import _EXPERIENCED_NOTE, _FRESHER_NOTE, BASE_INSTRUCTIONS
from interview_agent.profile import CandidateProfile

logger = logging.getLogger("interview_agent.pipeline")

# One runner for the whole process, built lazily. WorkerRunner() calls
# asyncio.get_running_loop() at construction time, so it can't be built at
# module import (no loop yet) - only from inside bridge.py's async lifespan,
# which is where get_runner() is first called.
_runner: WorkerRunner | None = None


def get_runner() -> WorkerRunner:
    global _runner
    if _runner is None:
        _runner = WorkerRunner()
    return _runner


# The worker for the session currently running, if any. One interview at a
# time: this is a single-user local tool, and starting a second one should
# stop the first rather than leave two pipelines holding live Deepgram and
# Cartesia websockets.
_current_worker: PipelineWorker | None = None


async def stop_current_session() -> None:
    global _current_worker
    if _current_worker is None:
        return
    worker, _current_worker = _current_worker, None
    try:
        await worker.cancel()
    except Exception:  # noqa: BLE001
        logger.exception("could not cancel the previous voice session")


def system_prompt(role: str, mode: str, profile: CandidateProfile | None) -> str:
    """Same composition as InterviewSession.system_prompt() (interviewer.py),
    kept here as a plain function since a voice session has no InterviewSession
    instance - pipecat's LLMContext holds the turn history instead."""
    return BASE_INSTRUCTIONS.format(
        fresher_note=_FRESHER_NOTE if settings.fresher else _EXPERIENCED_NOTE,
        role_prompt=prompts.role_prompt(role),
        mode_prompt=prompts.mode_prompt(mode, profile),
    )


async def start_voice_session(
    connection: SmallWebRTCConnection,
    role: str,
    mode: str,
    profile: CandidateProfile | None,
) -> None:
    """Builds one interview's voice pipeline against a live WebRTC connection
    and registers it with the process-wide runner. Returns once the worker is
    registered - the caller (bridge.py) doesn't wait for the interview to
    finish, only for the SDP answer the connection itself produces.
    """
    global _current_worker

    # Whatever was running is over the moment a new interview starts.
    await stop_current_session()

    stt = DeepgramSTTService(api_key=settings.deepgram_api_key)
    tts = CartesiaTTSService(
        api_key=settings.cartesia_api_key,
        voice_id=(settings.voice.get("tts", {}) or {}).get("voice_id") or None,
    )
    llm = CerebrasLLMService(
        api_key=settings.cerebras_api_key,
        settings=CerebrasLLMService.Settings(model=settings.model),
    )

    context = LLMContext(
        messages=[{"role": "system", "content": system_prompt(role, mode, profile)}]
    )
    aggregators = LLMContextAggregatorPair(context)

    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=True),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            VADProcessor(vad_analyzer=SileroVADAnalyzer()),
            stt,
            aggregators.user(),
            llm,
            tts,
            transport.output(),
            aggregators.assistant(),
        ]
    )

    worker = PipelineWorker(pipeline, params=PipelineParams())

    @transport.event_handler("on_client_connected")
    async def _on_connected(_transport, _client) -> None:
        # The system prompt is already in context; this kicks off the
        # interviewer's opening question without a fake user turn.
        logger.info("voice session connected: role=%s mode=%s", role, mode)
        await worker.queue_frame(LLMRunFrame())

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client) -> None:
        global _current_worker
        logger.info("voice session disconnected: role=%s mode=%s", role, mode)
        # EndFrame drains the pipeline cleanly; clearing the handle stops
        # stop_current_session() from later cancelling an already-finished
        # worker, and lets it be garbage collected.
        if _current_worker is worker:
            _current_worker = None
        await worker.queue_frame(EndFrame())

    _current_worker = worker
    await get_runner().add_workers(worker)
