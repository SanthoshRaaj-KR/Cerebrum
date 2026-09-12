"""Drives one interview session.

There is no plan and no clock. Before the interview starts, research.py
gathers a RoleBrief - what freshers for this role are really asked and
really expected to know. Every turn after that, the model sees the whole
conversation so far, the role brief, a running coverage note, and a
private note on how the last answer went, and is explicitly instructed to
react to what the candidate just said before it does anything else. Where
it goes next - which competency, how hard - is a judgment call made fresh
each turn, the way an actual interviewer makes it, not a lookup into a
pre-written list.

The interview ends when the coverage ledger says every competency has a
read (see coverage.py), with a min/max question band as the floor and
ceiling. Asking and reading the last answer are deliberately separate
calls - see evaluator.py. Each answer is also judged more deeply in a
background task as the interview runs, and the report is written from
those at the end - see scorecard.RunningScore. Nothing evaluative is ever
shown to the candidate mid-interview.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from interview_agent import (
    agent,
    evaluator,
    gateway,
    prompts,
    questionnaire,
    research,
    resume,
)
from interview_agent.config import settings
from interview_agent.context import CandidateContext
from interview_agent.coverage import CoverageLedger
from interview_agent.evaluator import AnswerNote, CompetencyBar, Rubric
from interview_agent.prompts import Mode
from interview_agent.research import RoleBrief
from interview_agent.resume import ResumeDigest
from interview_agent.scorecard import RunningScore

@dataclass
class Turn:
    """One question and, once answered, the answer. The interviewer's
    private read (AnswerNote) travels with the turn but is never rendered
    to the candidate - see to_dict()."""

    question: str
    answer: str | None = None
    skipped: bool = False
    note: AnswerNote | None = None

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "answer": self.answer,
            "skipped": self.skipped,
        }


@dataclass
class InterviewSession:
    mode_key: str
    candidate: CandidateContext = field(default_factory=CandidateContext)
    mode: Mode = field(init=False)
    brief: RoleBrief | None = None
    resume_digest: ResumeDigest | None = None
    turns: list[Turn] = field(default_factory=list)
    ledger: CoverageLedger = field(default_factory=CoverageLedger)
    # Per-answer judgements accumulated in the background while the
    # interview runs; the scorecard is written from them at the end.
    running_score: RunningScore = field(default_factory=RunningScore)
    finished: bool = False
    _final_turn_sent: bool = False
    # Per-session ceiling on questions; None means use settings.max_questions.
    # Only the quality-check harness sets it, to keep scripted runs short.
    _max_questions: int | None = None

    def __post_init__(self) -> None:
        self.mode = prompts.get(self.mode_key)
        # The round carries the role; nobody types it. Only fill in what the
        # caller left blank, so the résumé round can still pass a role the
        # candidate named for themselves.
        if not self.candidate.role:
            self.candidate.role = self.mode.default_role
        if not self.candidate.level:
            self.candidate.level = "Fresher" if settings.fresher else "Experienced"

    # -- setup --------------------------------------------------------------

    async def start(self, max_questions: int | None = None) -> Turn:
        if self.mode_key == gateway.MODE_KEY:
            # The résumé round has no external syllabus - its brief is built
            # FROM the résumé, so the digest has to land first.
            self.resume_digest = await resume.digest(self.candidate.resume)
            self.brief = await gateway.build_brief(
                self.candidate, self.resume_digest, self.mode
            )
        else:
            # Independent prep work, both non-raising - run them together so
            # a session start is one round-trip's wait, not two.
            self.brief, self.resume_digest = await asyncio.gather(
                research.build_brief(self.candidate, self.mode),
                resume.digest(self.candidate.resume),
            )
        self.turns = []
        self.ledger = CoverageLedger()
        self.running_score = RunningScore()
        self.finished = False
        self._final_turn_sent = False
        self._max_questions = max_questions
        return await self._ask(opening=True)

    # -- state ----------------------------------------------------------

    @property
    def question_cap(self) -> int:
        """The most questions this interview will ask before wrapping up,
        no matter how coverage is going."""
        return self._max_questions or settings.max_questions

    @property
    def question_agent(self):
        """Which agent writes this mode's questions. The résumé round runs
        off the candidate's own work (gateway.py); everything else runs off
        a researched role brief. Same next_question(ctx) signature, so
        neither the coordinator nor the main agent has to care which."""
        return gateway if self.mode_key == gateway.MODE_KEY else questionnaire

    @property
    def closing(self) -> bool:
        """True once the wrap-up question has been sent - the interview
        ends on the next answer."""
        return self._final_turn_sent

    def _competency_names(self) -> list[str]:
        return [c.name for c in self.brief.competencies] if self.brief else []

    def _rubric(self) -> Rubric:
        """What the evaluator judges this session's answers against. Built
        here rather than in evaluator.py so that module stays independent of
        where the competencies came from - a role search today, the résumé
        itself for résumé mode."""
        if not self.brief:
            return Rubric()
        return Rubric(
            competencies=[
                CompetencyBar(name=c.name, fresher_bar=c.fresher_bar)
                for c in self.brief.competencies
            ],
            red_flags=list(self.brief.red_flags),
        )

    def _history(self) -> list[dict[str, str]]:
        """The conversation so far, trimmed. Private reads are deliberately
        left out - the interviewer must not see its own scoring."""
        msgs: list[dict[str, str]] = []
        for t in self.turns:
            msgs.append({"role": "assistant", "content": t.question})
            if t.answer is not None:
                msgs.append(
                    {"role": "user", "content": t.answer or "(skipped this question)"}
                )
        keep = max(4, settings.remember_turns * 2)
        return msgs[-keep:]

    def _question_context(self, stage: str) -> questionnaire.QuestionContext:
        """Everything the questionnaire agent needs for one question."""
        return questionnaire.QuestionContext(
            mode_key=self.mode_key,
            candidate=self.candidate,
            brief=self.brief,
            resume_digest=self.resume_digest,
            coverage_note=self.ledger.render(self._competency_names()),
            history=self._history(),
            private_note=self._last_answer_note(),
            stage=stage,
        )

    def _closing_now(self) -> bool:
        """Whether this next question should be the wrap-up one: we're a
        question away from the cap, or coverage is complete and we've asked
        a fair number of questions already."""
        if len(self.turns) >= self.question_cap - 1:
            return True
        names = self._competency_names()
        return (
            bool(names)
            and len(self.turns) >= settings.min_questions
            and not self.ledger.open_ground(names)
        )

    def _last_answer_note(self) -> str:
        """A private read on how the last answer went, for the
        interviewer's own use - never voiced to the candidate."""
        answered = [t for t in self.turns if t.note is not None]
        if not answered:
            return ""
        last = answered[-1]
        note = last.note
        if note is None:
            return ""

        if last.skipped:
            return (
                "PRIVATE NOTE - they skipped that question entirely. Do not "
                "re-ask it and do not ask it in other words. Move to new "
                "ground, and consider dropping the difficulty a little."
            )

        if note.topic_exhausted:
            return (
                "PRIVATE NOTE - never say this out loud. That is at least "
                "two weak answers in a row on the same ground. You have "
                "found the edge of what they know here, which is all you "
                "needed. Do NOT ask about it again in any form. Move to "
                "different ground, and make it easier."
            )

        stance = {
            "strong": (
                "That answer held up. Either push it one level harder or "
                "move to ground you have less on."
            ),
            "thin": (
                "That answer was thin. Pull the thread rather than "
                "starting a new topic."
            ),
            "wrong": (
                "That answer contained something wrong. Do NOT move on as "
                "if it were fine - challenge it directly and give them the "
                "chance to correct it. Push once only: if this is already "
                "your second attempt at this ground, move on instead."
            ),
            "dodged": (
                "They answered something other than what you asked. Say "
                "so plainly and put the original question back to them, "
                "more concretely."
            ),
            "dont_know": (
                "They plainly don't know, and said so honestly. Do not "
                "grind them down and do not ask the same thing again in "
                "other words. That honesty is worth more than a bluff - "
                "treat it that way. Drop to something adjacent and easier."
            ),
        }.get(note.read, "")

        thread = f" Worth pulling on: {note.thread}." if note.thread else ""
        return (
            "PRIVATE NOTE on their last answer - never say any of this out "
            f"loud, just act on it. {stance}{thread}"
        )

    # -- the interview ----------------------------------------------------

    async def _ask(self, opening: bool) -> Turn:
        if opening:
            stage = "opening"
        elif self._closing_now():
            self._final_turn_sent = True
            stage = "closing"
        else:
            stage = "next"

        question = await self.question_agent.next_question(self._question_context(stage))
        turn = Turn(question=question.text)
        self.turns.append(turn)
        return turn

    async def answer(self, text: str, skipped: bool = False) -> Turn | None:
        """Record the answer, take a private read on it, and ask the next
        question - or None if the interview just ended.

        No score is returned and none reaches the candidate. A deeper
        judgement of this answer is kicked off in the background here (see
        scorecard.RunningScore) but it is never awaited on this path and
        never surfaces until the report.
        """
        if self.finished:
            raise RuntimeError("this interview has already finished")
        if not self.turns:
            raise RuntimeError("the interview has not started")

        current = self.turns[-1]
        if current.answer is not None:
            raise RuntimeError("that question has already been answered")

        current.answer = "" if skipped else text.strip()
        current.skipped = skipped or not current.answer

        prev_note = self.turns[-2].note if len(self.turns) > 1 else None
        prior_read = prev_note.read if prev_note is not None else ""

        # Either the LLM main agent drives this turn (it calls the evaluator
        # and picks the move), or the deterministic path does. The
        # invariants below run identically for both - the agent is not
        # trusted with the ledger, the cap, or the background scorer.
        # Once the wrap-up question has gone out, this answer is the last
        # one: there is no next move to decide, so don't run the agent loop
        # to write a question the guard below would only throw away. The
        # read itself still has to happen - the ledger and the scorecard
        # both want it - so it falls through to the direct call. The
        # deterministic path has always short-circuited here; this is the
        # agent path matching it.
        decision = None
        agent_closing = False
        if settings.coordinator == "agent" and not self._final_turn_sent:
            agent_closing = self._closing_now()
            decision = await agent.run_turn(self, current, agent_closing)
            current.note = decision.note

        if current.note is None:
            current.note = await evaluator.read(
                current.question,
                current.answer,
                current.skipped,
                self._rubric(),
                prior_read,
            )
        # evaluator.read's "two weak in a row" guard keys off prior_read, which
        # is the previous answer whatever its topic. Only let that retire a
        # competency in the ledger when the previous answer was on the SAME
        # focus - otherwise a rough patch across different areas would settle
        # competencies that were each only asked once.
        same_focus = bool(
            current.note.focus
            and prev_note is not None
            and prev_note.focus == current.note.focus
        )
        self.ledger.record(
            current.note.evidenced,
            evaluator.strength_of(current.note.read),
            focus=current.note.focus,
            exhausted=current.note.topic_exhausted and same_focus,
        )

        # Fire-and-forget: the deep judgement of this answer runs while the
        # candidate is already reading the next question. Never awaited here
        # - they must not wait on a verdict they aren't allowed to see.
        self.running_score.schedule(
            index=len(self.turns),
            question=current.question,
            answer=current.answer or "",
            skipped=current.skipped,
            note=current.note,
            rubric=self._rubric(),
        )

        # The cap and the wrap-up turn are code's call, not the agent's: if
        # it produced a question past the ceiling, that question is dropped.
        if self._final_turn_sent or len(self.turns) >= self.question_cap:
            self.finished = True
            return None

        if decision is not None and not decision.fell_back:
            # end_interview is only honoured once there's been a real
            # interview - the agent doesn't get to bail out at question two.
            if decision.ended and len(self.turns) >= settings.min_questions:
                self.finished = True
                return None
            if decision.question:
                # The agent was told this was the wrap-up turn, so the
                # question it just wrote is the last one. Mark that only now,
                # as the question actually goes out - marking it before the
                # guard above would make the guard swallow the wrap-up and
                # end the interview a question early, with no close at all.
                if agent_closing:
                    self._final_turn_sent = True
                turn = Turn(question=decision.question)
                self.turns.append(turn)
                return turn

        return await self._ask(opening=False)
