"""Coach notes and the end-of-session headline.

Separate from the per-answer grader because it reads across the whole
interview: the useful feedback at the end is usually a pattern ("you bury
the result in the last sentence") rather than a restatement of any single
grade.
"""

from __future__ import annotations

import json
import logging

from interview_agent.config import settings
from interview_agent.llm import client
from interview_agent.interviewer import InterviewSession

logger = logging.getLogger("interview_agent.report")

MAX_TOKENS = 600

_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["headline", "notes"],
    "additionalProperties": False,
}

_PROMPT = """\
You just finished interviewing this candidate. Write the notes you'd hand
them afterwards.

headline: one sentence on where they landed overall, addressed to them.
Honest, not flattering - "Close. Depth is the gap, not structure." is more
useful than "Great job!". No score number in it.

notes: two to four short coaching notes, each one sentence, each about a
PATTERN you saw across several answers rather than a single answer. The
things a good coach notices: burying the result at the end, saying "we"
for work they clearly owned, never naming a number, reaching for the
first tool without weighing an alternative, answers running long, hedging
instead of committing. Only write notes you can actually justify from the
transcript below. If they did something well consistently, one note may
say so.

Address the candidate as "you". No markdown.
"""


def _transcript(session: InterviewSession) -> str:
    parts = []
    for t in session.turns:
        parts.append(f"Q{t.index + 1} ({t.short}): {t.question}")
        if t.skipped:
            parts.append("Answer: (skipped)")
        elif t.answer:
            parts.append(f"Answer: {t.answer}")
        if t.grade and t.grade.score > 0:
            parts.append(f"Scored {t.grade.score}/10 - {t.grade.verdict}")
        parts.append("")
    return "\n".join(parts)


async def build(session: InterviewSession) -> dict:
    """Headline plus coach notes. Never raises."""
    graded = session.graded()
    if not graded:
        return {
            "headline": "No answers to score yet.",
            "notes": ["Notes appear once your first answer is graded."],
        }

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": _PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Interview mode: {session.mode.name}\n"
                        f"Target role: {session.candidate.role or 'unspecified'}\n"
                        f"Level: {session.candidate.level or 'unspecified'}\n"
                        f"Average score: {session.average()}/10\n\n"
                        f"TRANSCRIPT\n{_transcript(session)}"
                    ),
                },
            ],
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "report", "schema": _SCHEMA, "strict": True},
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
        notes = [str(n).strip() for n in payload.get("notes", []) if str(n).strip()]
        return {
            "headline": str(payload.get("headline", "")).strip() or _fallback_headline(session),
            "notes": notes or ["No pattern stood out across these answers."],
        }
    except Exception:  # noqa: BLE001
        logger.exception("could not build the session report")
        return {"headline": _fallback_headline(session), "notes": []}


def _fallback_headline(session: InterviewSession) -> str:
    avg = session.average() or 0
    if avg >= 8:
        return "Interview-ready on this track."
    if avg >= 6.5:
        return "Close. Depth is the gap, not structure."
    if avg >= 4:
        return "Structure is fine; the specifics are not there yet."
    return "The fundamentals need another pass before this round."
