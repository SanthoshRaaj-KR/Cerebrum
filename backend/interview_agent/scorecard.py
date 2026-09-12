"""The scorecard, accumulated during the interview and written at the end.

Nothing is scored while the interview is running *to the candidate* - no
score, no rubric, no "missing" line ever reaches them mid-session, because
no real interviewer grades you to your face. But the interviewer is
absolutely forming a view as it goes, and so does this: after each answer
a background task judges that one answer carefully (RunningScore.update),
off the critical path, while the candidate is already reading the next
question. At the end, finalize() writes the report from that accumulated
per-answer analysis plus the whole transcript.

Splitting it this way buys two things. Each answer gets real attention
instead of a skim during one big end-of-interview pass; and the expensive
judging happens in parallel with the conversation rather than after it.
The per-answer pass runs on settings.scorer_model - catching a confidently
wrong technical claim is the hardest call in the system and it is the one
place a stronger model clearly pays for itself.

The calibration below exists because a fresher's scorecard has to answer
one honest question - "would a company hire this person as a fresher" -
not "would a senior engineer be impressed by them". Getting that wrong in
either direction wastes the practice: too strict and a genuinely
interview-ready fresher walks away thinking they're not; too soft and
someone with real gaps walks away thinking they're fine.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field

from interview_agent.config import settings
from interview_agent.evaluator import AnswerNote, Rubric
from interview_agent.llm import client

logger = logging.getLogger("interview_agent.scorecard")

MAX_TOKENS = 1800
VERDICT_MAX_TOKENS = 400

_STATUSES = ("solid", "developing", "not_shown", "not_covered")
_VERDICTS = ("strong_yes", "yes", "borderline", "not_yet")
_DEPTHS = ("solid", "partial", "absent")


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


# -- per-answer verdict (the background half) -------------------------------


@dataclass
class AnswerVerdict:
    """The background scorer's read on one answer. Deeper than the fast
    on-path read in evaluator.py, because this one isn't holding up the
    next question."""

    index: int
    question: str
    competency: str = ""
    correct: bool = False
    depth: str = "absent"
    evidence: str = ""
    gap: str = ""
    # The two fields the candidate actually learns from. `gap` names what
    # was missing; these say what to have said instead and what to do about
    # it next time. Kept separate because a report that only names gaps
    # tells someone they were wrong without telling them anything.
    better: str = ""
    improve: str = ""
    # What they actually said, carried so the report can show the answer
    # next to the judgement of it rather than making them scroll.
    answer: str = ""
    skipped: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        head = f"Q{self.index}"
        if self.competency:
            head += f" [{self.competency}]"
        head += f"  correct={'yes' if self.correct else 'no'}  depth={self.depth}"
        lines = [head]
        if self.evidence:
            lines.append(f"    showed: {self.evidence}")
        if self.gap:
            lines.append(f"    gap:    {self.gap}")
        return "\n".join(lines)


_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "competency": {"type": "string"},
        "correct": {"type": "boolean"},
        "depth": {"type": "string", "enum": list(_DEPTHS)},
        "evidence": {"type": "string"},
        "gap": {"type": "string"},
        "better": {"type": "string"},
        "improve": {"type": "string"},
    },
    "required": [
        "competency",
        "correct",
        "depth",
        "evidence",
        "gap",
        "better",
        "improve",
    ],
    "additionalProperties": False,
}

_VERDICT_PROMPT = """\
Judge ONE answer from a mock interview with an entry-level candidate. You
are not talking to them - this is analysis that will be folded into their
scorecard later.

{rubric}

Work out the technical content first, before you judge anything else:
what would a correct answer contain, what did they actually say, and where
is the difference. Fluent, confident and on-topic is not the same as
right. If the claim is wrong, it is wrong no matter how well it was put.

- competency: which tracked competency this answer bears on, by name
  exactly as listed above. Empty string if it maps to none of them.
- correct: was the technical content of the answer right? An answer that
  is vague but not incorrect is still correct=true; one containing a
  confident false claim is correct=false.
- depth: solid (a fresher-level answer with real reasoning behind it) /
  partial (right shape, shallow, or only half the picture) / absent (they
  didn't have it, skipped, dodged, or got it wrong).
- evidence: one short line naming what they actually demonstrated. Empty
  string unless correct is true - a wrong answer demonstrates nothing.
- gap: one short line naming what a good fresher answer would have had
  that this didn't, or what specifically was wrong and what is actually
  true. Empty string only when the answer fully held up.
- better: two or three sentences sketching what a strong fresher answer to
  THIS question sounds like. Not a model essay and not everything that
  could be said - the version a good new graduate would actually give out
  loud, concrete enough that they can hear the difference from their own.
  When their answer already held up, say what would have taken it one
  level further instead.
- improve: one concrete thing to do differently next time, addressed to
  them as "you". Actionable, not a platitude: "say which index you would
  add and on which column" rather than "study databases more". When the
  answer was strong, make this the harder thing to reach for rather than
  inventing a fault.

Calibrate to a FRESHER. Naming the concept, giving one worked example and
reasoning about a trade-off out loud is a solid entry-level answer. An
honest "I don't know" is depth=absent but is NOT a wrong claim - never
record it as correct=false with an invented gap; its gap is simply the
topic they didn't know.
"""


async def _judge_answer(
    index: int,
    question: str,
    answer: str,
    skipped: bool,
    note: AnswerNote,
    rubric: Rubric,
) -> AnswerVerdict:
    """Never raises - a failed verdict just means this answer contributes
    nothing extra to the final scorecard, which still sees the transcript."""
    if skipped or not (answer or "").strip():
        return AnswerVerdict(
            index=index,
            question=question,
            competency=note.focus,
            correct=False,
            depth="absent",
            gap="skipped this question",
            improve=(
                "Say what you do know and where you would start, rather than "
                "passing - a partial answer is always worth more than silence."
            ),
            answer="",
            skipped=True,
        )

    try:
        completion = await client().chat.completions.create(
            model=settings.scorer_model,
            messages=[
                {"role": "system", "content": _VERDICT_PROMPT.format(rubric=rubric.render())},
                {
                    "role": "user",
                    "content": f"QUESTION:\n{question}\n\nANSWER:\n{answer}",
                },
            ],
            max_tokens=VERDICT_MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "answer_verdict",
                    "schema": _VERDICT_SCHEMA,
                    "strict": True,
                },
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("could not judge answer %d in the background", index)
        return AnswerVerdict(
            index=index,
            question=question,
            competency=note.focus,
            answer=answer,
        )

    competency = str(payload.get("competency", "")).strip()
    if competency not in rubric.names:
        competency = note.focus
    depth = str(payload.get("depth", "")).strip()
    if depth not in _DEPTHS:
        depth = "partial"

    return AnswerVerdict(
        index=index,
        question=question,
        competency=competency,
        correct=bool(payload.get("correct", False)),
        depth=depth,
        evidence=str(payload.get("evidence", "")).strip(),
        gap=str(payload.get("gap", "")).strip(),
        better=str(payload.get("better", "")).strip(),
        improve=str(payload.get("improve", "")).strip(),
        answer=answer,
        skipped=False,
    )


class RunningScore:
    """Per-answer verdicts accumulated in the background during the
    interview, then written up at the end.

    schedule() is fire-and-forget on purpose: it must never make the
    candidate wait for a judgement they are not allowed to see. finalize()
    waits for whatever is still in flight before writing the report.
    """

    def __init__(self) -> None:
        self.verdicts: list[AnswerVerdict] = []
        # Strong refs: a bare create_task() can be garbage collected
        # mid-flight, which silently drops the verdict.
        self._tasks: set[asyncio.Task] = set()

    def schedule(
        self,
        index: int,
        question: str,
        answer: str,
        skipped: bool,
        note: AnswerNote,
        rubric: Rubric,
    ) -> None:
        async def _run() -> None:
            verdict = await _judge_answer(index, question, answer, skipped, note, rubric)
            self.verdicts.append(verdict)

        task = asyncio.create_task(_run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def await_pending(self) -> None:
        if not self._tasks:
            return
        # return_exceptions: a background judgement that blew up must not
        # take the report down with it.
        await asyncio.gather(*list(self._tasks), return_exceptions=True)

    def render(self) -> str:
        if not self.verdicts:
            return ""
        ordered = sorted(self.verdicts, key=lambda v: v.index)
        return "\n".join(v.render() for v in ordered)

    async def finalize(self, session) -> Scorecard:
        await self.await_pending()
        return await _write_scorecard(session, self.render())


# -- the final write-up -----------------------------------------------------


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

Before calling anything a strength, check whether the specific technical
claim in it was actually correct - fluent, confident, and on-topic is not
the same as right. Read every answer for its content, not its topic:
"they talked about indexing" is not evidence indexing was understood, it
is just evidence indexing came up. If what they actually said about it was
wrong, that is a gap, full stop - it must not be softened into a strength
anywhere in the scorecard, including the per-competency evidence field.

Worked example: a candidate says "indexes make everything faster, there's
no real downside, that's why databases have them." That claim is WRONG -
indexes cost extra work on every write and disk space, which is exactly
why they aren't put on every column. The correct write-up: this goes in
gaps ("you said indexes have no downside - they slow down writes and cost
storage, which is why you index selectively"), the Database competency is
not_shown or developing at best, and nothing about this answer is praised
as "familiarity with indexing" or similar - knowing the word is not the
same as understanding the trade-off, and crediting it as if it were is
exactly the mistake this paragraph exists to prevent. Structural check
before you finalize: if a claim is named in gaps, no strengths bullet may
describe that same claim or topic in softer language - a wrong answer
gets exactly one appearance in the scorecard, in gaps, not two.

For each competency listed below, decide:
- solid: they showed real evidence of it, correct and with some depth.
- developing: touched on it, but shallow, partial, or shaky.
- not_shown: it came up and they didn't have it, or answered wrong.
- not_covered: it never came up in this conversation - the interview
  simply didn't reach it. Do not penalize this; it is a fact about what
  there was room to ask, not about them.

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

_ANALYSIS_HEADER = """\
PER-ANSWER ANALYSIS - each answer was judged on its own, during the
interview, with more care than one pass over a whole transcript allows.
Trust it on whether a specific technical claim was correct or wrong. Use
the transcript below it for the things it cannot see: patterns across
several answers, how they handled being pushed, whether they corrected
themselves.
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


async def _write_scorecard(session, analysis: str) -> Scorecard:
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
    analysis_block = f"{_ANALYSIS_HEADER}\n{analysis}\n\n" if analysis else ""

    try:
        completion = await client().chat.completions.create(
            model=settings.scorer_model,
            messages=[
                {"role": "system", "content": _PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Interview mode: {session.mode.name}\n"
                        f"Target role: {session.candidate.role or 'unspecified'}\n"
                        f"Level: {session.candidate.level or 'fresher'}\n\n"
                        f"COMPETENCIES TRACKED FOR THIS ROLE:\n{competency_block}\n\n"
                        f"{analysis_block}"
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
