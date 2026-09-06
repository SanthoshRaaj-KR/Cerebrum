"""The résumé round's own agent - it owns both halves of that interview.

Every other mode is a researched syllabus: research.py searches for what
freshers are actually asked for the target role, and the questionnaire
works from that brief. The résumé round has no external syllabus. The
material IS the candidate's own projects, so searching the web for it is
meaningless - what needs verifying is whether they actually did what they
wrote down, and whether they can go one level past the rehearsed summary.

So for `resume_projects` this module replaces research.py: build_brief
reads the résumé digest and decides what this particular interview should
examine, naming competencies after the candidate's real projects and
flagging the claims that would matter if they can't back them up. From
there everything downstream is unchanged - the coverage ledger, the
evaluator's rubric and the scorecard all just see a RoleBrief and neither
know nor care that it came from a résumé rather than a search.

Question-writing reuses questionnaire.py wholesale and only swaps in a
different framing; duplicating the reactive ladder and the voice rules
here would just let the two drift apart.
"""

from __future__ import annotations

import json
import logging

from interview_agent import questionnaire
from interview_agent.config import settings
from interview_agent.context import CandidateContext
from interview_agent.llm import client
from interview_agent.prompts import Mode
from interview_agent.questionnaire import Question, QuestionContext
from interview_agent.research import Competency, RoleBrief
from interview_agent.resume import ResumeDigest

logger = logging.getLogger("interview_agent.gateway")

MODE_KEY = "resume_projects"
BRIEF_MAX_TOKENS = 1400


_BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "competencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "why_it_matters": {"type": "string"},
                    "fresher_bar": {"type": "string"},
                    "probe_angles": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["name", "why_it_matters", "fresher_bar", "probe_angles"],
                "additionalProperties": False,
            },
        },
        "red_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["competencies", "red_flags"],
    "additionalProperties": False,
}

_BRIEF_PROMPT = """\
You are preparing to interview an entry-level candidate about their OWN
résumé - the projects and skills they wrote down. There is no external
syllabus for this round: the material is what is in front of you.

Decide what this particular interview should examine.

- competencies: 5 to 8 areas THIS résumé makes it fair to examine. One per
  substantial project, plus a cluster for any skill claimed across several
  of them. Name them after the actual thing - "Friday AI: the agent loop
  and tool safety", not "Backend Development". For each:
  - why_it_matters: one sentence on what examining it would tell you.
  - fresher_bar: what genuine ownership of that looks like from someone at
    this level - being able to say why they made a specific decision, what
    they'd do differently, what broke. Not production war stories.
  - probe_angles: 2-3 short phrases naming ways in, taken from their own
    wording.
- red_flags: 3 to 6 claims in THIS résumé that would be a real problem if
  they can't back them up. A technology in the skills list that appears in
  no project. A system described as if it carried scale they almost
  certainly didn't have. An architecture choice stated with no decision
  behind it. Quote or closely paraphrase the résumé so the claim is
  recognisable.

Everything must come from the résumé itself. Do not invent projects, and
do not import generic role expectations they never claimed.
"""

_FRAMING = """\
THIS ROUND IS ABOUT THEIR OWN WORK. The competencies above are their
projects, not a syllabus. Every question should be anchored in something
specific they actually wrote down, and your job is to find out whether
they really did it:

- Push one level past the rehearsed summary. Anyone can describe their
  project; ask why that choice over the obvious alternative, what they
  measured, what broke, what they'd do differently now.
- Ownership is the thing being tested. "We" for work that was clearly
  theirs, or vagueness about the part they supposedly built, is worth
  following up on directly but without accusation.
- A technology listed on the résumé that they cannot say anything
  concrete about is exactly the kind of claim to challenge.
"""


async def build_brief(
    candidate: CandidateContext, digest: ResumeDigest | None, mode: Mode
) -> RoleBrief:
    """The résumé round's answer to research.build_brief. Never raises - a
    failure degrades to an empty brief and the interview still runs off the
    résumé text in the prompt."""
    source = (digest.render() if digest and not digest.is_empty() else "") or (
        candidate.resume_text()
    )
    if not source.strip():
        return RoleBrief(grounded=False)

    try:
        completion = await client().chat.completions.create(
            model=settings.model,
            messages=[
                {"role": "system", "content": _BRIEF_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Target role: {candidate.role or 'unspecified'}\n"
                        f"Level: {candidate.level or 'fresher'}\n\n"
                        f"THEIR RÉSUMÉ:\n{source}"
                    ),
                },
            ],
            max_tokens=BRIEF_MAX_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "resume_brief",
                    "schema": _BRIEF_SCHEMA,
                    "strict": True,
                },
            },
        )
        payload = json.loads(completion.choices[0].message.content or "{}")
    except Exception:  # noqa: BLE001
        logger.exception("could not build the résumé brief")
        return RoleBrief(grounded=False)

    brief = RoleBrief(
        competencies=[
            Competency(
                name=str(c.get("name", "")).strip(),
                why_it_matters=str(c.get("why_it_matters", "")).strip(),
                fresher_bar=str(c.get("fresher_bar", "")).strip(),
                probe_angles=[
                    str(p).strip() for p in c.get("probe_angles", []) if str(p).strip()
                ],
            )
            for c in payload.get("competencies", [])
            if str(c.get("name", "")).strip()
        ],
        red_flags=[str(r).strip() for r in payload.get("red_flags", []) if str(r).strip()],
        # Grounded in the candidate's own résumé rather than a web search.
        # There are no sources to cite, and the report shouldn't claim any.
        sources=[],
        grounded=bool(payload.get("competencies")),
    )
    logger.info("résumé brief: %d competencies from their own work", len(brief.competencies))
    return brief


async def next_question(ctx: QuestionContext) -> Question:
    """Same machinery as every other mode, different framing."""
    ctx.framing = _FRAMING
    return await questionnaire.next_question(ctx)
