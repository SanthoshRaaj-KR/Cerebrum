"""Résumé text -> a small structured digest, once, before the interview.

pypdf (and people pasting out of a PDF) produce noisy text: interleaved
columns, wrapped bullets, header/footer crumbs. One LLM call at session
start turns that into a clean, stable shape - named projects with their
stack, the skills actually claimed, any real experience, education - that
every turn's prompt can lean on without re-parsing the raw text each time.

The raw text is still carried alongside it (see interviewer.InterviewSession)
so the interviewer can quote the candidate's exact words when it challenges
a claim. Nothing here is evaluative - it's extraction, not judgement, and
it runs on the cheap model.

Source-text verification: any field whose identifying text can't be found
back in the raw résumé is dropped, so a hallucinated project or a skill
the model "rounded up to" never reaches the interview.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field

from interview_agent.config import settings
from interview_agent.llm import client

logger = logging.getLogger("interview_agent.resume")

MAX_TOKENS = 900


@dataclass
class Project:
    name: str
    stack: list[str] = field(default_factory=list)
    highlights: list[str] = field(default_factory=list)


@dataclass
class Experience:
    org: str
    role: str = ""
    duration: str = ""


@dataclass
class ResumeDigest:
    projects: list[Project] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    experience: list[Experience] = field(default_factory=list)
    education: str = ""
    # False when the digest call itself failed - the interview then works
    # from the raw résumé text alone, which is still fine.
    ok: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    def is_empty(self) -> bool:
        return not (self.projects or self.skills or self.experience or self.education)

    def render(self) -> str:
        """The block injected into the interviewer's system prompt."""
        if self.is_empty():
            return ""
        lines = [
            "RÉSUMÉ DIGEST - the structured read of their résumé, for deciding "
            "what to probe. Their own wording is in the candidate block above; "
            "quote from that when you put a claim to them."
        ]
        if self.projects:
            lines.append("\nProjects:")
            for p in self.projects:
                stack = f" [{', '.join(p.stack)}]" if p.stack else ""
                lines.append(f"- {p.name}{stack}")
                for h in p.highlights:
                    lines.append(f"    {h}")
        if self.skills:
            lines.append("\nSkills claimed: " + ", ".join(self.skills))
        if self.experience:
            lines.append("\nExperience:")
            for e in self.experience:
                bits = " - ".join(x for x in (e.role, e.org, e.duration) if x)
                lines.append(f"- {bits}")
        if self.education:
            lines.append(f"\nEducation: {self.education}")
        return "\n".join(lines)


_SCHEMA = {
    "type": "object",
    "properties": {
        "projects": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "stack": {"type": "array", "items": {"type": "string"}},
                    "highlights": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "stack", "highlights"],
                "additionalProperties": False,
            },
        },
        "skills": {"type": "array", "items": {"type": "string"}},
        "experience": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "org": {"type": "string"},
                    "role": {"type": "string"},
                    "duration": {"type": "string"},
                },
                "required": ["org", "role", "duration"],
                "additionalProperties": False,
            },
        },
        "education": {"type": "string"},
    },
    "required": ["projects", "skills", "experience", "education"],
    "additionalProperties": False,
}

_PROMPT = """\
Extract a structured digest from this résumé. Copy what is there - do not
infer, upgrade, or add anything the text doesn't say.

- projects: each named project or notable piece of personal / academic
  work. name as written; stack = technologies named for THAT project;
  highlights = up to 2 short phrases of what they did, their words where
  possible.
- skills: technologies and tools the résumé explicitly lists as skills or
  clearly claims hands-on use of. Do not add adjacent ones.
- experience: real jobs / internships only - org, role, duration as
  written. Empty list if the résumé shows none (a fresher résumé often
  has none).
- education: the single highest or most recent qualification, one line.

If something isn't in the text, leave it out. An empty field is the
correct answer when the résumé doesn't cover it.
"""


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _appears(needle: str, haystack_norm: str) -> bool:
    """Containment check, tolerant of the model reformatting the text: the
    whole phrase, or every wordish token of it (4+ chars) appearing
    somewhere. The all-tokens rule, not longest-token, so a hallucinated
    "Ghost Project" isn't rescued by the résumé's "PROJECTS" heading."""
    n = _norm(needle)
    if not n:
        return False
    if n in haystack_norm:
        return True
    tokens = [t for t in re.split(r"[^a-z0-9+#.]+", n) if len(t) >= 4]
    return bool(tokens) and all(t in haystack_norm for t in tokens)


def _verify(d: ResumeDigest, raw: str) -> ResumeDigest:
    h = _norm(raw)
    d.projects = [p for p in d.projects if _appears(p.name, h)]
    d.skills = [s for s in d.skills if _appears(s, h)]
    d.experience = [e for e in d.experience if _appears(e.org, h)]
    if d.education and not _appears(d.education[:20], h):
        d.education = ""
    return d


async def digest(resume_text: str) -> ResumeDigest:
    """Never raises - a failed digest just means the interview works from
    the raw résumé text alone."""
    raw = (resume_text or "").strip()
    if not raw:
        return ResumeDigest()

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": raw},
            ],
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "resume_digest", "schema": _SCHEMA, "strict": True},
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("could not digest the résumé")
        return ResumeDigest(ok=False)

    out = ResumeDigest(
        projects=[
            Project(
                name=str(p.get("name", "")).strip(),
                stack=[str(x).strip() for x in p.get("stack", []) if str(x).strip()],
                highlights=[str(x).strip() for x in p.get("highlights", []) if str(x).strip()],
            )
            for p in payload.get("projects", [])
            if str(p.get("name", "")).strip()
        ],
        skills=[str(s).strip() for s in payload.get("skills", []) if str(s).strip()],
        experience=[
            Experience(
                org=str(e.get("org", "")).strip(),
                role=str(e.get("role", "")).strip(),
                duration=str(e.get("duration", "")).strip(),
            )
            for e in payload.get("experience", [])
            if str(e.get("org", "")).strip()
        ],
        education=str(payload.get("education", "")).strip(),
    )
    return _verify(out, raw)
