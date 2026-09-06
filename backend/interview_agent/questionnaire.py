"""Writes the next question. One call, one question.

Pulled out of interviewer.py so that asking is a thing the coordinator
*calls* rather than something it does inline - the main agent needs it as
a tool it can invoke, and résumé mode needs to swap in a different
implementation behind the same `next_question(ctx)` signature (see the
gateway agent).

There is no question plan anywhere in here. The role brief's real_questions
calibrate difficulty and territory - how hard is fair for a fresher, what
ground is normal - and the prompt is explicit that they are not a script to
read out. The actual question is written fresh each turn, in reaction to
what the candidate just said. That is the whole reason this doesn't feel
like a form: ten researched questions asked in order would be a
questionnaire, not an interview.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from interview_agent import prompts
from interview_agent.config import settings
from interview_agent.context import CandidateContext
from interview_agent.llm import client
from interview_agent.research import RoleBrief
from interview_agent.resume import ResumeDigest

logger = logging.getLogger("interview_agent.questionnaire")

# A spoken question, not an essay.
MAX_TOKENS = 300

FALLBACK_QUESTION = "Tell me about something you've built recently."

STAGES = ("opening", "next", "closing")


@dataclass
class QuestionContext:
    """Everything needed to write the next question. Assembled by whoever
    owns the session - the coordinator today, the main agent in MA-5."""

    mode_key: str
    candidate: CandidateContext
    brief: RoleBrief | None = None
    resume_digest: ResumeDigest | None = None
    coverage_note: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    # The private read on the last answer. Never shown to the candidate.
    private_note: str = ""
    stage: str = "next"
    # Optional steer from the coordinator: which competency to aim at and
    # what kind of move this is. Left empty when the questionnaire is
    # deciding for itself from the reactive ladder below.
    target: str = ""
    intent: str = ""


@dataclass
class Question:
    text: str


BASE_INSTRUCTIONS = """\
You are a technical interviewer running a mock interview. Speak directly to
the candidate, one question at a time - never a written exam, never several
questions in one turn.

{level_note}

{mode_prompt}

{resume_digest}

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

_ASK = {
    "opening": (
        "Begin the interview. Greet them in one short sentence, then ask the "
        "opening question. Output only that."
    ),
    "next": (
        "Ask the next question now. Work through the five options in order - "
        "challenge, redirect, dig, ease off, advance - and only move to new "
        "ground if the last answer genuinely gives you nothing more to work "
        "with. Output only the question."
    ),
    "closing": (
        "You are closing the interview out now - you've covered the ground this "
        "role needs. Work through the five options once more if the last answer "
        "still needs it, but if you're clear to move on, ask at most ONE more "
        "substantive question, then thank them for their time and ask if they "
        "have any questions for you. Output only what you'd say."
    ),
}

_STEER = """\
The interviewer running this round has already decided where to go next:
{decision}
Write that question. Everything above about voice, and about never
grading them, still applies.
"""


def _system_prompt(ctx: QuestionContext) -> str:
    return BASE_INSTRUCTIONS.format(
        level_note=_FRESHER_NOTE if settings.fresher else _EXPERIENCED_NOTE,
        mode_prompt=prompts.mode_prompt(ctx.mode_key, ctx.candidate),
        resume_digest=ctx.resume_digest.render() if ctx.resume_digest else "",
        role_research=ctx.brief.render() if ctx.brief else "",
        coverage_block=ctx.coverage_note,
    )


def _ask_message(ctx: QuestionContext) -> str:
    ask = _ASK.get(ctx.stage, _ASK["next"])
    bits = []
    if ctx.intent:
        bits.append(f"- what kind of move this is: {ctx.intent}")
    if ctx.target:
        bits.append(f"- what to aim it at: {ctx.target}")
    if bits:
        return f"{ask}\n\n{_STEER.format(decision=chr(10).join(bits))}"
    return ask


async def next_question(ctx: QuestionContext) -> Question:
    """Never raises - a failed call falls back to a neutral opener rather
    than costing the candidate their turn."""
    messages = [
        {"role": "system", "content": _system_prompt(ctx)},
        *ctx.history,
        *([{"role": "system", "content": ctx.private_note}] if ctx.private_note else []),
        {"role": "user", "content": _ask_message(ctx)},
    ]

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=messages,  # type: ignore[arg-type]
            max_tokens=MAX_TOKENS,
        )
    except Exception:  # noqa: BLE001
        logger.exception("could not get the next question")
        return Question(text=FALLBACK_QUESTION)

    text = (completion.choices[0].message.content or "").strip()
    return Question(text=text or FALLBACK_QUESTION)
