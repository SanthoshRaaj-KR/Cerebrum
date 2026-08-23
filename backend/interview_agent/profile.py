"""Resume/projects ingestion: PDF text extraction, then structuring via Cerebras.

The interviewer (Phase 3) reads a CandidateProfile, not raw resume text - the
structuring step here is what lets prompts reference "your project X" instead
of re-reading a wall of PDF text every turn.
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict, dataclass, field

from openai import AsyncOpenAI
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from interview_agent.config import settings

CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

# Resumes rarely run past a few hundred KB; this is a generous ceiling meant
# to reject something wrong (a video, a zip) rather than a real resume.
MAX_PDF_BYTES = 10 * 1024 * 1024

_STRUCTURE_PROMPT = """You turn raw resume/CV text into a structured candidate
profile for a technical mock-interview tool. Extract only what's actually in
the text - do not invent skills, projects, or experience that aren't stated
or clearly implied. If a section is absent, return an empty list for it.

For each project, "description" should be one or two sentences capturing
what it does and the candidate's role in it - enough for an interviewer to
ask a grounded follow-up question about it."""

_PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "education": {"type": "array", "items": {"type": "string"}},
        "skills": {"type": "array", "items": {"type": "string"}},
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "tech": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "description", "tech"],
                "additionalProperties": False,
            },
        },
        "experience": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "education", "skills", "projects", "experience"],
    "additionalProperties": False,
}


class ResumeParseError(Exception):
    """The PDF could not be read, or nothing usable came out of it."""


@dataclass
class Project:
    name: str
    description: str
    tech: list[str] = field(default_factory=list)


@dataclass
class CandidateProfile:
    name: str
    education: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    experience: list[str] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def for_api(self) -> dict:
        """The shape sent back to the frontend - everything but raw_text.

        raw_text exists for the interviewer (Phase 3) to ground follow-up
        questions in the actual document; the UI only ever renders the
        structured fields, so there's no reason to ship a whole resume's
        worth of text back down the wire for it to ignore.
        """
        data = self.to_dict()
        del data["raw_text"]
        return data


def extract_text(pdf_bytes: bytes) -> str:
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise ResumeParseError(
            f"file too large ({len(pdf_bytes) // 1024} KB) - is this actually a resume?"
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except PdfReadError as exc:
        raise ResumeParseError(f"not a readable PDF: {exc}") from exc

    pages = [page.extract_text() or "" for page in reader.pages]
    text = "\n".join(pages).strip()
    if not text:
        raise ResumeParseError(
            "no extractable text found - this may be a scanned/image-only PDF"
        )
    return text


def _client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.cerebras_api_key, base_url=CEREBRAS_BASE_URL)


async def structure(raw_text: str) -> CandidateProfile:
    completion = await _client().chat.completions.create(
        model=settings.model,
        messages=[
            {"role": "system", "content": _STRUCTURE_PROMPT},
            {"role": "user", "content": raw_text},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "candidate_profile",
                "schema": _PROFILE_SCHEMA,
                "strict": True,
            },
        },
    )
    content = completion.choices[0].message.content or "{}"
    payload = json.loads(content)

    projects = [
        Project(
            name=str(p.get("name", "")),
            description=str(p.get("description", "")),
            tech=[str(t) for t in p.get("tech", [])],
        )
        for p in payload.get("projects", [])
    ]
    return CandidateProfile(
        name=str(payload.get("name", "")),
        education=[str(e) for e in payload.get("education", [])],
        skills=[str(s) for s in payload.get("skills", [])],
        projects=projects,
        experience=[str(e) for e in payload.get("experience", [])],
        raw_text=raw_text,
    )


async def parse_resume(pdf_bytes: bytes) -> CandidateProfile:
    text = extract_text(pdf_bytes)
    return await structure(text)
