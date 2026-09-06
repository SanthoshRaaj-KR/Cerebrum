"""Web search for role research, with a provider fallback chain.

research.py needs a handful of search hits to ground the role brief; it
does not care which engine produced them. This module tries the configured
providers in order (Tavily, then Brave) and hands back whatever the first
usable one returns. If none are usable, research.py falls back to a
model-knowledge-only brief - a search outage never costs the candidate
their session.

A provider counts as "unusable" when its key is missing or rejected, or
when every query against it errored - not when it merely returned few
results. The chain logs which provider actually served the brief, so a
quiet Tavily outage shows up in the logs instead of silently degrading
grounding.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

from interview_agent.config import settings

logger = logging.getLogger("interview_agent.search")

# Per request, not per provider: one slow query must not stall the rest,
# and a dead provider should hand off quickly rather than after a full
# three-query wait on the old 20s-each timeout.
REQUEST_TIMEOUT = 12.0

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class SearchHit:
    title: str
    url: str
    content: str


@dataclass
class SearchOutcome:
    hits: list[SearchHit]
    provider: str | None  # None when no provider was usable


class SearchProviderError(Exception):
    """A whole provider is unusable (bad key, or every query failed)."""


# -- providers -------------------------------------------------------------


async def _tavily(queries: list[str], max_results: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    errors = 0
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        for q in queries:
            try:
                r = await http.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.tavily_api_key,
                        "query": q,
                        "search_depth": "basic",
                        "max_results": max_results,
                        "include_answer": False,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("tavily query %r failed: %s", q, exc)
                errors += 1
                continue
            if r.status_code in (401, 403):
                raise SearchProviderError(f"tavily key rejected ({r.status_code})")
            if r.status_code != 200:
                logger.warning("tavily query %r: HTTP %s", q, r.status_code)
                errors += 1
                continue
            for res in r.json().get("results", []):
                hits.append(
                    SearchHit(
                        title=str(res.get("title", "")),
                        url=str(res.get("url", "")),
                        content=str(res.get("content", "") or ""),
                    )
                )
    if queries and errors == len(queries):
        raise SearchProviderError("every tavily query failed")
    return hits


async def _brave(queries: list[str], max_results: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    errors = 0
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as http:
        for q in queries:
            try:
                r = await http.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": q, "count": max_results},
                    headers={
                        "Accept": "application/json",
                        "X-Subscription-Token": settings.brave_api_key,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("brave query %r failed: %s", q, exc)
                errors += 1
                continue
            if r.status_code in (401, 403):
                raise SearchProviderError(f"brave key rejected ({r.status_code})")
            if r.status_code != 200:
                logger.warning("brave query %r: HTTP %s", q, r.status_code)
                errors += 1
                continue
            for res in (r.json().get("web") or {}).get("results", []):
                # Brave wraps matched terms in <strong> in the description;
                # strip the markup before it goes into the distill prompt.
                hits.append(
                    SearchHit(
                        title=str(res.get("title", "")),
                        url=str(res.get("url", "")),
                        content=_TAG_RE.sub("", str(res.get("description", "") or "")),
                    )
                )
    if queries and errors == len(queries):
        raise SearchProviderError("every brave query failed")
    return hits


_Provider = Callable[[list[str], int], Awaitable[list[SearchHit]]]

# name -> (runner, "is this provider's key present?")
_PROVIDERS: dict[str, tuple[_Provider, Callable[[], bool]]] = {
    "tavily": (_tavily, lambda: bool(settings.tavily_api_key)),
    "brave": (_brave, lambda: bool(settings.brave_api_key)),
}


def configured_providers() -> list[str]:
    """The providers to actually try, in order: the ones named in
    config.yaml's research.providers that also have a key in .env. Unknown
    names are dropped with a warning."""
    out: list[str] = []
    for name in settings.research_providers:
        entry = _PROVIDERS.get(name)
        if entry is None:
            logger.warning("unknown research provider %r in config.yaml", name)
            continue
        if entry[1]():
            out.append(name)
    return out


def any_provider_configured() -> bool:
    return bool(configured_providers())


async def gather(queries: list[str], max_results: int) -> SearchOutcome:
    """Run the queries against each configured provider in turn; return the
    hits from the first one that yields any. Empty outcome (provider=None)
    if the chain is exhausted - the caller degrades to model knowledge."""
    for name in configured_providers():
        run = _PROVIDERS[name][0]
        try:
            found = await run(queries, max_results)
        except SearchProviderError as exc:
            logger.warning("search provider %s unusable, falling back: %s", name, exc)
            continue
        except Exception:  # noqa: BLE001
            logger.exception("search provider %s crashed, falling back", name)
            continue
        if found:
            logger.info("role research served by %s (%d hits)", name, len(found))
            return SearchOutcome(hits=found, provider=name)
        logger.info("search provider %s returned no hits, trying next", name)
    return SearchOutcome(hits=[], provider=None)
