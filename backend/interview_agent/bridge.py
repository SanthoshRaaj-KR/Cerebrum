"""The bridge between the web console and the interview backend.

    python -m interview_agent.bridge

Bound to 127.0.0.1 deliberately. Nothing here is authenticated, because
nothing outside this machine can reach it - same posture as Friday AI.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
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
from interview_agent.config import settings

logger = logging.getLogger("interview_agent.bridge")

HOST = "127.0.0.1"
PORT = 7332

# Holds the most recently uploaded candidate profile, and the active
# interview session, for this process. No database: both are ephemeral,
# reset on every restart - same posture as Friday AI's in-memory Supervisor
# history. One session at a time: this is a single-user local tool.
_profile: profile_mod.CandidateProfile | None = None
_session: interviewer_mod.InterviewSession | None = None

# One handler for the process: tracks in-flight WebRTC peer connections by
# pc_id so a renegotiation (ICE restart, reconnect) reuses the existing
# connection instead of leaking a new one. MULTIPLE mode (the default) is
# fine for a single-user local tool - it just means "don't reject a second
# connection", not "actually serve two people at once".
_webrtc_handler = SmallWebRTCRequestHandler()


def system_info() -> dict[str, Any]:
    """The real configuration, for the console to display instead of guessing."""
    return {
        "model": settings.model,
        "fresher": settings.fresher,
        "roles": settings.roles,
        "modes": settings.modes,
    }


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # WorkerRunner needs a running event loop to construct, so it's built
    # here rather than at import time (see pipeline.get_runner()).
    # auto_end=False: this is a long-lived host that adds a worker per voice
    # session, not a one-shot bot script that should exit when a session ends.
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
    # The Next dev server runs on a different port; both are local.
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "system": system_info()}


@app.post("/api/resume")
async def upload_resume(file: UploadFile) -> dict:
    global _profile

    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(400, "please upload a PDF")

    data = await file.read()
    try:
        _profile = await profile_mod.parse_resume(data)
    except profile_mod.ResumeParseError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("resume structuring failed")
        raise HTTPException(502, f"could not process resume: {exc}") from exc

    return {"profile": _profile.for_api()}


@app.get("/api/resume")
async def get_resume() -> dict:
    return {"profile": _profile.for_api() if _profile else None}


@app.post("/api/session/start")
async def start_session(body: dict) -> dict:
    """Starts (or restarts) the one active interview session with a fresh
    system prompt and empty history. Text-only for now - Phase 4 swaps this
    endpoint's role for a live voice pipeline without touching interviewer.py."""
    global _session

    role = str(body.get("role", ""))
    mode = str(body.get("mode", ""))
    try:
        _session = interviewer_mod.InterviewSession(role=role, mode=mode, profile=_profile)
    except interviewer_mod.UnknownRoleOrMode as exc:
        raise HTTPException(400, str(exc)) from exc

    try:
        question = await _session.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not start interview session")
        _session = None
        raise HTTPException(502, f"could not start interview: {exc}") from exc

    return {"question": question}


@app.post("/api/session/answer")
async def submit_answer(body: dict) -> dict:
    if _session is None:
        raise HTTPException(400, "no active interview session - call /api/session/start first")

    text = str(body.get("text", "")).strip()
    if not text:
        raise HTTPException(400, "empty answer")

    try:
        question = await _session.answer(text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("interview session failed to produce a next question")
        raise HTTPException(502, f"could not get next question: {exc}") from exc

    return {"question": question}


@app.post("/api/session/end")
async def end_session() -> dict:
    """Ends the text-harness session and returns a brief recap. Ephemeral,
    like everything else here - the summary is generated once, shown once,
    and gone the moment the process restarts."""
    global _session

    if _session is None:
        raise HTTPException(400, "no active interview session")

    try:
        summary = await _session.summarize()
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not summarize interview session")
        raise HTTPException(502, f"could not summarize interview: {exc}") from exc
    finally:
        _session = None

    return {"summary": summary}


@app.post("/api/offer")
async def offer(body: dict) -> dict:
    """WebRTC signaling endpoint: the browser posts an SDP offer (plus
    role/mode in request_data), this returns the SDP answer, and the actual
    voice pipeline (pipeline.start_voice_session) is built in the background
    the moment the connection is created - see _on_webrtc_connection below."""
    request = SmallWebRTCRequest.from_dict(body)

    role = mode = ""
    if isinstance(request.request_data, dict):
        role = str(request.request_data.get("role", ""))
        mode = str(request.request_data.get("mode", ""))
    if role not in settings.roles or mode not in settings.modes:
        raise HTTPException(400, f"unknown role/mode: {role!r}/{mode!r}")

    async def _on_webrtc_connection(connection) -> None:
        await pipeline_mod.start_voice_session(connection, role, mode, _profile)

    try:
        answer = await _webrtc_handler.handle_web_request(request, _on_webrtc_connection)
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not establish voice session")
        raise HTTPException(502, f"could not establish voice session: {exc}") from exc

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
    print(f"  roles  {', '.join(info['roles'])}")
    print(f"  modes  {', '.join(info['modes'])}")
    print("  Open the console with:  cd web && npm run dev\n")
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
