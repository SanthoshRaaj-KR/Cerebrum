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
from interview_agent import prompts, report
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
        "questionsPerSession": settings.questions_per_session,
        "modes": [
            {
                "key": m.key,
                "name": m.name,
                "blurb": m.blurb,
                "dims": list(m.dims),
                "count": settings.questions_per_session,
            }
            for m in (prompts.get(k) for k in settings.modes)
        ],
    }


def _session_state(session: interviewer_mod.InterviewSession) -> dict:
    """Everything the interview screen renders, in one payload."""
    return {
        "mode": {"key": session.mode.key, "name": session.mode.name, "dims": list(session.mode.dims)},
        "role": session.candidate.role,
        "level": session.candidate.level,
        "index": session.index,
        "total": session.total,
        "finished": session.finished,
        # The sidebar shows what was actually asked, not what was planned -
        # the interviewer deviates from the plan whenever it challenges a
        # claim or re-asks a dodged question, and a label that still read
        # "REST API design" next to a question about password storage would
        # be lying. The grader labels the question it just graded; unasked
        # slots fall back to the plan's own label.
        "plan": [
            {
                "num": i + 1,
                "short": (
                    (session.turns[i].grade.topic if session.turns[i].grade else "")
                    or session.turns[i].short
                    if i < len(session.turns)
                    else s.short
                ),
                "score": (
                    session.turns[i].grade.score
                    if i < len(session.turns) and session.turns[i].grade
                    else None
                ),
            }
            for i, s in enumerate(session.plan)
        ],
        "turns": [t.to_dict() for t in session.turns],
        "average": session.average(),
        "dimensionAverages": session.dimension_averages(),
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


app = FastAPI(title="Interview Agent bridge", lifespan=lifespan)
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

    try:
        session = interviewer_mod.InterviewSession(mode_key=mode_key, candidate=candidate)
    except prompts.UnknownMode as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        await session.start()
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
        logger.exception("could not grade the answer")
        raise HTTPException(502, f"could not grade the answer: {exc}") from exc

    return _session_state(_session)


@app.get("/api/session")
async def get_session() -> dict:
    if _session is None:
        return {"session": None}
    return {"session": _session_state(_session)}


@app.post("/api/session/report")
async def session_report() -> dict:
    """The end-of-session report. Marks the interview finished so no
    further answers are accepted, but leaves it readable."""
    if _session is None:
        raise HTTPException(400, "no active interview session")

    _session.finished = True
    summary = await report.build(_session)
    state = _session_state(_session)
    state["report"] = summary
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
    print(f"\n  Interview Agent bridge on http://{HOST}:{PORT}")
    print(f"  model  {info['model']}   fresher  {str(info['fresher']).lower()}")
    print(f"  modes  {', '.join(m['name'] for m in info['modes'])}")
    print(f"  {info['questionsPerSession']} questions per session\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
