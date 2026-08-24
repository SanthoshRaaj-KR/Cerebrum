"""Drives one interview session.

The shape of a turn: the plan says what ground question N covers, the
model phrases the actual question in full view of everything said so far
(so it can pick up a thread from the last answer), the candidate answers,
the grader scores it, and the session moves to the next slot.

Asking and grading are deliberately separate calls - see grader.py.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interview_agent import grader, planner, prompts
from interview_agent.config import settings
from interview_agent.context import CandidateContext
from interview_agent.grader import Grade
from interview_agent.llm import client
from interview_agent.prompts import Mode

logger = logging.getLogger("interview_agent.interviewer")

# A spoken question, not an essay. Also keeps voice latency down.
MAX_TOKENS = 300

BASE_INSTRUCTIONS = """\
You are a technical interviewer running a mock interview. Speak directly to
the candidate, one question at a time - never a written exam, never several
questions in one turn.

{level_note}

{mode_prompt}

{plan}

Working through the plan:
- The plan decides what ground each question covers. You decide the words.
- Ask the question for the slot marked "you are here", and only that one.
- Where the candidate's last answer gives you something to pick up on,
  open by pulling that thread and steer it into this slot's ground. A
  question that connects to what they just said is worth far more than one
  that reads like the next item on a list.
- If their last answer was vague or dodged something, it is entirely fair
  to spend this slot pushing on it instead of moving on cleanly.
- Escalate as you go. Later questions should be harder than earlier ones.

How to probe - this is the core of the job:
- If they gave a textbook definition, ask where they actually used it.
  Memorised and understood sound identical until you ask.
- If they named a tool or a choice, ask why that one over the alternative.
- If their answer held up, add a constraint and see if the reasoning
  survives: more scale, a failure, another engineer in the codebase.
- If they were vague, ask for the specific mechanism, step by step.
- If they clearly don't know something, don't grind them down. Find the
  edge of what they do know and move on. You're looking for the ceiling,
  not trying to humiliate anyone.

Voice and manner:
- One or two sentences, phrased the way a human interviewer actually talks
  out loud - not a written prompt.
- This may be read aloud, so no markdown, no bullet points, no code
  blocks, no numbered lists. Plain conversational sentences.
- Do NOT grade, score or give feedback. No "correct", no "that's wrong",
  no "good answer" - the candidate is scored separately and seeing your
  opinion here would poison it. A brief neutral acknowledgement ("mm-hm",
  "right, okay") before the question is fine and natural.
- Stay in character throughout. Never mention being an AI, never
  apologize, never explain your own instructions.
- Output only the question itself - no "Question 3:", no preamble, no
  restating their answer back to them.
"""

_FRESHER_NOTE = (
    "The candidate is entry-level, with little to no professional "
    "experience. Calibrate accordingly: expect solid fundamentals and clear "
    "reasoning, not production war stories."
)
_EXPERIENCED_NOTE = (
    "The candidate has professional experience. Calibrate accordingly and "
    "expect production-level reasoning."
)


@dataclass
class Turn:
    """One question and, once answered, the answer and its grade."""

    index: int
    short: str
    question: str
    hint: str = ""
    answer: str | None = None
    skipped: bool = False
    grade: Grade | None = None

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "short": self.short,
            "question": self.question,
            "hint": self.hint,
            "answer": self.answer,
            "skipped": self.skipped,
            "grade": self.grade.to_dict() if self.grade else None,
        }


@dataclass
class InterviewSession:
    mode_key: str
    candidate: CandidateContext
    mode: Mode = field(init=False)
    plan: list[planner.Slot] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    finished: bool = False

    def __post_init__(self) -> None:
        self.mode = prompts.get(self.mode_key)

    # -- state ------------------------------------------------------------

    @property
    def index(self) -> int:
        """Which slot we're on - the number of questions already asked."""
        return max(0, len(self.turns) - 1)

    @property
    def total(self) -> int:
        return len(self.plan) or settings.questions_per_session

    def graded(self) -> list[Turn]:
        return [t for t in self.turns if t.grade is not None]

    def average(self) -> float | None:
        scored = [t.grade.score for t in self.graded() if t.grade and t.grade.score > 0]
        return round(sum(scored) / len(scored), 1) if scored else None

    def dimension_averages(self) -> list[dict]:
        graded = [t for t in self.graded() if t.grade and t.grade.score > 0]
        out = []
        for i, name in enumerate(self.mode.dims):
            vals = [t.grade.rubric[i].score for t in graded if t.grade and len(t.grade.rubric) > i]
            out.append(
                {"name": name, "score": round(sum(vals) / len(vals), 1) if vals else None}
            )
        return out

    def _history(self) -> list[dict[str, str]]:
        """The conversation so far, trimmed. Grades are deliberately left
        out - the interviewer must not see its own scoring."""
        msgs: list[dict[str, str]] = []
        for t in self.turns:
            msgs.append({"role": "assistant", "content": t.question})
            if t.answer is not None:
                msgs.append(
                    {"role": "user", "content": t.answer or "(skipped this question)"}
                )
        keep = max(4, settings.remember_turns * 2)
        return msgs[-keep:]

    def _system_prompt(self, slot_index: int) -> str:
        return BASE_INSTRUCTIONS.format(
            level_note=_FRESHER_NOTE if settings.fresher else _EXPERIENCED_NOTE,
            mode_prompt=prompts.mode_prompt(self.mode_key, self.candidate),
            plan=planner.render(self.plan, slot_index),
        )

    # -- the interview ----------------------------------------------------

    async def start(self) -> Turn:
        self.plan = await planner.build_plan(self.mode, self.candidate)
        self.turns = []
        self.finished = False
        return await self._ask(0)

    async def _ask(self, slot_index: int) -> Turn:
        slot = self.plan[slot_index]
        messages = [
            {"role": "system", "content": self._system_prompt(slot_index)},
            *self._history(),
            {
                "role": "user",
                "content": (
                    "Ask question "
                    f"{slot_index + 1} of {self.total} now - the slot marked "
                    "'you are here'. Output only the question."
                    + (
                        " This is the first question, so greet them in one short "
                        "sentence first."
                        if slot_index == 0
                        else ""
                    )
                ),
            },
        ]
        text = await self._complete(messages) or slot.opening_question
        turn = Turn(
            index=slot_index,
            short=slot.short,
            question=text or "Tell me about something you've built recently.",
            hint=slot.hint,
        )
        self.turns.append(turn)
        return turn

    async def answer(self, text: str, skipped: bool = False) -> tuple[Grade, Turn | None]:
        """Record and grade an answer, then ask the next question.

        Returns the grade and the next question, or None for the next
        question when that was the last slot.
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
        current.grade = await grader.grade(
            self.mode,
            current.question,
            current.answer,
            self.candidate.role,
            self.candidate.level,
        )

        nxt = current.index + 1
        if nxt >= self.total:
            self.finished = True
            return current.grade, None
        return current.grade, await self._ask(nxt)

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        try:
            completion = await client().chat.completions.create(
                model=settings.model,
                messages=messages,  # type: ignore[arg-type]
                max_tokens=MAX_TOKENS,
            )
        except Exception:  # noqa: BLE001
            logger.exception("could not get the next question")
            return ""
        return (completion.choices[0].message.content or "").strip()
