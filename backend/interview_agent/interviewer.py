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
read (see notes.CoverageLedger), with a min/max question band as the floor
and ceiling. Asking and reading the last answer are deliberately separate
calls - see notes.py. Scoring happens once, at the end - see scorecard.py.
Nothing evaluative is ever computed or shown mid-interview.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interview_agent import notes, prompts, research
from interview_agent.config import settings
from interview_agent.context import CandidateContext
from interview_agent.llm import client
from interview_agent.notes import AnswerNote, CoverageLedger
from interview_agent.prompts import Mode
from interview_agent.research import RoleBrief

logger = logging.getLogger("interview_agent.interviewer")

# A spoken question, not an essay. Also keeps voice latency down.
MAX_TOKENS = 300

_FALLBACK_QUESTION = "Tell me about something you've built recently."

BASE_INSTRUCTIONS = """\
You are a technical interviewer running a mock interview. Speak directly to
the candidate, one question at a time - never a written exam, never several
questions in one turn.

{level_note}

{mode_prompt}

{role_research}

{coverage_block}

BEFORE you think about where to go next, react to what they just said, in
that order. The coverage note above tells you WHERE to go once you've
decided to move on - it is not a script to read through, and there is no
fixed list of questions waiting to be asked.

Read their last answer and pick ONE of these:

1. CHALLENGE - they said something wrong, unsupported, or alarming.
   This outranks everything else. Do not let it pass and do not move to a
   new topic. Put it to them directly and give them the chance to correct
   it: "you said X - walk me through why." Claims that must never go
   unchallenged include storing or emailing plaintext passwords, "it's
   secure because...", a tool chosen because it "scales" with no reason,
   a flat factual error about how something works, or anything flagged in
   the role research above. Getting this wrong is the single worst thing
   you can do in this job.

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
   pushed on it once. Move to new ground: pick whatever you have the
   least evidence on so far (see COVERAGE above). Connect the new question
   to something they said if you can.

Only option 5 means picking new ground. The other four are you doing your
job, and they are more common than 5 in a real interview.

Escalate as you go: later questions should be harder than earlier ones,
and meaningfully harder once you're most of the way through the coverage.

Voice and manner:
- One or two sentences, phrased the way a human interviewer actually talks
  out loud - not a written prompt.
- This may be read aloud, so no markdown, no bullet points, no code
  blocks, no numbered lists. Plain conversational sentences.
- Do NOT grade, score or give feedback. No "correct", no "that's wrong",
  no "good answer" - the candidate is scored separately, once, at the very
  end, and seeing your opinion here would poison it. A brief neutral
  acknowledgement ("mm-hm", "right, okay") before the question is fine and
  natural.
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

_ASK_OPENING = (
    "Begin the interview. Greet them in one short sentence, then ask the "
    "opening question. Output only that."
)
_ASK_NEXT = (
    "Ask the next question now. Work through the five options in order - "
    "challenge, redirect, dig, ease off, advance - and only move to new "
    "ground if the last answer genuinely gives you nothing more to work "
    "with. Output only the question."
)
_ASK_CLOSING = (
    "You are closing the interview out now - you've covered the ground this "
    "role needs. Work through the five options once more if the last answer "
    "still needs it, but if you're clear to move on, ask at most ONE more "
    "substantive question, then thank them for their time and ask if they "
    "have any questions for you. Output only what you'd say."
)


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
    candidate: CandidateContext
    mode: Mode = field(init=False)
    brief: RoleBrief | None = None
    turns: list[Turn] = field(default_factory=list)
    ledger: CoverageLedger = field(default_factory=CoverageLedger)
    finished: bool = False
    _final_turn_sent: bool = False
    # Per-session ceiling on questions; None means use settings.max_questions.
    # Only the quality-check harness sets it, to keep scripted runs short.
    _max_questions: int | None = None

    def __post_init__(self) -> None:
        self.mode = prompts.get(self.mode_key)

    # -- setup --------------------------------------------------------------

    async def start(self, max_questions: int | None = None) -> Turn:
        self.brief = await research.build_brief(self.candidate, self.mode)
        self.turns = []
        self.ledger = CoverageLedger()
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
    def closing(self) -> bool:
        """True once the wrap-up question has been sent - the interview
        ends on the next answer."""
        return self._final_turn_sent

    def _competency_names(self) -> list[str]:
        return [c.name for c in self.brief.competencies] if self.brief else []

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

    def _system_prompt(self) -> str:
        return BASE_INSTRUCTIONS.format(
            level_note=_FRESHER_NOTE if settings.fresher else _EXPERIENCED_NOTE,
            mode_prompt=prompts.mode_prompt(self.mode_key, self.candidate),
            role_research=self.brief.render() if self.brief else "",
            coverage_block=self.ledger.render(self._competency_names()),
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
        note = self._last_answer_note()

        if opening:
            ask = _ASK_OPENING
        elif self._closing_now():
            self._final_turn_sent = True
            ask = _ASK_CLOSING
        else:
            ask = _ASK_NEXT

        messages = [
            {"role": "system", "content": self._system_prompt()},
            *self._history(),
            *([{"role": "system", "content": note}] if note else []),
            {"role": "user", "content": ask},
        ]
        text = await self._complete(messages) or _FALLBACK_QUESTION
        turn = Turn(question=text)
        self.turns.append(turn)
        return turn

    async def answer(self, text: str, skipped: bool = False) -> Turn | None:
        """Record the answer, take a private read on it, and ask the next
        question - or None if the interview just ended.

        No score is computed here and none is returned - grading happens
        once, at the end, in scorecard.py.
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

        prior_read = ""
        if len(self.turns) > 1 and self.turns[-2].note is not None:
            prior_read = self.turns[-2].note.read  # type: ignore[union-attr]

        current.note = await notes.take(
            current.question,
            current.answer,
            current.skipped,
            self._competency_names(),
            prior_read,
        )
        self.ledger.record(
            current.note.evidenced,
            notes.strength_of(current.note.read),
            focus=current.note.focus,
            exhausted=current.note.topic_exhausted,
        )

        if self._final_turn_sent or len(self.turns) >= self.question_cap:
            self.finished = True
            return None
        return await self._ask(opening=False)

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
