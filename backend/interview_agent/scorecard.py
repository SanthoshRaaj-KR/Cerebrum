"""The end-of-interview scorecard.

Nothing is scored while the interview is running - no score, no rubric,
no "missing" line ever reaches the candidate mid-session, because no real
interviewer grades you to your face. grader.py and report.py used to be
two separate calls (score each answer as it happens, then look for
patterns across the transcript afterwards); this replaces both with one
call at the end, over the whole conversation and the competency map
research.py grounded it in.

The calibration below exists because a fresher's scorecard has to answer
one honest question - "would a company hire this person as a fresher" -
not "would a senior engineer be impressed by them". Getting that wrong in
either direction wastes the practice: too strict and a genuinely
interview-ready fresher walks away thinking they're not; too soft and
someone with real gaps walks away thinking they're fine.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field

from interview_agent.config import settings
from interview_agent.llm import client

logger = logging.getLogger("interview_agent.scorecard")

MAX_TOKENS = 1800

_STATUSES = ("solid", "developing", "not_shown", "not_covered")
_VERDICTS = ("strong_yes", "yes", "borderline", "not_yet")


@dataclass
class CompetencyResult:
    name: str
    status: str
    evidence: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Scorecard:
    verdict: str
    score: float
    headline: str
    strengths: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    competencies: list[CompetencyResult] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    grounded: bool = True

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "score": self.score,
            "headline": self.headline,
            "strengths": self.strengths,
            "gaps": self.gaps,
            "notes": self.notes,
            "competencies": [c.to_dict() for c in self.competencies],
            "sources": self.sources,
            "grounded": self.grounded,
        }


_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": list(_VERDICTS)},
        "score": {"type": "number"},
        "headline": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "array", "items": {"type": "string"}},
        "competencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "status": {"type": "string", "enum": list(_STATUSES)},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "status", "evidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["verdict", "score", "headline", "strengths", "gaps", "notes", "competencies"],
    "additionalProperties": False,
}

_PROMPT = """\
You just finished a mock technical interview with this candidate. Write
their scorecard.

The question you are answering is "would a company hire this person as a
FRESHER / entry-level candidate" - NOT "would a senior engineer be
impressed by them". Calibrate accordingly, deliberately more generously
than a senior-level rubric would:

- Naming the concept correctly, giving one worked example, and reasoning
  about a trade-off out loud IS a solid pass for a fresher - score that
  7-8, not 6. Do not hold an entry-level candidate to a
  production-experience bar.
- An honest "I don't know" on genuinely advanced ground costs very little.
  A confidently stated WRONG claim costs much more than an honest gap -
  score the bluff below the honest admission, always.
- Having no professional experience is never, on its own, a penalty.
- What should actually cost points: claims that were wrong and stated with
  confidence, and not being able to explain their own project one level
  deeper than the rehearsed summary.

For each competency listed below, decide:
- solid: they showed real evidence of it, correct and with some depth.
- developing: touched on it, but shallow, partial, or shaky.
- not_shown: it came up and they didn't have it, or answered wrong.
- not_covered: it never came up in this conversation - the interview
  simply didn't reach it in the time available. Do not penalize this; it
  is a fact about time, not about them.

Then write:
- verdict: strong_yes / yes / borderline / not_yet - would you advance
  this fresher candidate to the next round.
- score: 1-10 overall, calibrated to the fresher bar above, not a senior
  bar.
- headline: one sentence, addressed to them as "you", honest but not
  harsh, and not flattering either. No score number in it.
- strengths: 2-4 short bullets, specific to what they actually said - not
  generic praise.
- gaps: 2-4 short bullets, specific and actionable - what a strong fresher
  answer would have included that theirs didn't.
- notes: 2-4 coaching notes about PATTERNS across several answers, not a
  single answer - burying the result at the end, saying "we" for work they
  clearly owned, never naming a number, reaching for the first tool
  without weighing an alternative, hedging instead of committing. Only
  write what you can actually justify from the transcript below.

Address the candidate as "you" throughout. No markdown, and no score
numbers inside the strengths/gaps/notes text - those are prose, the score
field is the number.
"""


def _transcript(turns) -> str:
    parts = []
    for i, t in enumerate(turns):
        parts.append(f"Q{i + 1}: {t.question}")
        parts.append(f"A{i + 1}: {'(skipped)' if t.skipped else (t.answer or '')}")
        parts.append("")
    return "\n".join(parts)


def _fallback(competency_names: list[str], headline: str) -> Scorecard:
    return Scorecard(
        verdict="borderline",
        score=0.0,
        headline=headline,
        competencies=[CompetencyResult(name=n, status="not_covered") for n in competency_names],
        grounded=False,
    )


async def build(session) -> Scorecard:
    """Never raises - a scoring failure shouldn't cost the candidate a
    readable report, even a degraded one."""
    brief = getattr(session, "brief", None)
    competency_names = [c.name for c in brief.competencies] if brief else []
    answered_turns = [t for t in session.turns if t.answer is not None]

    if not answered_turns:
        return Scorecard(
            verdict="not_yet",
            score=0.0,
            headline="No answers to score yet.",
            notes=["A scorecard appears once you've answered at least one question."],
            competencies=[CompetencyResult(name=n, status="not_covered") for n in competency_names],
        )

    competency_block = (
        "\n".join(
            f"- {c.name}: fair bar for a fresher - {c.fresher_bar}" for c in brief.competencies
        )
        if brief and brief.competencies
        else "(no specific competency map was gathered - judge generally for this role and mode)"
    )

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
                        f"Level: {session.candidate.level or 'fresher'}\n\n"
                        f"COMPETENCIES TRACKED FOR THIS ROLE:\n{competency_block}\n\n"
                        f"TRANSCRIPT\n{_transcript(session.turns)}"
                    ),
                },
            ],
            max_tokens=MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "scorecard", "schema": _SCHEMA, "strict": True},
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("could not build the scorecard")
        return _fallback(competency_names, "Scoring was unavailable for this session.")

    competencies = [
        CompetencyResult(
            name=str(c.get("name", "")).strip(),
            status=(
                str(c.get("status", "")).strip()
                if str(c.get("status", "")).strip() in _STATUSES
                else "not_covered"
            ),
            evidence=str(c.get("evidence", "")).strip(),
        )
        for c in payload.get("competencies", [])
        if str(c.get("name", "")).strip()
    ]
    verdict = str(payload.get("verdict", "")).strip()
    if verdict not in _VERDICTS:
        verdict = "borderline"

    try:
        score = round(max(1.0, min(10.0, float(payload.get("score", 5)))), 1)
    except (TypeError, ValueError):
        score = 5.0

    return Scorecard(
        verdict=verdict,
        score=score,
        headline=str(payload.get("headline", "")).strip() or "Interview complete.",
        strengths=[str(s).strip() for s in payload.get("strengths", []) if str(s).strip()],
        gaps=[str(g).strip() for g in payload.get("gaps", []) if str(g).strip()],
        notes=[str(n).strip() for n in payload.get("notes", []) if str(n).strip()],
        competencies=competencies,
        sources=brief.sources if brief else [],
        grounded=bool(brief.grounded) if brief else False,
    )
