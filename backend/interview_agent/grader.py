"""Grades one answer against the mode's rubric.

Its own call, separate from asking the next question, for two reasons.
The interviewer prompt is under strict orders not to evaluate out loud -
mixing "judge this" into the same call is how you get "great answer!"
leaking into the next question. And grading wants structured output
(numbers, fixed dimensions) while a question wants prose; one call cannot
be both without the JSON ending up spoken aloud.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from interview_agent.config import settings
from interview_agent.llm import client
from interview_agent.prompts import Mode

logger = logging.getLogger("interview_agent.grader")

MAX_TOKENS = 500


@dataclass
class DimScore:
    name: str
    score: float


@dataclass
class Grade:
    score: float
    verdict: str
    strength: str
    gap: str
    topic: str = ""
    rubric: list[DimScore] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_SCHEMA = {
    "type": "object",
    "properties": {
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "score": {"type": "number"},
                },
                "required": ["name", "score"],
                "additionalProperties": False,
            },
        },
        "topic": {"type": "string"},
        "verdict": {"type": "string"},
        "strength": {"type": "string"},
        "gap": {"type": "string"},
    },
    "required": ["dimensions", "topic", "verdict", "strength", "gap"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """\
You are grading one answer from a technical mock interview, for a
{level} candidate interviewing for: {role}.

Score each of these three dimensions from 1 to 10: {dims}.

Calibrate honestly - this is practice, and inflated scores waste the
candidate's time:
- 8-10: genuinely strong. Specific, correct, and shows reasoning beyond
  the definition.
- 6-7.9: solid but shallow. Right shape, thin substance.
- 4-5.9: partially right, or too general to evaluate.
- 1-3.9: wrong, evasive, or essentially non-responsive.
A skipped or empty answer scores 1 across the board.

Two things to get right, because they are easy to score badly:
- A candidate who plainly says "I don't know" is not the same as one who
  bluffs. Correctness and depth are still low - they didn't answer - but
  do not punish the communication dimension for it, and say in the
  strength field that being straight about it beats guessing. Bluffing a
  confident wrong answer should score BELOW an honest admission.
- A confidently stated wrong claim is worse than a vague one. Score
  correctness at the bottom of the range and name the error plainly in
  the gap, so they don't walk away still believing it.

Also write:
- topic: a 2-4 word label for what this question was actually about, for
  the progress sidebar. Label the question that was ASKED, not the answer
  given - if the interviewer challenged a claim, that challenge is the
  topic. Examples: "Index write cost", "Password storage", "JWT
  revocation". Not a sentence.

Then write, addressed to the candidate as "you":
- verdict: where this lands, in at most eight words. It renders inline
  next to the score, so it must be a short phrase, not a sentence about
  the answer. Examples: "Strong - hire signal.", "Solid, room to go
  deeper.", "Right shape, thin substance.", "Too general to evaluate."
  No score number in it.
- strength: what actually worked. If nothing did, say so plainly rather
  than inventing praise.
- gap: the single most useful thing missing - what a strong candidate
  would have said here that they didn't. Be concrete and specific to
  their answer; generic advice is useless.

Keep strength and gap to one sentence each. Judge the answer against what
is fair for this level, not against a senior engineer.
"""


def _fallback(mode: Mode, answered: bool) -> Grade:
    """A failed grading call shouldn't end the interview. Marked clearly so
    it can't be mistaken for a real score."""
    return Grade(
        score=0.0,
        verdict="Grading was unavailable for this answer.",
        topic="",
        strength="",
        gap="",
        rubric=[DimScore(name=d, score=0.0) for d in mode.dims],
    )


def _clamp(v: float) -> float:
    return round(max(1.0, min(10.0, float(v))), 1)


async def grade(
    mode: Mode, question: str, answer: str, role: str, level: str
) -> Grade:
    """Never raises - a grading failure degrades to an unavailable grade
    rather than costing the candidate their session."""
    answered = bool((answer or "").strip())

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": _INSTRUCTIONS.format(
                        dims=", ".join(mode.dims),
                        role=role.strip() or "an unspecified role",
                        level=level.strip() or "entry-level",
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Interview mode: {mode.name}\n\n"
                        f"QUESTION ASKED:\n{question}\n\n"
                        f"CANDIDATE'S ANSWER:\n"
                        f"{answer.strip() if answered else '(skipped - no answer given)'}"
                    ),
                },
            ],
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "grade", "schema": _SCHEMA, "strict": True},
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("could not grade an answer")
        return _fallback(mode, answered)

    # Trust the mode's dimension names over whatever the model echoed back,
    # so the UI's three bars always line up with the rubric it advertised.
    scored = {d.get("name", ""): d.get("score", 0) for d in payload.get("dimensions", [])}
    rubric = [
        DimScore(name=name, score=_clamp(scored.get(name, next(iter(scored.values()), 5))))
        for name in mode.dims
    ]
    overall = round(sum(d.score for d in rubric) / len(rubric), 1) if rubric else 0.0

    return Grade(
        score=overall,
        topic=str(payload.get("topic", "")).strip(),
        verdict=str(payload.get("verdict", "")).strip(),
        strength=str(payload.get("strength", "")).strip(),
        gap=str(payload.get("gap", "")).strip(),
        rubric=rubric,
    )
