"""Saved interviews.

The interview itself is still ephemeral - the session lives in the bridge
process and dies with it. This is the one deliberate exception: when the
candidate presses Store on a finished report, the whole thing goes to
MongoDB so they can read it again later and see whether they are actually
getting better.

Two properties this module is built around:

**Optional.** With no MONGODB_URI, `available()` is False and the console
never offers the button. Nothing else changes. A missing database is not
an error state, it is the default one.

**Never fatal.** A save that fails must not take the report down with it -
the report is the thing the candidate came for, and losing it because a
cluster was unreachable would be the worst possible trade. Failures raise
StorageError, which the bridge turns into a message on the button rather
than a broken screen.

What gets stored is the scorecard the candidate actually saw, not a fresh
one. See InterviewSession.scorecard for why that distinction matters.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

# How many saved interviews the library asks for at once. Generous enough
# that nobody paginates in practice, small enough that the progress header
# is computed over a bounded set.
DEFAULT_LIMIT = 60
MAX_LIMIT = 200


class StorageError(RuntimeError):
    """Saving or reading a stored interview did not work."""


class StorageUnavailable(StorageError):
    """No database is configured. Distinct from a failure: nothing is wrong."""


_client: Any = None
_indexed = False


def available() -> bool:
    """Whether saving is on offer. Cheap - no network."""
    return settings.storage_enabled


def _collection():
    """The interviews collection, connecting on first use.

    AsyncMongoClient does not connect eagerly, so building it is cheap and
    a bad URI surfaces on the first real operation rather than at import -
    which is what we want, since import happens whether or not anyone ever
    presses the button.
    """
    global _client
    if not available():
        raise StorageUnavailable(
            "no MONGODB_URI in .env, so there is nowhere to save this"
        )
    if _client is None:
        try:
            from pymongo import AsyncMongoClient
        except ImportError as exc:  # pragma: no cover - dependency is pinned
            raise StorageError(
                "pymongo is not installed - run: pip install -r requirements.txt"
            ) from exc
        # A short timeout because this sits behind a button press. Waiting
        # 30 seconds for the default server-selection timeout to expire
        # reads as a hang, and the honest answer arrives just as well at 5.
        _client = AsyncMongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            appname="cerebrum",
        )
    return _client[settings.storage_database][settings.storage_collection]


async def _ensure_indexes(col) -> None:
    """Both indexes the library actually queries by. Idempotent, and once
    per process - create_index on an existing index is a no-op server-side,
    but it is still a round-trip we do not need on every save."""
    global _indexed
    if _indexed:
        return
    try:
        await col.create_index([("savedAt", -1)])
        await col.create_index([("mode.key", 1), ("savedAt", -1)])
        _indexed = True
    except Exception:  # noqa: BLE001 - an index is an optimisation, not a feature
        logger.exception("could not create interview indexes")


def _wrap(exc: Exception) -> StorageError:
    """Mongo's own errors name drivers and topologies. The person reading
    this pressed a button on a report."""
    from pymongo.errors import ServerSelectionTimeoutError

    if isinstance(exc, ServerSelectionTimeoutError):
        return StorageError(
            "couldn't reach the database - check MONGODB_URI, and that this "
            "machine's IP is allowed if you're on Atlas"
        )
    # The type alone is not enough to act on - it sent me looking in the
    # wrong place once already. Truncated because a driver error can run to
    # several lines of topology description, and this ends up on a button.
    detail = str(exc).strip().splitlines()[0][:140] if str(exc).strip() else ""
    return StorageError(
        f"the database refused that: {type(exc).__name__}"
        + (f" - {detail}" if detail else "")
    )


# -- writing -----------------------------------------------------------------


def build_document(session, card, system: dict[str, Any]) -> dict[str, Any]:
    """Flatten a finished session and its scorecard into one document.

    Deliberately a snapshot rather than a set of references: a saved
    interview has to keep rendering identically in a year, after the
    prompts have moved on and the model has been swapped. That includes
    `system`, so an old report can say which model judged it.

    What is NOT stored: brief.real_questions (the crib sheet - it is kept
    out of the browser for the same reason), the private per-turn
    AnswerNotes, and the coverage ledger. The scorecard's per-answer
    verdicts already carry everything the report renders.
    """
    from . import gateway

    brief = getattr(session, "brief", None)
    payload = card.to_dict()
    # Same derivation the bridge uses for the live report: the résumé round
    # has no external syllabus, so its brief came from the CV via gateway.py.
    source = "resume" if session.mode_key == gateway.MODE_KEY else "research"

    return {
        "savedAt": datetime.now(timezone.utc),
        "startedAt": getattr(session, "started_at", None),
        "mode": {"key": session.mode.key, "name": session.mode.name},
        "role": session.candidate.role,
        "level": session.candidate.level,
        "verdict": payload["verdict"],
        "score": payload["score"],
        "headline": payload["headline"],
        "questionCount": len(session.turns),
        "strengths": payload["strengths"],
        "gaps": payload["gaps"],
        "notes": payload["notes"],
        "competencies": payload["competencies"],
        "answers": payload["answers"],
        "turns": [t.to_dict() for t in session.turns],
        "sources": payload["sources"],
        "grounded": payload["grounded"],
        "researchSource": source if brief else None,
        # Kept so a résumé round stays self-contained - you can see which
        # version of the CV produced which interview.
        "resume": session.candidate.resume or None,
        "system": {
            "model": system.get("model"),
            "scorerModel": system.get("scorerModel"),
            "coordinator": system.get("coordinator"),
            "fresher": system.get("fresher"),
        },
    }


async def save(session, card, system: dict[str, Any]) -> str:
    """Store one finished interview. Returns its id."""
    col = _collection()
    await _ensure_indexes(col)
    doc = build_document(session, card, system)
    try:
        result = await col.insert_one(doc)
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not save interview")
        raise _wrap(exc) from None
    return str(result.inserted_id)


# -- reading -----------------------------------------------------------------

# The library grid needs a card's worth of each interview, not the whole
# transcript. Ten saved interviews' full answers is a lot of JSON to send
# so a grid can show a score.
_SUMMARY_FIELDS = {
    "savedAt": 1,
    "mode": 1,
    "role": 1,
    "verdict": 1,
    "score": 1,
    "headline": 1,
    "questionCount": 1,
}


def _out(doc: dict[str, Any]) -> dict[str, Any]:
    """ObjectId and datetime are not JSON. Ids become strings and times
    become ISO-8601 with an explicit Z, so the browser's Date parses them
    as UTC rather than guessing local."""
    doc = dict(doc)
    doc["id"] = str(doc.pop("_id"))
    for key in ("savedAt", "startedAt"):
        value = doc.get(key)
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            doc[key] = value.isoformat().replace("+00:00", "Z")
    return doc


async def recent(limit: int = DEFAULT_LIMIT, mode: str | None = None) -> list[dict]:
    """Summaries for the library, newest first."""
    col = _collection()
    query: dict[str, Any] = {}
    if mode:
        query["mode.key"] = mode
    limit = max(1, min(MAX_LIMIT, int(limit)))
    try:
        cursor = col.find(query, _SUMMARY_FIELDS).sort("savedAt", -1).limit(limit)
        return [_out(d) async for d in cursor]
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not list interviews")
        raise _wrap(exc) from None


async def get(interview_id: str) -> dict | None:
    """One interview in full, for re-reading the report."""
    from bson import ObjectId
    from bson.errors import InvalidId

    col = _collection()
    try:
        oid = ObjectId(interview_id)
    except (InvalidId, TypeError):
        return None      # a malformed id is a miss, not a server error
    try:
        doc = await col.find_one({"_id": oid})
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not read interview %s", interview_id)
        raise _wrap(exc) from None
    return _out(doc) if doc else None


async def delete(interview_id: str) -> bool:
    from bson import ObjectId
    from bson.errors import InvalidId

    col = _collection()
    try:
        oid = ObjectId(interview_id)
    except (InvalidId, TypeError):
        return False
    try:
        result = await col.delete_one({"_id": oid})
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not delete interview %s", interview_id)
        raise _wrap(exc) from None
    return result.deleted_count > 0


# -- progress ----------------------------------------------------------------


async def stats() -> dict[str, Any]:
    """What the library's header shows: are you getting better, where are
    you strong, and what keeps coming back as a gap.

    Computed here rather than in the browser because the recurring-gaps
    tally needs every interview's competency list, and shipping all of
    those to draw one list would undo the point of the summary projection.
    """
    col = _collection()
    try:
        cursor = (
            col.find({}, {"savedAt": 1, "mode": 1, "score": 1, "verdict": 1,
                          "competencies": 1})
            .sort("savedAt", -1)
            .limit(MAX_LIMIT)
        )
        docs = [d async for d in cursor]
    except Exception as exc:  # noqa: BLE001
        logger.exception("could not compute progress")
        raise _wrap(exc) from None

    if not docs:
        return {"count": 0, "trend": [], "byMode": [], "recurringGaps": []}

    # Oldest first: a trend line that runs backwards is a trap.
    ordered = list(reversed(docs))

    trend = [
        {
            "at": _out(d)["savedAt"],
            "score": float(d.get("score") or 0),
            "mode": (d.get("mode") or {}).get("name", ""),
            "id": str(d["_id"]),
        }
        for d in ordered
    ]

    by_mode: dict[str, dict[str, Any]] = {}
    for d in docs:
        mode = d.get("mode") or {}
        key = mode.get("key") or "unknown"
        row = by_mode.setdefault(
            key, {"key": key, "name": mode.get("name", key), "count": 0, "total": 0.0}
        )
        row["count"] += 1
        row["total"] += float(d.get("score") or 0)
    for row in by_mode.values():
        row["average"] = round(row.pop("total") / max(1, row["count"]), 1)

    # A competency counts as a recurring gap when it came back as anything
    # other than solid. "not_covered" is excluded: it means the interview
    # never got to it, which is not the same as not having it.
    gaps: dict[str, int] = {}
    for d in docs:
        for comp in d.get("competencies") or []:
            if comp.get("status") in ("developing", "not_shown"):
                name = comp.get("name", "").strip()
                if name:
                    gaps[name] = gaps.get(name, 0) + 1

    recurring = sorted(gaps.items(), key=lambda kv: (-kv[1], kv[0]))[:8]

    scores = [float(d.get("score") or 0) for d in docs]
    return {
        "count": len(docs),
        "average": round(sum(scores) / len(scores), 1),
        "best": round(max(scores), 1),
        "trend": trend,
        "byMode": sorted(by_mode.values(), key=lambda r: -r["count"]),
        "recurringGaps": [{"name": n, "times": c} for n, c in recurring],
    }


async def ping() -> str:
    """Used by doctor.py. Returns the server version, or raises."""
    col = _collection()
    try:
        info = await col.database.client.server_info()
    except Exception as exc:  # noqa: BLE001
        raise _wrap(exc) from None
    return str(info.get("version", "?"))


async def close() -> None:
    """Let the bridge's lifespan shut the pool down cleanly."""
    global _client, _indexed
    if _client is not None:
        try:
            await _client.close()
        except Exception:  # noqa: BLE001
            logger.exception("could not close the mongo client")
        _client = None
        _indexed = False
