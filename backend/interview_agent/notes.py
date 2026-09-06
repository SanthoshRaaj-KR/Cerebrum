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
    # Which single tracked competency the question was mainly probing.
    # Empty for an opener or small talk. With no clock, this is how the
    # ledger knows a competency has been worked even when the answer proved
    # nothing - so it doesn't get picked again as "untouched ground".
    focus: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CoverageLedger:
    """Which competencies the candidate has shown something on, and how
    strongly - carried across the whole interview, independent of how much
    of the raw transcript is still in context.

    With the clock gone, this ledger is also the interview's end condition:
    when every competency is "settled" - shown at thin-or-better, or worked
    until the edge of what they know was found - there's nothing left to
    cover and the interview wraps up (see interviewer.InterviewSession)."""

    touched: dict[str, int] = field(default_factory=dict)
    # Competencies pushed on twice with weak answers - the edge of what the
    # candidate knows here has been found, so they count as done even though
    # `touched` may still be 0 for them.
    exhausted: set[str] = field(default_factory=set)

    def record(
        self,
        evidenced: list[str],
        strength: int,
        focus: str = "",
        exhausted: bool = False,
    ) -> None:
        for name in evidenced:
            self.touched[name] = max(self.touched.get(name, 0), strength)
        # A focused question that proved nothing still puts the competency
        # on the board, so it isn't mistaken for never-asked ground.
        if focus and focus not in self.touched:
            self.touched[focus] = 0
        if focus and exhausted:
            self.exhausted.add(focus)

    def settled(self, all_names: list[str]) -> list[str]:
        """Competencies with nothing more worth asking: shown at
        thin-or-better, or the edge of what they know was found."""
        return [
            n
            for n in all_names
            if self.touched.get(n, 0) >= 1 or n in self.exhausted
        ]

    def open_ground(self, all_names: list[str]) -> list[str]:
        done = set(self.settled(all_names))
        return [n for n in all_names if n not in done]

    def progress(self, all_names: list[str]) -> float:
        if not all_names:
            return 0.0
        return len(self.settled(all_names)) / len(all_names)

    def render(self, all_competencies: list[str]) -> str:
        if not all_competencies:
            return ""
        settled = self.settled(all_competencies)
        open_ground = [n for n in all_competencies if n not in set(settled)]
        total = len(all_competencies)

        if not open_ground:
            return (
                f"COVERAGE - you now have a read on all {total} competencies "
                "tracked for this role. Push hardest on whatever has held up, "
                "or wrap the interview up; do not open brand-new ground now."
            )

        frac = len(settled) / total
        lead = (
            f"COVERAGE - {len(settled)} of {total} competencies have a read. "
            f"Nothing shown yet on: {', '.join(open_ground)}."
        )
        if frac < 0.34:
            tail = (
                " Still early - go deep on two or three of these rather than "
                "touching all of them at once."
            )
        elif frac < 0.75:
            tail = (
                " Weigh these when you pick new ground, and keep raising the "
                "difficulty."
            )
        else:
            tail = (
                " Near the end of coverage - get something on what's left, "
                "push hardest on what's held up, and don't start a brand-new "
                "deep topic."
            )
        return lead + tail


_SCHEMA = {
    "type": "object",
    "properties": {
        "read": {"type": "string", "enum": list(_READS)},
        "evidenced": {"type": "array", "items": {"type": "string"}},
        "topic_exhausted": {"type": "boolean"},
        "thread": {"type": "string"},
        "focus": {"type": "string"},
    },
    "required": ["read", "evidenced", "topic_exhausted", "thread", "focus"],
    "additionalProperties": False,
}

_PROMPT = """\
You are the interviewer's private scratchpad, never shown to the
candidate. Read the last question and answer and record your honest read.

Competencies being tracked for this role: {competencies}

- read: strong (correct, specific, shows real reasoning) / thin (right
  shape, shallow) / wrong (a confident but incorrect claim) / dodged
  (answered something else, deflected, asked for clarification instead of
  attempting an answer, or skipped) / dont_know (an honest admission they
  don't know - this is NOT the same as wrong, do not conflate them; being
  straight about not knowing is worth more than bluffing).
- evidenced: which of the tracked competencies this answer actually gave
  evidence on, by name exactly as listed above. Empty list if none.
- topic_exhausted: you are told below whether the PREVIOUS answer, on this
  same ground, was also weak (thin/wrong/dodged/dont_know). Set this true
  if THIS answer is weak too - any combination of thin, wrong, dodged, or
  dont_know counts, they do not have to be the same read twice. Two weak
  answers in a row on the same ground means the edge of what they know or
  are willing to say has been found, and asking a third time in any form
  is grinding, not interviewing. If the previous answer was strong, or
  this is the first question on new ground, this is always false.
- thread: the single most interesting specific thing in their answer worth
  pulling on next, in a few words. Empty string if nothing stands out.
- focus: which single tracked competency (from the list above, by name
  exactly) the question was mainly probing. Empty string if it was an
  opener or small talk that wasn't really about any of them.
"""

_PRIOR_WEAK = ("thin", "wrong", "dodged", "dont_know")


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
        return AnswerNote(read="dodged", topic_exhausted=prior_read in _PRIOR_WEAK)

    prior_line = (
        f"The PREVIOUS answer on this same ground was read as: {prior_read}."
        if prior_read
        else "This is the first question on this ground - no previous answer "
        "to compare against."
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
                    "content": f"{prior_line}\n\nQUESTION:\n{question}\n\nANSWER:\n{answer}",
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

    # Only trust a focus that names a competency we're actually tracking -
    # a free-text guess would just pollute the ledger.
    focus = str(payload.get("focus", "")).strip()
    if focus not in competencies:
        focus = ""

    # Deterministic safety net, independent of whether the model followed
    # the topic_exhausted instruction above: two weak reads in a row on the
    # same ground always counts as exhausted. This is the guard the
    # original grader-in-the-loop design had (see interviewer.py's git
    # history) after the model re-asked the same question three times
    # without it - it must not depend on the model reliably reasoning about
    # a previous turn it can't see in this isolated call.
    topic_exhausted = bool(payload.get("topic_exhausted", False)) or (
        prior_read in _PRIOR_WEAK and read in _PRIOR_WEAK
    )

    return AnswerNote(
        read=read,
        evidenced=[str(e).strip() for e in payload.get("evidenced", []) if str(e).strip()],
        topic_exhausted=topic_exhausted,
        thread=str(payload.get("thread", "")).strip(),
        focus=focus,
    )


def strength_of(read: str) -> int:
    return _STRENGTH.get(read, 1)
