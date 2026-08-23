"""The bridge between the web console and the interview backend.

    python -m interview_agent.bridge

Bound to 127.0.0.1 deliberately. Nothing here is authenticated, because
nothing outside this machine can reach it - same posture as Friday AI.
"""

from __future__ import annotations

import logging
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from interview_agent import profile as profile_mod
from interview_agent.config import settings

logger = logging.getLogger("interview_agent.bridge")

HOST = "127.0.0.1"
PORT = 7332

# Holds the most recently uploaded candidate profile for this process.
# No database: sessions are ephemeral, so this resets on every restart -
# same posture as Friday AI's in-memory Supervisor history.
_profile: profile_mod.CandidateProfile | None = None


def system_info() -> dict[str, Any]:
    """The real configuration, for the console to display instead of guessing."""
    return {
        "model": settings.model,
        "fresher": settings.fresher,
        "roles": settings.roles,
        "modes": settings.modes,
    }


app = FastAPI(title="Interview Agent bridge")
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

    return {"profile": _profile.to_dict()}


@app.get("/api/resume")
async def get_resume() -> dict:
    return {"profile": _profile.to_dict() if _profile else None}


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
