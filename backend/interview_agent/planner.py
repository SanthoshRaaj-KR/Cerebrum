"""Builds the interview's question plan before the first question is asked.

A real interview isn't a shuffled question bag - it has a shape. The
interviewer opens easy to settle the candidate, goes deep on a few areas
rather than skimming ten, escalates as answers hold up, and leaves time to
close. Without a plan the model does what a nervous interviewer does:
follows whatever the last answer suggested, wanders, and never covers the
ground the mode is supposed to cover.

The plan is also visible to the candidate - it's the numbered list down the
left of the interview screen - so the slots need short labels a person can
read at a glance.

Each slot is a topic, not a script. The question actually asked is
generated in context at the time, so it can pick up on what the candidate
just said; the slot only decides what ground it covers.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from interview_agent.config import settings
from interview_agent.context import CandidateContext
from interview_agent.llm import client
from interview_agent.prompts import Mode, mode_prompt

logger = logging.getLogger("interview_agent.planner")

MAX_TOKENS = 1200


@dataclass
class Slot:
    short: str
    focus: str
    opening_question: str
    hint: str = ""


_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "short": {"type": "string"},
                    "focus": {"type": "string"},
                    "opening_question": {"type": "string"},
                    "hint": {"type": "string"},
                },
                "required": ["short", "focus", "opening_question", "hint"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

_PROMPT = """\
You are an experienced technical interviewer planning a mock interview
before it starts. Lay out exactly {count} questions, in the order you will
ask them.

Shape it the way a real interview is actually run:
- Question 1 is a warm-up that gets them talking and settled. Never open
  with the hardest thing you plan to ask.
- The middle questions are the substance. Go deep on two or three areas
  rather than touching {count} unrelated ones - consecutive questions
  working the same area from different angles is good interviewing.
- Difficulty escalates. The last technical question should be meaningfully
  harder than the first.
- The final question closes the interview off.

For each question give:
- short: a 2-4 word label for the progress sidebar, e.g. "Indexing cost"
  or "Recent project". Not a sentence.
- focus: one sentence on what you're trying to find out, and what a strong
  answer would contain. This is for you, not shown to the candidate.
- opening_question: the exact words you'd SAY OUT LOUD to open this. One
  or two sentences, conversational, the way a person actually talks. Not a
  written-exam prompt.
- hint: a short nudge shown under the question if the candidate looks
  stuck, e.g. "Say what you're excluding before you start designing."
  Empty string for questions that need none - most don't.

Pick the areas that matter most for this mode and are fair for this
candidate's level. Where the résumé gives you something concrete to work
with, use it.
"""


def _fallback(mode: Mode, count: int) -> list[Slot]:
    """A failed planning call shouldn't cost the candidate their session -
    they came here to practise, not to read an error."""
    logger.warning("using the fallback plan for mode %s", mode.key)
    slots = [
        Slot(
            short="Warm-up",
            focus="Settle the candidate and find out what they know.",
            opening_question=(
                "Let's start easy - tell me a bit about your background and "
                "what you've been working on recently."
            ),
        )
    ]
    for i in range(count - 1):
        slots.append(
            Slot(
                short=f"{mode.name}, part {i + 1}",
                focus=(
                    f"Probe {mode.name} in depth, escalating as answers hold up."
                ),
                opening_question="",
            )
        )
    return slots


async def build_plan(mode: Mode, candidate: CandidateContext) -> list[Slot]:
    """The question plan. Never raises."""
    count = settings.questions_per_session
    level = candidate.level.strip() or (
        "fresher / entry-level" if settings.fresher else "experienced"
    )

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": _PROMPT.format(count=count)},
                {
                    "role": "user",
                    "content": (
                        f"Candidate level: {level}\n\n{mode_prompt(mode.key, candidate)}"
                    ),
                },
            ],
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "plan", "schema": _SCHEMA, "strict": True},
            },
        )
        raw = json.loads(completion.choices[0].message.content or "{}").get("questions", [])
        slots = [
            Slot(
                short=str(q.get("short", "")).strip() or f"Question {i + 1}",
                focus=str(q.get("focus", "")).strip(),
                opening_question=str(q.get("opening_question", "")).strip(),
                hint=str(q.get("hint", "")).strip(),
            )
            for i, q in enumerate(raw)
        ]
        if not slots:
            raise ValueError("planner returned no questions")
    except Exception:  # noqa: BLE001
        logger.exception("could not build a question plan")
        return _fallback(mode, count)

    # The model occasionally returns a different number than asked for.
    # The UI counts "Q3 of 6" against this list, so make it authoritative.
    if len(slots) > count:
        slots = slots[:count]
    while len(slots) < count:
        slots.append(_fallback(mode, count)[len(slots)])
    return slots


def render(slots: list[Slot], current: int) -> str:
    """The plan as prompt text, marking where the interview has got to."""
    lines = ["QUESTION PLAN - you are working through these in order:"]
    for i, s in enumerate(slots):
        marker = "  <- you are here" if i == current else ""
        state = "done" if i < current else ("now" if i == current else "upcoming")
        lines.append(f"\n{i + 1}. [{state}] {s.short}{marker}")
        if s.focus:
            lines.append(f"   Looking for: {s.focus}")
        if i == current and s.opening_question:
            lines.append(f"   Planned opening: {s.opening_question}")
    return "\n".join(lines)
