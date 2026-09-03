"""Dictation for the answer box: mic in -> VAD -> Deepgram STT -> back to
the browser as transcript messages over the WebRTC data channel.

This used to be a full spoken interview - the model talked back through
TTS. Cerebrum's design made the interview typed and graded, so the
microphone's job shrank to one thing: let someone speak an answer instead
of typing it. No LLM and no TTS in this path; the transcript lands in the
textarea and the normal typed flow takes over from there.

Pipecat's RTVIProcessor (attached to every PipelineWorker by default)
already emits `user-transcription` messages over the data channel, which
is exactly what web/lib/webrtc.ts listens for - so nothing custom is
needed between STT and the browser.
"""

from __future__ import annotations

import logging

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transports.base_transport import TransportParams
from pipecat.transports.smallwebrtc.connection import SmallWebRTCConnection
from pipecat.transports.smallwebrtc.transport import SmallWebRTCTransport
from pipecat.workers.runner import WorkerRunner

from interview_agent.config import settings

logger = logging.getLogger("interview_agent.pipeline")

# One runner for the whole process, built lazily: WorkerRunner() calls
# asyncio.get_running_loop() at construction, so it cannot be a
# module-level singleton.
_runner: WorkerRunner | None = None


def get_runner() -> WorkerRunner:
    global _runner
    if _runner is None:
        _runner = WorkerRunner()
    return _runner


# The worker for the mic session currently open, if any. One at a time:
# opening a second would leave the first holding a live Deepgram socket.
_current_worker: PipelineWorker | None = None


async def stop_current_session() -> None:
    global _current_worker
    if _current_worker is None:
        return
    worker, _current_worker = _current_worker, None
    try:
        await worker.cancel()
    except Exception:  # noqa: BLE001
        logger.exception("could not close the previous microphone session")


async def start_dictation(connection: SmallWebRTCConnection, session=None) -> None:
    """Open the mic for the current interview. `session` is accepted so the
    caller can pass context later (per-mode vocabulary hints, say); the
    transcript itself is candidate-agnostic."""
    global _current_worker

    await stop_current_session()

    stt = DeepgramSTTService(api_key=settings.deepgram_api_key)

    transport = SmallWebRTCTransport(
        webrtc_connection=connection,
        # audio_out stays off - nothing is spoken back, so there is no
        # outbound audio stream to negotiate.
        params=TransportParams(audio_in_enabled=True, audio_out_enabled=False),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            VADProcessor(vad_analyzer=SileroVADAnalyzer()),
            stt,
            # transport.output() is required even with audio_out_enabled=False.
            # It is not only an audio sink: the RTVI processor reports
            # transcriptions by pushing OutputTransportMessageUrgentFrames
            # downstream, and the OUTPUT transport is the only thing that
            # turns those into data channel messages. Without it, audio still
            # flows in and Deepgram still transcribes, but every result is
            # dropped at the end of the pipeline and the browser hears
            # nothing back.
            transport.output(),
        ]
    )

    worker = PipelineWorker(pipeline, params=PipelineParams())

    @transport.event_handler("on_client_connected")
    async def _on_connected(_transport, _client) -> None:
        logger.info("microphone opened")

    @transport.event_handler("on_client_disconnected")
    async def _on_disconnected(_transport, _client) -> None:
        global _current_worker
        logger.info("microphone closed")
        if _current_worker is worker:
            _current_worker = None
        await worker.queue_frame(EndFrame())

    _current_worker = worker
    await get_runner().add_workers(worker)
