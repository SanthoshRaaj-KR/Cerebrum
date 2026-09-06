"""The interviewer's private read on one answer.

Never shown to the candidate - this is working notes, not feedback. It has
one job: judge the answer that just came in, well enough that the next
question can react to it. Was the claim actually correct? Is this the
second weak answer on the same ground, meaning it's time to move? What
would a right answer have contained that this one didn't?

Deliberately a separate, structured call from asking the question, for the
same reason grader.py used to be separate: a call that has to both judge
and speak fluently tends to do one of them badly - usually the judgement
leaking into the voice as "great answer!" right before the next question.

This is the fast, on-the-critical-path half of evaluation: the next
question genuinely depends on it, so it runs on the cheap model and stays
small. The heavier running score (scorecard.py) is the half that gets to
take its time in the background.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from interview_agent.config import settings
from interview_agent.llm import client

logger = logging.getLogger("interview_agent.evaluator")

MAX_TOKENS = 450

_READS = ("strong", "thin", "wrong", "dodged", "dont_know")

# How much a read counts toward "we've shown something on this competency" -
# used only to decide what still needs covering, never surfaced as a score.
_STRENGTH = {"strong": 3, "thin": 1, "wrong": 0, "dodged": 0, "dont_know": 0}

_PRIOR_WEAK = ("thin", "wrong", "dodged", "dont_know")


@dataclass
class CompetencyBar:
    """One competency and what counts as having it at entry level."""

    name: str
    fresher_bar: str = ""


@dataclass
class Rubric:
    """What the evaluator judges against. Built from the role brief (or,
    for résumé mode, from the résumé) by whoever owns the session - this
    module deliberately doesn't import research.py, so the same evaluator
    serves any source of competencies."""

    competencies: list[CompetencyBar] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.competencies]

    def render(self) -> str:
        if not self.competencies and not self.red_flags:
            return "No competency map was gathered - judge generally for this role."

        lines: list[str] = []
        if self.competencies:
            lines.append(
                "COMPETENCIES TRACKED, and what counts as HAVING each one at "
                "entry level. Judge against this bar, not a senior one:"
            )
            for c in self.competencies:
                bar = f" - {c.fresher_bar}" if c.fresher_bar else ""
                lines.append(f"- {c.name}{bar}")
        if self.red_flags:
            lines.append(
                "\nCLAIMS THAT ARE SIMPLY WRONG for this role. If the answer "
                "asserts one of these, the read is `wrong` however fluently "
                "it was said:"
            )
            for r in self.red_flags:
                lines.append(f"- {r}")
        return "\n".join(lines)


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
    # What a correct answer would have contained that this one didn't.
    # Empty when the answer held up. Forces the judgement to be a concrete
    # delta rather than a bare label, and gives the running score something
    # auditable to carry forward.
    gap: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


_SCHEMA = {
    "type": "object",
    "properties": {
        "read": {"type": "string", "enum": list(_READS)},
        "evidenced": {"type": "array", "items": {"type": "string"}},
        "topic_exhausted": {"type": "boolean"},
        "thread": {"type": "string"},
        "focus": {"type": "string"},
        "gap": {"type": "string"},
    },
    "required": ["read", "evidenced", "topic_exhausted", "thread", "focus", "gap"],
    "additionalProperties": False,
}

_PROMPT = """\
You are the interviewer's private scratchpad, never shown to the
candidate. Read the last question and answer and record your honest read.

{rubric}

Judge the CONTENT of what they said, not its topic or its fluency. That
they talked about indexing is not evidence indexing was understood. Work
it out explicitly: what would a correct answer contain, what did they
actually say, where is the difference. A confident, well-phrased, WRONG
claim is `wrong` - do not let delivery carry it.

- read: strong (correct, specific, shows real reasoning) / thin (right
  shape, shallow) / wrong (a confident but incorrect claim) / dodged
  (answered something else, deflected, asked for clarification instead of
  attempting an answer, or skipped) / dont_know (an honest admission they
  don't know - this is NOT the same as wrong, do not conflate them; being
  straight about not knowing is worth more than bluffing).
- evidenced: which of the tracked competencies this answer actually gave
  evidence on, by name exactly as listed above. Empty list if none. Only
  list one if what they said about it was RIGHT - being wrong about a
  topic is not evidence of the competency.
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
- gap: what a correct answer would have contained that theirs didn't, in
  one short sentence. Empty string when the answer genuinely held up. For
  a `wrong` read, name the specific thing that was wrong and what is
  actually true.
"""


async def read(
    question: str,
    answer: str,
    skipped: bool,
    rubric: Rubric,
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
                {"role": "system", "content": _PROMPT.format(rubric=rubric.render())},
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

    read_value = str(payload.get("read", "")).strip()
    if read_value not in _READS:
        read_value = "thin"

    # Only trust a focus that names a competency we're actually tracking -
    # a free-text guess would just pollute the ledger.
    names = rubric.names
    focus = str(payload.get("focus", "")).strip()
    if focus not in names:
        focus = ""

    # Deterministic safety net, independent of whether the model followed
    # the topic_exhausted instruction above: two weak reads in a row on the
    # same ground always counts as exhausted. This is the guard the
    # original grader-in-the-loop design had (see interviewer.py's git
    # history) after the model re-asked the same question three times
    # without it - it must not depend on the model reliably reasoning about
    # a previous turn it can't see in this isolated call.
    topic_exhausted = bool(payload.get("topic_exhausted", False)) or (
        prior_read in _PRIOR_WEAK and read_value in _PRIOR_WEAK
    )

    return AnswerNote(
        read=read_value,
        evidenced=[
            str(e).strip()
            for e in payload.get("evidenced", [])
            if str(e).strip() in names
        ],
        topic_exhausted=topic_exhausted,
        thread=str(payload.get("thread", "")).strip(),
        focus=focus,
        gap=str(payload.get("gap", "")).strip(),
    )


def strength_of(read_value: str) -> int:
    return _STRENGTH.get(read_value, 1)
