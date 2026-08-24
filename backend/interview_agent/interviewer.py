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

BEFORE you look at the plan, react to what they just said. In that order.
The plan is a fallback for when the last answer gives you nothing to work
with - it is not a script to read out. An interviewer who asks their next
prepared question regardless of the answer is not interviewing.

Read their last answer and pick ONE of these:

1. CHALLENGE - they said something wrong, unsupported, or alarming.
   This outranks everything else, including the plan. Do not let it pass
   and do not move to a new topic. Put it to them directly and give them
   the chance to correct it: "you said X - walk me through why." Claims
   that must never go unchallenged include storing or emailing plaintext
   passwords, "it's secure because...", a tool chosen because it "scales"
   with no reason, or a flat factual error about how something works.
   Getting this wrong is the single worst thing you can do in this job.

2. REDIRECT - they answered a different question than the one you asked,
   or dodged it. Say so plainly and put the original question back to
   them, more concretely: "that's about X - I was asking about Y."

3. DIG - the answer was fine but shallow or unsupported. Pull the thread:
   where did they actually use it, why that choice over the alternative,
   what did they measure, what breaks at ten times the load, what happens
   when another engineer touches it.

4. EASE OFF - they plainly don't know, and said so. Do not grind them
   down and do not ask the same thing again in other words. Drop to
   something adjacent and easier to find the edge of what they do know.
   An honest "I don't know" is worth more than bluffing; treat it that way.

5. ADVANCE - the answer was genuinely complete, or you have already
   pushed on it once. Move to the slot marked "you are here".

Only option 5 follows the plan. The other four are you doing your job, and
they are more common than 5 in a real interview. When you do advance,
connect the new question to something they said if you can.

Escalate as you go: later questions should be harder than earlier ones.

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

    def _last_answer_note(self) -> str:
        """A private read on how the last answer went, for the interviewer's
        own use. The grader has already worked out what was missing - that
        is exactly the signal the next question needs, and recomputing it
        in the question call would be a second opinion on the same thing.

        This is never shown to the candidate: the interviewer must not
        voice the assessment, only act on it."""
        answered = [t for t in self.turns if t.grade is not None]
        if not answered:
            return ""
        last = answered[-1]
        g = last.grade
        if g is None:
            return ""

        if last.skipped:
            return (
                "PRIVATE NOTE - they skipped that question entirely. Do not "
                "re-ask it and do not ask it in other words. Move to the next "
                "slot, and consider dropping the difficulty a little."
            )
        if g.score <= 0:
            return ""

        # Have we already pushed on this ground and got nowhere? Two poor
        # answers in a row means the ground has been covered - a third
        # attempt is grinding, not interviewing. This guard exists because
        # without it the model re-asked the same question three times after
        # the candidate had already said they didn't know.
        stuck = (
            len(answered) >= 2
            and answered[-2].grade is not None
            and 0 < answered[-2].grade.score < 4
            and g.score < 4
        )
        if stuck:
            return (
                "PRIVATE NOTE - never say this out loud. That is two weak "
                "answers in a row on the same ground. You have found the edge "
                "of what they know here, which is all you needed. Do NOT ask "
                "about it again in any form. Move to a different topic, and "
                "make it an easier one."
            )

        if g.score < 4:
            stance = (
                "That answer was poor - wrong, off-topic, or essentially "
                "non-responsive. Do NOT move on as if it were fine. Either "
                "challenge what they got wrong or put the question back to "
                "them more concretely. Push once only: if this is already "
                "your second attempt at this ground, move on instead."
            )
        elif g.score < 7:
            stance = (
                "That answer was thin. Pull the thread rather than starting "
                "a new topic."
            )
        else:
            stance = (
                "That answer held up. Either push it one level harder or "
                "move on to the next slot."
            )

        return (
            f"PRIVATE NOTE on their last answer - never say any of this out "
            f"loud, just act on it. {stance} What a strong answer would have "
            f"included and theirs did not: {g.gap}"
        )

    async def _ask(self, slot_index: int) -> Turn:
        slot = self.plan[slot_index]
        note = self._last_answer_note()
        if slot_index == 0:
            ask = (
                "Begin the interview. Greet them in one short sentence, then "
                "ask the opening question. Output only that."
            )
        else:
            ask = (
                "Ask the next question now. Work through the five options in "
                "order - challenge, redirect, dig, ease off, advance - and "
                f"only fall through to the plan's slot {slot_index + 1} "
                f"(of {self.total}) if the last answer genuinely gives you "
                "nothing to work with. Output only the question."
            )
        messages = [
            {"role": "system", "content": self._system_prompt(slot_index)},
            *self._history(),
            *([{"role": "system", "content": note}] if note else []),
            {"role": "user", "content": ask},
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
