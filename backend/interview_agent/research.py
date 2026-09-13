"""Research the role before the interview starts.

Real interviewers don't invent a role's shape from vibes - they know what
freshers for that role are actually asked and actually expected to know.
This module gets that from a live web search (see search.py for the
provider fallback chain), then distills it into a RoleBrief the interviewer
carries as background knowledge for the whole session.

Nothing here is a question plan. The brief calibrates difficulty and
territory - what a fresher for this role is fairly judged on, and roughly
how hard real companies ask it - but the actual next question is still
generated in the conversation, in interviewer.py, in reaction to what the
candidate just said. See RoleBrief.render() for the framing that keeps the
real_questions field from turning back into a script.

Cached to disk per (role, level, mode) because a second session on the same
role shouldn't pay for the search or the distillation call again.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from interview_agent import search
from interview_agent.config import ROOT, settings
from interview_agent.context import CandidateContext
from interview_agent.llm import client
from interview_agent.prompts import Mode

logger = logging.getLogger("interview_agent.research")

CACHE_DIR = ROOT / ".cache" / "research"
DISTILL_MAX_TOKENS = 1600


@dataclass
class Competency:
    name: str
    why_it_matters: str
    fresher_bar: str
    probe_angles: list[str] = field(default_factory=list)


@dataclass
class RoleBrief:
    competencies: list[Competency] = field(default_factory=list)
    real_questions: list[str] = field(default_factory=list)
    red_flags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    # False when search was skipped, unconfigured, or every provider came
    # back empty - the brief still exists (from the model's own knowledge of
    # the role) but isn't backed by a live search, which the report is
    # honest about.
    grounded: bool = True

    def to_dict(self) -> dict:
        return asdict(self)

    def render(self) -> str:
        """The block injected into the interviewer's system prompt."""
        if not self.competencies:
            return ""
        lines = [
            "ROLE RESEARCH - what freshers for this role are actually "
            "expected to know, gathered before this interview started:"
        ]
        for c in self.competencies:
            lines.append(f"\n- {c.name}: {c.why_it_matters}")
            lines.append(f"  Fair bar for a fresher: {c.fresher_bar}")
            if c.probe_angles:
                lines.append(f"  Ways in: {'; '.join(c.probe_angles)}")

        if self.red_flags:
            lines.append(
                "\nClaims specific to this role that must be challenged if "
                "the candidate makes them:"
            )
            for r in self.red_flags:
                lines.append(f"- {r}")

        if self.real_questions:
            lines.append(
                "\nReal questions companies have asked freshers for this "
                "role, found just now. These calibrate DIFFICULTY AND SHAPE "
                "only - how hard is fair, what ground is normal. Do not "
                "read these out and do not work through them in order. Ask "
                "your own question, arising from what the candidate just "
                "said:"
            )
            for q in self.real_questions[:12]:
                lines.append(f"- {q}")

        return "\n".join(lines)


# -- cache -------------------------------------------------------------------


# Bumped whenever the research queries or the distill prompt change in a
# way that should invalidate what is already on disk. Without this a brief
# cached under the old, level-unanchored searches would keep being served
# for the rest of its 14 days, and the fix would look like it did nothing.
_BRIEF_VERSION = 2


def _cache_key(role: str, level: str, mode_key: str) -> str:
    raw = f"v{_BRIEF_VERSION}|{role.strip().lower()}|{level.strip().lower()}|{mode_key}"
    return hashlib.sha1(raw.encode()).hexdigest()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{key}.json"


def _brief_from_dict(payload: dict) -> RoleBrief:
    return RoleBrief(
        competencies=[Competency(**c) for c in payload.get("competencies", [])],
        real_questions=list(payload.get("real_questions", [])),
        red_flags=list(payload.get("red_flags", [])),
        sources=list(payload.get("sources", [])),
        grounded=bool(payload.get("grounded", True)),
    )


def _load_cache(key: str) -> RoleBrief | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    age_days = (time.time() - payload.get("_cached_at", 0)) / 86400
    if age_days > settings.research_cache_days:
        return None
    try:
        return _brief_from_dict(payload)
    except Exception:  # noqa: BLE001
        return None


def _save_cache(key: str, brief: RoleBrief) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = brief.to_dict()
        payload["_cached_at"] = time.time()
        _cache_path(key).write_text(json.dumps(payload), encoding="utf-8")
    except Exception:  # noqa: BLE001
        logger.exception("could not write research cache")


# -- search --------------------------------------------------------------


# Words that all mean "this is someone's first job". Any of them makes the
# searches say "entry level" explicitly rather than passing the level
# through raw, because search engines have far more indexed content for
# that phrase than for "fresher" alone outside India.
_ENTRY_LEVEL_WORDS = {
    "fresher", "freshers", "entry level", "entry-level", "graduate",
    "new grad", "new graduate", "student", "intern", "beginner", "junior",
}


def _is_entry_level(level: str) -> bool:
    return level.strip().lower() in _ENTRY_LEVEL_WORDS


async def _gather_raw(role: str, mode: Mode, level: str) -> tuple[str, list[str]]:
    """Runs the searches, returns (digest text for the LLM, source urls).

    Four angles rather than one: what is actually asked, what is asked
    RIGHT NOW, what the role actually requires, and the round's own framing.

    **Every one of them carries the level.** A bare "{role} interview
    questions" search skews hard toward senior content - it returns
    distributed-systems war stories for a role whose real screen is "what
    is an index" - and one unanchored query out of four is enough on its
    own, because `real_questions` is lifted straight out of this digest and
    becomes what the interviewer pitches from. The recency query used to be
    exactly that unanchored shape.

    For an entry level, one query also says "0 to 1 years experience" in so
    many words. That is the phrase job postings actually use, and it pulls
    the postings written for people with no experience rather than the ones
    that merely say "junior" in the title and then ask for three years.

    The year is explicit on two of them. Interview content dates faster
    than it looks: the questions an AI engineer gets asked moved more in
    the last two years than a backend syllabus moved in ten, and a search
    that does not say "this year" happily returns a listicle from 2019. The
    mode name goes in too, so an LLD round pulls object-design questions
    rather than whatever the role is asked in general.
    """
    year = datetime.date.today().year
    lv = level.strip() or "fresher"
    entry = _is_entry_level(lv)
    # "entry level" for anything that means a first job; otherwise the level
    # as the candidate typed it, so this still works if `fresher` is off.
    phrase = "entry level" if entry else lv

    queries = [
        f"{role} {lv} interview questions asked",
        f"{phrase} {role} interview questions {year}",
        f"{phrase} {role} technical interview questions {mode.name}",
        (
            f"{role} {lv} job description required skills"
            f" 0 to 1 years experience {year}"
            if entry
            else f"{role} {lv} job description required skills {year}"
        ),
    ]
    outcome = await search.gather(queries, settings.research_max_results)

    seen: set[str] = set()
    digest_parts: list[str] = []
    sources: list[str] = []
    for hit in outcome.hits:
        if not hit.url or hit.url in seen:
            continue
        seen.add(hit.url)
        digest_parts.append(f"SOURCE: {hit.title} ({hit.url})\n{hit.content[:1200]}")
        sources.append(hit.url)

    return "\n\n".join(digest_parts), sources[:10]


# -- distillation --------------------------------------------------------


_SCHEMA = {
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
        "real_questions": {"type": "array", "items": {"type": "string"}},
        "red_flags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["competencies", "real_questions", "red_flags"],
    "additionalProperties": False,
}

_DISTILL_PROMPT = """\
You are preparing an interviewer's background brief on a role, before a
real mock interview starts. Distill what actually matters for a FRESHER /
entry-level candidate applying for: {role} (a {mode_name} round).

It is {today}. Where the sources disagree, or where something has clearly
moved on, weight what is being asked NOW over what used to be standard.

{digest_block}

Produce:
- competencies: 6 to 10 named areas a fresher for this role is actually
  judged on. For each: why_it_matters (one sentence), fresher_bar (what
  COUNTS AS HAVING IT at entry level - be concrete and generous, describe
  what a good fresher answer looks like, not what a senior engineer would
  know), probe_angles (2-3 short phrases naming ways an interviewer could
  open into this area from a candidate's own project or a scenario - not a
  list of exam questions).
- real_questions: pull actual interview questions out of the sources if
  they contain any, verbatim or lightly cleaned up, favouring the ones that
  show up again and again - those are what this role is really being asked.
  Empty list if the sources gave you nothing concrete to quote; do not
  invent questions to fill this field.
  DROP anything that only makes sense to someone who has already held the
  job: running an incident, operating a cluster, owning a migration,
  tuning something in production, or a senior system-design question in a
  fresher's clothing. Search will hand you some of these no matter how the
  query is worded, and a question someone with zero years cannot fairly be
  expected to have met does not belong in this list however often it
  appears.
- red_flags: 3-6 claims specific to this role that a fresher might
  plausibly say and that an interviewer must not let pass unchallenged - a
  security misconception, a wrong claim about how something works, a tool
  choice defended with a made-up justification.

Ground everything in what is FAIR AND NORMAL to ask a new graduate, not a
wishlist of everything the role could ever touch.
"""


def _digest_block(digest: str) -> str:
    if digest:
        return (
            "SEARCH RESULTS (real postings and question lists found just "
            f"now):\n\n{digest}"
        )
    return (
        "No live search results were available this time - use your own "
        "knowledge of what this role's fresher interviews typically cover, "
        "but stay general and conservative rather than inventing specifics."
    )


async def _distill(role: str, mode: Mode, digest: str) -> RoleBrief:
    completion = await client().chat.completions.create(
        model=settings.model,
        messages=[
            {
                "role": "system",
                "content": _DISTILL_PROMPT.format(
                    role=role,
                    mode_name=mode.name,
                    today=datetime.date.today().strftime("%B %Y"),
                    digest_block=_digest_block(digest),
                ),
            },
            {"role": "user", "content": f"Role: {role}\nRound: {mode.name} - {mode.blurb}"},
        ],
        max_tokens=DISTILL_MAX_TOKENS,
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "role_brief", "schema": _SCHEMA, "strict": True},
        },
    )
    payload = json.loads(completion.choices[0].message.content or "{}")
    return RoleBrief(
        competencies=[
            Competency(
                name=str(c.get("name", "")).strip(),
                why_it_matters=str(c.get("why_it_matters", "")).strip(),
                fresher_bar=str(c.get("fresher_bar", "")).strip(),
                probe_angles=[str(p).strip() for p in c.get("probe_angles", []) if str(p).strip()],
            )
            for c in payload.get("competencies", [])
            if str(c.get("name", "")).strip()
        ],
        real_questions=[str(q).strip() for q in payload.get("real_questions", []) if str(q).strip()],
        red_flags=[str(r).strip() for r in payload.get("red_flags", []) if str(r).strip()],
    )


# -- entrypoint ------------------------------------------------------------


async def build_brief(candidate: CandidateContext, mode: Mode) -> RoleBrief:
    """The role brief for this session. Never raises - a research failure
    degrades to a model-knowledge-only brief rather than costing the
    candidate their session."""
    role = candidate.role.strip() or mode.name
    level = candidate.level.strip() or ("fresher" if settings.fresher else "experienced")
    key = _cache_key(role, level, mode.key)

    cached = _load_cache(key)
    if cached is not None:
        return cached

    if not settings.research_enabled or not search.any_provider_configured():
        try:
            brief = await _distill(role, mode, digest="")
        except Exception:  # noqa: BLE001
            logger.exception("could not build a role brief without research")
            return RoleBrief(grounded=False)
        brief.grounded = False
        return brief

    digest, sources = "", []
    try:
        digest, sources = await _gather_raw(role, mode, level)
    except Exception:  # noqa: BLE001
        logger.exception("could not gather role research")

    try:
        brief = await _distill(role, mode, digest)
    except Exception:  # noqa: BLE001
        logger.exception("could not distill the role research brief")
        return RoleBrief(grounded=False)

    brief.sources = sources
    brief.grounded = bool(digest)
    if brief.grounded:
        _save_cache(key, brief)
    return brief
