"""The main agent: an LLM that runs one turn by calling tools.

Its two tools are the other agents - evaluator.read (how did that answer
go) and questionnaire.next_question (what do we ask now). The agent's job
is the decision in between: challenge that claim, dig into it, ease off,
or move to new ground, and on which competency.

The loop is PER TURN, not per interview. An interview is human-in-the-loop,
so the agent runs, lands on a question, and stops - the HTTP request
returns, the candidate types, and the next request runs the loop again.

Five things this module deliberately does NOT let the agent do, because a
tool-calling loop is not a place to put invariants you actually care
about:

1. It never writes to the candidate. The agent picks intent and target;
   the questionnaire agent writes the words, and those words are returned
   verbatim. This is the structural guarantee against a score leak now
   that the main agent gets to see evaluator output.
2. It cannot skip judging the last answer - the first tool call is pinned
   to evaluate_answer with tool_choice.
3. It cannot loop forever - MAX_STEPS, then fall back to asking directly.
4. It does not decide when the interview ends. Code owns the question cap
   and the closing turn; end_interview is only honoured past the minimum.
5. It does not own the ledger or the background scorer. Those run in
   interviewer.answer() regardless of what the agent did.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from interview_agent import evaluator
from interview_agent.config import settings
from interview_agent.evaluator import AnswerNote
from interview_agent.llm import client

logger = logging.getLogger("interview_agent.agent")

# Enough for evaluate -> think -> ask, with slack for a stray extra call.
MAX_STEPS = 6
MAX_TOKENS = 400

INTENTS = ("challenge", "redirect", "dig", "ease_off", "advance")


@dataclass
class TurnDecision:
    """What the agent settled on for this turn."""

    note: AnswerNote | None = None
    question: str = ""
    ended: bool = False
    end_reason: str = ""
    # True when the loop fell over and the caller should ask directly.
    fell_back: bool = False


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "evaluate_answer",
            "description": (
                "Read the candidate's last answer: was it correct, thin, "
                "wrong, dodged, or an honest 'I don't know', which "
                "competency it bears on, and what a right answer would "
                "have contained. Call this first, before deciding anything."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "next_question",
            "description": (
                "Ask the candidate the next question. You choose the move "
                "and the ground; the question itself gets written for you. "
                "This ends your turn."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "enum": list(INTENTS),
                        "description": (
                            "challenge: they said something wrong or "
                            "unsupported - put it to them. redirect: they "
                            "answered a different question. dig: fine but "
                            "shallow, pull the thread. ease_off: they "
                            "honestly don't know, drop to adjacent easier "
                            "ground. advance: done here, move to new ground."
                        ),
                    },
                    "target": {
                        "type": "string",
                        "description": (
                            "The competency to aim at, by name, from the "
                            "coverage list. Empty string to stay on "
                            "whatever the last answer was about."
                        ),
                    },
                    "why": {
                        "type": "string",
                        "description": "One short line: why this move, now.",
                    },
                },
                "required": ["intent", "target", "why"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "end_interview",
            "description": (
                "End the interview. Only when there is genuinely nothing "
                "left worth asking - every competency has a read and "
                "pushing further would just be padding."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "One short line."},
                },
                "required": ["reason"],
            },
        },
    },
]

_SYSTEM = """\
You are running one turn of a mock technical interview with an entry-level
candidate. You do not talk to the candidate yourself - you decide what
happens next, and the questionnaire tool writes the actual words.

Work in this order:
1. Call evaluate_answer to find out how their last answer actually went.
2. Read that result and decide ONE move.
3. Call next_question with that move, which ends your turn.

Choosing the move - a wrong claim outranks everything else:
- challenge if the read came back `wrong`. Do not let it pass and do not
  move to a new topic. This is the most important thing you do.
- redirect if they answered something other than what was asked.
- dig if the answer was `thin` - right shape, no substance behind it.
- ease_off if they honestly said they don't know. Do not grind. An honest
  "I don't know" is worth more than a bluff; treat it that way.
- advance only if the answer genuinely held up, or you have already pushed
  on this ground once. Then pick the competency with the least evidence.

If the read says the ground is exhausted - two weak answers in a row on
the same thing - you must not aim at it again. Move on and go easier.

{state}

Never write a question, a greeting, or any candidate-facing text
yourself. Never say anything evaluative to them; they are scored once, at
the very end, and never see your working.
"""


def _state_block(session, closing: bool) -> str:
    names = session._competency_names()
    lines = [session.ledger.render(names) or "COVERAGE - nothing tracked for this role."]
    lines.append(
        f"\nThis is question {len(session.turns)} of at most "
        f"{session.question_cap}."
    )
    if closing:
        lines.append(
            "This is the WRAP-UP turn: whatever you ask is the last thing "
            "they answer. Ask one final question, or end the interview."
        )
    return "\n".join(lines)


async def run_turn(session, current, closing: bool) -> TurnDecision:
    """One bounded agent loop over the turn that just got answered.

    Never raises. On any failure it returns fell_back=True and the caller
    runs the deterministic path instead - a wobbly agent must not cost the
    candidate their interview.
    """
    decision = TurnDecision()
    prior_note = session.turns[-2].note if len(session.turns) > 1 else None
    prior_read = prior_note.read if prior_note is not None else ""

    messages: list[dict] = [
        {"role": "system", "content": _SYSTEM.format(state=_state_block(session, closing))},
        {
            "role": "user",
            "content": (
                f"QUESTION YOU ASKED:\n{current.question}\n\n"
                f"THEIR ANSWER:\n"
                f"{'(skipped)' if current.skipped else (current.answer or '')}"
            ),
        },
    ]

    for step in range(MAX_STEPS):
        # Pin the first call: the agent does not get to decide whether to
        # judge the answer.
        force_eval = step == 0 and decision.note is None
        try:
            completion = await client().chat.completions.create(
                model=settings.model,
                messages=messages,  # type: ignore[arg-type]
                tools=TOOLS,  # type: ignore[arg-type]
                tool_choice=(
                    {"type": "function", "function": {"name": "evaluate_answer"}}
                    if force_eval
                    else "auto"
                ),
                max_tokens=MAX_TOKENS,
            )
        except Exception:  # noqa: BLE001
            logger.exception("main agent call failed at step %d", step)
            decision.fell_back = True
            return decision

        msg = completion.choices[0].message
        calls = msg.tool_calls or []
        if not calls:
            # It replied with prose instead of acting. That prose is not
            # allowed anywhere near the candidate, so drop it and push it
            # back on track.
            logger.warning("main agent produced text instead of a tool call; nudging")
            messages.append({"role": "assistant", "content": msg.content or ""})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Do not write to the candidate. Call next_question "
                        "or end_interview now."
                    ),
                }
            )
            continue

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": c.id,
                        "type": "function",
                        "function": {
                            "name": c.function.name,
                            "arguments": c.function.arguments,
                        },
                    }
                    for c in calls
                ],
            }
        )

        for call in calls:
            name = call.function.name
            try:
                args = json.loads(call.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if name == "evaluate_answer":
                decision.note = await evaluator.read(
                    current.question,
                    current.answer or "",
                    current.skipped,
                    session._rubric(),
                    prior_read,
                )
                # Publish it onto the turn straight away. The questionnaire's
                # private note is read back off session.turns, so holding this
                # until run_turn returns would steer the question we are about
                # to write with the PREVIOUS answer's read.
                current.note = decision.note
                result = decision.note.to_dict()

            elif name == "next_question":
                intent = str(args.get("intent", "")).strip().lower()
                if intent not in INTENTS:
                    intent = "advance"
                target = str(args.get("target", "")).strip()
                if target not in session._competency_names():
                    target = ""
                ctx = session._question_context("closing" if closing else "next")
                ctx.intent = intent
                ctx.target = target
                # The pitch follows whatever ground the agent actually
                # picked, not whatever the last answer happened to be about.
                ctx.pitch = session._pitch_for(target)
                # Routed by mode: the résumé round uses the gateway agent.
                question = await session.question_agent.next_question(ctx)
                decision.question = question.text
                logger.info(
                    "main agent: %s%s - %s",
                    intent,
                    f" @ {target}" if target else "",
                    str(args.get("why", ""))[:120],
                )
                result = {"asked": question.text}

            elif name == "end_interview":
                decision.ended = True
                decision.end_reason = str(args.get("reason", "")).strip()
                result = {"ended": True}

            else:
                result = {"error": f"no such tool: {name}"}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )

        if decision.question or decision.ended:
            return decision

    logger.warning("main agent hit MAX_STEPS without asking; falling back")
    decision.fell_back = True
    return decision
