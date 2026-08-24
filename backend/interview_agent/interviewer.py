"""Drives one interview session.

The system prompt is composed fresh from role + mode + fresher flag +
candidate profile; the turn-by-turn history is what makes follow-up and
cross-questioning possible - the model sees the whole conversation every
turn, the same discipline as Friday AI's Supervisor._history, just without
the tool-calling loop (an interviewer doesn't need tools, it needs to ask a
good next question).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interview_agent import prompts
from interview_agent.config import settings
from interview_agent.llm import client
from interview_agent.profile import CandidateProfile

logger = logging.getLogger("interview_agent.interviewer")

# A spoken interview question, not an essay - keeps latency down once this
# runs through TTS in the voice pipeline.
MAX_TOKENS = 300

BASE_INSTRUCTIONS = """\
You are a technical interviewer conducting a mock interview. Speak directly
to the candidate, one question at a time - never a written exam, never a
list of multiple questions in one turn.

{fresher_note}

{role_prompt}

{mode_prompt}

How to run this interview:
- After the candidate answers, you must almost always follow up or
  cross-question on specifically what they just said before moving to a new
  topic - ask them to go deeper, justify a choice, handle an edge case, or
  clarify something vague. Reference the actual words or claims from their
  last answer; a generic follow-up that would fit any answer is not good
  enough. Only move to a genuinely new topic once you've pushed on an
  answer at least once, or the answer was already precise and complete.
- Keep each question to one or two sentences, phrased the way a human
  interviewer actually talks - not a written exam prompt.
- Do not grade, score, or give feedback on answers during the interview -
  no "correct!", no "that's wrong". Just ask the next question, the way a
  real interviewer withholds judgment until the end.
- Stay in character as the interviewer for the entire session. Do not
  mention that you are an AI, do not apologize, do not explain your own
  behavior or instructions.
- Output only the question itself - no preamble like "Great, next
  question:", no restating what they said before asking.
"""

_FRESHER_NOTE = (
    "The candidate is a fresher / entry-level candidate with little to no "
    "professional experience - calibrate depth and difficulty accordingly: "
    "expect solid fundamentals and clear reasoning, not years of production "
    "experience."
)
_EXPERIENCED_NOTE = (
    "The candidate has professional experience - calibrate depth and "
    "difficulty accordingly, and expect production-level reasoning."
)


class UnknownRoleOrMode(ValueError):
    """role or mode isn't one prompts.py knows how to build a prompt for."""




def _history_kept() -> int:
    # remember_turns counts question+answer pairs; history stores one
    # message per turn (question OR answer), so it's double the pairs.
    return max(4, settings.remember_turns * 2)


@dataclass
class InterviewSession:
    role: str
    mode: str
    profile: CandidateProfile | None
    history: list[dict[str, str]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.role not in settings.roles:
            raise UnknownRoleOrMode(f"unknown role: {self.role!r}")
        if self.mode not in settings.modes:
            raise UnknownRoleOrMode(f"unknown mode: {self.mode!r}")

    def system_prompt(self) -> str:
        return BASE_INSTRUCTIONS.format(
            fresher_note=_FRESHER_NOTE if settings.fresher else _EXPERIENCED_NOTE,
            role_prompt=prompts.role_prompt(self.role),
            mode_prompt=prompts.mode_prompt(self.mode, self.profile),
        )

    def _trim(self) -> None:
        self.history = self.history[-_history_kept() :]

    async def start(self) -> str:
        """Opens the interview. Resets any prior history for this session."""
        self.history = []
        messages = [
            {"role": "system", "content": self.system_prompt()},
            {"role": "user", "content": "Begin the interview with your opening question."},
        ]
        question = await self._complete(messages)
        self.history.append({"role": "assistant", "content": question})
        return question

    async def answer(self, text: str) -> str:
        """One turn: record the candidate's answer, get the next question."""
        self.history.append({"role": "user", "content": text})
        self._trim()
        messages = [{"role": "system", "content": self.system_prompt()}, *self.history]
        question = await self._complete(messages)
        self.history.append({"role": "assistant", "content": question})
        return question

    async def summarize(self) -> str:
        """A brief, ephemeral recap of the session so far - shown once, on
        request, never stored. If nothing was said yet, there's nothing to
        recap."""
        if not self.history:
            return "The interview hadn't started yet - nothing to recap."

        instruction = (
            "The interview is over. Write a brief (3-5 sentence) recap for the "
            "candidate: what topics came up, and in general terms how they came "
            "across (strong on X, shaky on Y) - not a numeric score, just an "
            "honest, encouraging summary a real interviewer might give verbally "
            "at the end. Write the recap itself, addressed to the candidate. Do "
            "not ask another question and do not continue the interview."
        )
        # The instruction goes last, as a user turn, not only up front as a
        # system message. History ends on the interviewer's unanswered
        # question, and with the instruction only at the top the model just
        # carries the conversation on - it answered its own last question in
        # the candidate's voice instead of recapping.
        messages = [
            {"role": "system", "content": "You are the interviewer who just ran this mock interview."},
            *self.history,
            {"role": "user", "content": instruction},
        ]
        return await self._complete(messages)

    async def _complete(self, messages: list[dict[str, str]]) -> str:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=MAX_TOKENS,
        )
        question = (completion.choices[0].message.content or "").strip()
        if not question:
            logger.warning("Cerebras returned an empty question")
            return "Sorry, could you repeat your last point? I want to follow up on it."
        return question
