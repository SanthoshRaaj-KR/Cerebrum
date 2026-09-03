"""Research the role before the interview starts.

Real interviewers don't invent a role's shape from vibes - they know what
freshers for that role are actually asked and actually expected to know.
This module gets that from a live Tavily search, then distills it into a
RoleBrief the interviewer carries as background knowledge for the whole
session.

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

import hashlib
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx

from interview_agent.config import ROOT, settings
from interview_agent.context import CandidateContext
from interview_agent.llm import client
from interview_agent.prompts import Mode

logger = logging.getLogger("interview_agent.research")

TAVILY_URL = "https://api.tavily.com/search"
CACHE_DIR = ROOT / ".cache" / "research"
DISTILL_MAX_TOKENS = 1600
SEARCH_TIMEOUT = 20.0


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
    # False when Tavily was skipped, unconfigured, or came back empty - the
    # brief still exists (from the model's own knowledge of the role) but
    # isn't backed by a live search, which the report is honest about.
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


def _cache_key(role: str, level: str, mode_key: str) -> str:
    raw = f"{role.strip().lower()}|{level.strip().lower()}|{mode_key}"
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


async def _tavily_search(query: str, max_results: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as http:
        r = await http.post(
            TAVILY_URL,
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": False,
            },
        )
    r.raise_for_status()
    return r.json().get("results", [])


async def _gather_raw(role: str) -> tuple[str, list[str]]:
    """Runs the searches, returns (digest text for the LLM, source urls).

    Three angles rather than one query: what's actually asked, what's
    actually required, and the entry-level framing specifically - a bare
    "{role} interview questions" search skews toward senior content.
    """
    queries = [
        f"{role} fresher interview questions asked",
        f"entry level {role} technical interview questions",
        f"{role} fresher job description required skills",
    ]
    results: list[dict] = []
    for q in queries:
        try:
            results.extend(await _tavily_search(q, settings.research_max_results))
        except Exception:  # noqa: BLE001
            logger.exception("tavily search failed for %r", q)

    seen: set[str] = set()
    digest_parts: list[str] = []
    sources: list[str] = []
    for res in results:
        url = res.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        title = res.get("title", "")
        content = (res.get("content", "") or "")[:1200]
        digest_parts.append(f"SOURCE: {title} ({url})\n{content}")
        sources.append(url)

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
  they contain any, verbatim or lightly cleaned up. Empty list if the
  sources gave you nothing concrete to quote - do not invent questions to
  fill this field.
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
                    role=role, mode_name=mode.name, digest_block=_digest_block(digest)
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

    if not settings.research_enabled or not settings.tavily_api_key:
        try:
            brief = await _distill(role, mode, digest="")
        except Exception:  # noqa: BLE001
            logger.exception("could not build a role brief without research")
            return RoleBrief(grounded=False)
        brief.grounded = False
        return brief

    digest, sources = "", []
    try:
        digest, sources = await _gather_raw(role)
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
