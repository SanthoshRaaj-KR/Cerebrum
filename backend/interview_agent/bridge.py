"""The bridge between the web console and the interview backend.

    python -m interview_agent.bridge

Binds to INTERVIEW_AGENT_HOST (127.0.0.1 by default, 0.0.0.0 in the
container so Docker can publish the port). Nothing here is authenticated -
it is a single-user local tool, and the container publishes only to
localhost.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pipecat.transports.smallwebrtc.request_handler import (
    SmallWebRTCRequest,
    SmallWebRTCRequestHandler,
)

from interview_agent import interviewer as interviewer_mod
from interview_agent import pipeline as pipeline_mod
from interview_agent import profile as profile_mod
from interview_agent import prompts, scorecard
from interview_agent.config import settings
from interview_agent.context import CandidateContext

logger = logging.getLogger("interview_agent.bridge")

HOST = os.environ.get("INTERVIEW_AGENT_HOST", "127.0.0.1")
PORT = int(os.environ.get("INTERVIEW_AGENT_PORT", "7332"))

# The one active interview for this process. No database: sessions are
# ephemeral and reset on restart. One at a time - this is a single-user
# tool, not a service.
_session: interviewer_mod.InterviewSession | None = None

# Tracks in-flight WebRTC peer connections by pc_id so a renegotiation
# reuses the existing connection instead of leaking a new one.
_webrtc_handler = SmallWebRTCRequestHandler()


def system_info() -> dict[str, Any]:
    """The real configuration, for the console to display instead of guessing."""
    return {
        "model": settings.model,
        "fresher": settings.fresher,
        "durationMinutes": settings.duration_minutes,
        "modes": [
            {"key": m.key, "name": m.name, "blurb": m.blurb, "dims": list(m.dims)}
            for m in (prompts.get(k) for k in settings.modes)
        ],
    }


def _session_state(session: interviewer_mod.InterviewSession) -> dict:
    """Everything the interview screen renders, in one payload. Turn.to_dict()
    only ever carries a question, an answer, and whether it was skipped -
    nothing evaluative reaches the candidate until the report, by
    construction, not just by convention."""
    return {
        "mode": {"key": session.mode.key, "name": session.mode.name},
        "role": session.candidate.role,
        "level": session.candidate.level,
        "finished": session.finished,
        "clock": session.clock.to_dict() if session.clock else None,
        "turns": [t.to_dict() for t in session.turns],
        "researchBrief": (
            {
                "grounded": session.brief.grounded,
                "competencies": [c.name for c in session.brief.competencies],
                "realQuestions": session.brief.real_questions,
                "sources": session.brief.sources,
            }
            if session.brief
            else None
        ),
    }


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # WorkerRunner needs a running event loop to construct, so it's built
    # here rather than at import time (see pipeline.get_runner()).
    runner_task = asyncio.create_task(pipeline_mod.get_runner().run(auto_end=False))

    yield

    await pipeline_mod.stop_current_session()
    await pipeline_mod.get_runner().cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await runner_task
    await _webrtc_handler.close()


app = FastAPI(title="Cerebrum bridge", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    # The web console runs on its own port; both are local.
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "system": system_info()}


@app.post("/api/resume/extract")
async def extract_resume(file: UploadFile) -> dict:
    """PDF in, plain text out, for the résumé box to prefill itself. The
    interview itself works from whatever text ends up in that box, so this
    is a convenience rather than a required step."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "please upload a PDF")
    try:
        text = profile_mod.extract_text(await file.read())
    except profile_mod.ResumeParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"text": text}


@app.post("/api/session/start")
async def start_session(body: dict) -> dict:
    global _session

    mode_key = str(body.get("mode", ""))
    candidate = CandidateContext(
        role=str(body.get("role", "")).strip(),
        level=str(body.get("level", "")).strip(),
        resume=str(body.get("resume", "")).strip(),
    )
    # Minutes overridable per session - the web console never sends this
    # (it always wants the configured 40), but tools/quality_check.py does,
    # so a scripted run doesn't have to wait out a real 40 minutes.
    minutes_raw = body.get("minutes")
    minutes = int(minutes_raw) if isinstance(minutes_raw, (int, float)) and minutes_raw else None

    try:
        session = interviewer_mod.InterviewSession(mode_key=mode_key, candidate=candidate)
    except prompts.UnknownMode as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        await session.start(duration_minutes=minutes)
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not start interview session")
        raise HTTPException(502, f"could not start interview: {exc}") from exc

    _session = session
    return _session_state(session)


@app.post("/api/session/answer")
async def submit_answer(body: dict) -> dict:
    if _session is None:
        raise HTTPException(400, "no active interview session - start one first")
    if _session.finished:
        raise HTTPException(400, "this interview has finished - see the report")

    skipped = bool(body.get("skipped", False))
    text = str(body.get("text", "")).strip()
    if not skipped and not text:
        raise HTTPException(400, "empty answer")

    try:
        await _session.answer(text, skipped=skipped)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not process the answer")
        raise HTTPException(502, f"could not process the answer: {exc}") from exc

    return _session_state(_session)


@app.get("/api/session")
async def get_session() -> dict:
    if _session is None:
        return {"session": None}
    return {"session": _session_state(_session)}


@app.post("/api/session/report")
async def session_report() -> dict:
    """The end-of-session scorecard. Marks the interview finished so no
    further answers are accepted, but leaves it readable. This is the
    first point anything evaluative reaches the candidate."""
    if _session is None:
        raise HTTPException(400, "no active interview session")

    _session.finished = True
    summary = await scorecard.build(_session)
    state = _session_state(_session)
    state["scorecard"] = summary.to_dict()
    return state


@app.post("/api/session/reset")
async def reset_session() -> dict:
    global _session
    _session = None
    await pipeline_mod.stop_current_session()
    return {"ok": True}


@app.post("/api/offer")
async def offer(body: dict) -> dict:
    """WebRTC signaling for the mic. The browser posts an SDP offer, this
    returns the answer, and the voice pipeline is built the moment the
    connection is created."""
    if _session is None:
        raise HTTPException(400, "start an interview before opening the mic")

    request = SmallWebRTCRequest.from_dict(body)
    session = _session

    async def _on_webrtc_connection(connection) -> None:
        await pipeline_mod.start_dictation(connection, session)

    try:
        answer = await _webrtc_handler.handle_web_request(request, _on_webrtc_connection)
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not open the microphone session")
        raise HTTPException(502, f"could not open the microphone: {exc}") from exc

    if answer is None:
        raise HTTPException(502, "no SDP answer produced")
    return answer


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S"
    )

    info = system_info()
    print(f"\n  Cerebrum bridge on http://{HOST}:{PORT}")
    print(f"  model  {info['model']}   fresher  {str(info['fresher']).lower()}")
    print(f"  modes  {', '.join(m['name'] for m in info['modes'])}")
    print(f"  {info['durationMinutes']} minutes per session\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
