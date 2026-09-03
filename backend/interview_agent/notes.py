"""The interviewer's private read on the interview so far.

Not shown to the candidate, ever - this is the interviewer's own working
notes. It does two jobs:

1. Sharpen the very next question: was the last answer strong, thin,
   wrong, dodged, or an honest "I don't know" - and have we already pushed
   on this ground once before, which means it's time to move rather than
   grind.
2. Carry coverage forward once the transcript outgrows remember_turns - a
   40-minute interview has more turns than comfortably fit in context, so
   this ledger is what still remembers "we've never touched testing" after
   the turns that would have shown that have scrolled out of the window.

Deliberately a separate, structured call from asking the question, for the
same reason grader.py used to be separate: a call that has to both judge
and speak fluently tends to do one of them badly - usually the judgment
leaking into the voice as "great answer!" right before the next question.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from interview_agent.config import settings
from interview_agent.llm import client

logger = logging.getLogger("interview_agent.notes")

MAX_TOKENS = 350

_READS = ("strong", "thin", "wrong", "dodged", "dont_know")

# How much a read counts toward "we've shown something on this competency" -
# used only to decide what still needs covering, never surfaced as a score.
_STRENGTH = {"strong": 3, "thin": 1, "wrong": 0, "dodged": 0, "dont_know": 0}


@dataclass
class AnswerNote:
    read: str = ""
    evidenced: list[str] = field(default_factory=list)
    topic_exhausted: bool = False
    thread: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CoverageLedger:
    """Which competencies the candidate has shown something on, and how
    strongly - carried across the whole interview, independent of how much
    of the raw transcript is still in context."""

    touched: dict[str, int] = field(default_factory=dict)

    def record(self, names: list[str], strength: int) -> None:
        for name in names:
            self.touched[name] = max(self.touched.get(name, 0), strength)

    def untouched(self, all_names: list[str]) -> list[str]:
        return [n for n in all_names if n not in self.touched]

    def render(self, all_competencies: list[str]) -> str:
        if not all_competencies:
            return ""
        gaps = self.untouched(all_competencies)
        if not gaps:
            return (
                "COVERAGE - you have at least touched on every competency "
                "you're tracking for this role."
            )
        return (
            "COVERAGE - nothing shown yet on: "
            f"{', '.join(gaps)}. Weigh these when you pick new ground."
        )


_SCHEMA = {
    "type": "object",
    "properties": {
        "read": {"type": "string", "enum": list(_READS)},
        "evidenced": {"type": "array", "items": {"type": "string"}},
        "topic_exhausted": {"type": "boolean"},
        "thread": {"type": "string"},
    },
    "required": ["read", "evidenced", "topic_exhausted", "thread"],
    "additionalProperties": False,
}

_PROMPT = """\
You are the interviewer's private scratchpad, never shown to the
candidate. Read the last question and answer and record your honest read.

Competencies being tracked for this role: {competencies}

- read: strong (correct, specific, shows real reasoning) / thin (right
  shape, shallow) / wrong (a confident but incorrect claim) / dodged
  (answered something else, or skipped) / dont_know (an honest admission
  they don't know - this is NOT the same as wrong, do not conflate them;
  being straight about not knowing is worth more than bluffing).
- evidenced: which of the tracked competencies this answer actually gave
  evidence on, by name exactly as listed above. Empty list if none.
- topic_exhausted: true only if this is at least the second consecutive
  weak/thin answer on the SAME ground - meaning the edge of what they know
  here has already been found, and pushing a third time would be
  grinding, not interviewing.
- thread: the single most interesting specific thing in their answer worth
  pulling on next, in a few words. Empty string if nothing stands out.
"""


async def take(
    question: str,
    answer: str,
    skipped: bool,
    competencies: list[str],
    prior_read: str,
) -> AnswerNote:
    """Never raises - a failed read just means the next question falls back
    to the reactive ladder's own judgement from the raw transcript."""
    if skipped or not (answer or "").strip():
        return AnswerNote(
            read="dodged",
            topic_exhausted=prior_read in ("thin", "wrong", "dodged"),
        )

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": _PROMPT.format(
                        competencies=", ".join(competencies) or "none tracked"
                    ),
                },
                {
                    "role": "user",
                    "content": f"QUESTION:\n{question}\n\nANSWER:\n{answer}",
                },
            ],
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "answer_note", "schema": _SCHEMA, "strict": True},
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("could not take a private read on the last answer")
        return AnswerNote()

    read = str(payload.get("read", "")).strip()
    if read not in _READS:
        read = "thin"
    return AnswerNote(
        read=read,
        evidenced=[str(e).strip() for e in payload.get("evidenced", []) if str(e).strip()],
        topic_exhausted=bool(payload.get("topic_exhausted", False)),
        thread=str(payload.get("thread", "")).strip(),
    )


def strength_of(read: str) -> int:
    return _STRENGTH.get(read, 1)
