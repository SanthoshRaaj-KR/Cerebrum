"""Drive a whole interview through both coordinators with every model call
stubbed, and assert the things that must hold whichever one is driving.

    python tools/coordinator_check.py

Needs no API keys and no running bridge - it replaces the LLM client, the
evaluator, the questionnaire and the research call with fakes, so what it
exercises is purely the control flow in interviewer.py and agent.py. That
is the half of this system that `tools/quality_check.py` cannot see:
quality_check reads transcripts by eye to judge *what* was asked, and it
needs live models to do it. This one checks the structural invariants -
the things that are meant to be true by construction rather than by the
model behaving well.

What it asserts, for `code` and `agent` alike:

1. The interview delivers exactly as many questions as the cap allows.
   The agent path used to lose the last one: it marked the wrap-up as sent
   at the moment the agent *wrote* it, and the guard that ends the
   interview then fired on that same flag and discarded the question. The
   interview ended a turn early with no close at all.
2. A wrap-up turn actually reaches the candidate.
3. The questionnaire is steered by the read on the answer it is reacting
   to, not the one before it. The agent held the fresh AnswerNote locally
   until run_turn returned, while the questionnaire reads its private note
   back off session.turns - so every question was written against the
   previous answer's read.
4. No question is written and then thrown away. Writing one costs a model
   call; the deterministic path never does it, so the agent path
   shouldn't either.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from interview_agent import (  # noqa: E402
    agent,
    evaluator,
    interviewer,
    questionnaire,
    research,
    resume,
)
from interview_agent.config import settings  # noqa: E402
from interview_agent.context import CandidateContext  # noqa: E402
from interview_agent.evaluator import AnswerNote  # noqa: E402
from interview_agent.research import Competency, RoleBrief  # noqa: E402
from interview_agent.scorecard import RunningScore  # noqa: E402

CAP = 5
MIN_QUESTIONS = 2

BRIEF = RoleBrief(
    competencies=[
        Competency(
            name="Databases",
            why_it_matters="most of the job",
            fresher_bar="knows what an index does",
        ),
        Competency(
            name="HTTP",
            why_it_matters="every service speaks it",
            fresher_bar="knows the verbs",
        ),
    ],
    red_flags=["stores passwords in plaintext"],
    grounded=True,
)

# A deliberately mixed run: strong, then a wrong claim, then thin. Enough
# range that the ledger and the exhaustion guard both get exercised.
READS = ["strong", "wrong", "thin", "strong", "thin"]


class Run:
    """One scripted interview, and what the machinery did during it."""

    def __init__(self, coordinator: str) -> None:
        self.coordinator = coordinator
        self.questions_written: list[str] = []
        self.notes_seen: list[tuple[int, str]] = []
        self.session: interviewer.InterviewSession | None = None


def _install_fakes(run: Run) -> None:
    async def fake_read(question, answer, skipped, rubric, prior_read):
        idx = len(run.questions_written)
        return AnswerNote(
            read=READS[min(idx - 1, len(READS) - 1)],
            evidenced=[],
            focus="Databases",
            gap=f"gap-from-answer-{idx}",
            # The marker the staleness check keys off: it names the answer
            # this read was taken on.
            thread=f"thread-from-answer-{idx}",
        )

    async def fake_next_question(ctx):
        idx = len(run.questions_written)
        run.notes_seen.append((idx, ctx.private_note or ""))
        text = f"Q{idx + 1} [stage={ctx.stage} intent={ctx.intent or '-'}]"
        run.questions_written.append(text)
        return questionnaire.Question(text=text)

    async def fake_build_brief(candidate, mode):
        return BRIEF

    async def fake_digest(text):
        return None

    evaluator.read = fake_read
    agent.evaluator = evaluator
    agent.client = _fake_client
    questionnaire.next_question = fake_next_question
    research.build_brief = fake_build_brief
    resume.digest = fake_digest
    RunningScore.schedule = lambda self, **kw: None


class _FakeCompletions:
    """The main agent's model. Answers the forced first call with
    evaluate_answer, then commits to a question."""

    async def create(self, **kw):
        forced = isinstance(kw.get("tool_choice"), dict)
        name, args = (
            ("evaluate_answer", {})
            if forced
            else ("next_question", {"intent": "dig", "target": "Databases", "why": "s"})
        )
        call = types.SimpleNamespace(
            id=f"call-{name}",
            type="function",
            function=types.SimpleNamespace(name=name, arguments=json.dumps(args)),
        )
        message = types.SimpleNamespace(content="", tool_calls=[call])
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _fake_client():
    return types.SimpleNamespace(
        chat=types.SimpleNamespace(completions=_FakeCompletions())
    )


async def drive(coordinator: str) -> Run:
    run = Run(coordinator)
    settings.raw.setdefault("interviewer", {})["coordinator"] = coordinator
    settings.raw.setdefault("interview", {})["min_questions"] = MIN_QUESTIONS
    _install_fakes(run)

    session = interviewer.InterviewSession(
        mode_key="sde_backend",
        candidate=CandidateContext(role="Backend Engineer", level="Fresher", resume="x"),
    )
    run.session = session
    await session.start(max_questions=CAP)
    while not session.finished:
        await session.answer(f"an answer to {session.turns[-1].question}")
    return run


def check(run: Run) -> list[str]:
    """Returns a list of failures - empty means this coordinator is sound."""
    assert run.session is not None
    failures: list[str] = []
    turns = run.session.turns

    if len(turns) != CAP:
        failures.append(
            f"delivered {len(turns)} questions, expected {CAP} "
            "(the wrap-up turn is most likely being discarded)"
        )

    if not any("stage=closing" in t.question for t in turns):
        failures.append("no wrap-up turn ever reached the candidate")

    discarded = len(run.questions_written) - len(turns)
    if discarded:
        failures.append(
            f"{discarded} question(s) written by a model call and then thrown away"
        )

    for idx, note in run.notes_seen:
        if idx < 1 or not note:
            continue
        expected = f"thread-from-answer-{idx}"
        if expected not in note:
            failures.append(
                f"question {idx + 1} was written against a stale private note "
                f"(expected the read on answer {idx})"
            )

    return failures


async def main() -> int:
    print("\nCerebrum - coordinator invariants")
    print("=" * 62)

    failed = False
    for coordinator in ("code", "agent"):
        run = await drive(coordinator)
        failures = check(run)
        assert run.session is not None
        print(f"\ncoordinator: {coordinator}")
        print(f"  {len(run.session.turns)}/{CAP} questions delivered")
        for t in run.session.turns:
            print(f"    {t.question}")
        if failures:
            failed = True
            for f in failures:
                print(f"  [FAIL] {f}")
        else:
            print("  [ ok ] cap honoured, wrap-up delivered, notes current, nothing wasted")

    print("\n" + "=" * 62)
    if failed:
        print("Coordinator invariants are broken - see the failures above.\n")
        return 1
    print("Both coordinators hold their invariants.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
