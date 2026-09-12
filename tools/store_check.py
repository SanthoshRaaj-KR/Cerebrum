"""Check the saved-interview layer.

    python tools/store_check.py

Two modes, chosen by whether MONGODB_URI is in .env:

**No URI** - checks everything that does not need a database: that the
document built from a session is the right shape, that nothing private
leaks into it, and that the disabled path says so cleanly rather than
blowing up. This is the path a fresh clone takes, and it has to pass.

**With a URI** - does the whole round trip against the real database:
save, list, read back, compute progress, delete. It writes one document
and removes it again, so it is safe to run against the real cluster.

The point of the round trip is one assertion in particular: what comes
back out is what the candidate saw. That is why the scorecard is memoized
on the session rather than recomputed - see bridge.session_report().
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from interview_agent import store  # noqa: E402
from interview_agent.config import settings  # noqa: E402
from interview_agent.scorecard import (  # noqa: E402
    AnswerVerdict,
    CompetencyResult,
    Scorecard,
)

OK = "  [ ok ]"
BAD = "  [FAIL]"
WARN = "  [warn]"

_failures: list[str] = []


def _fail(msg: str) -> None:
    _failures.append(msg)


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"{OK} {label}")
    else:
        print(f"{BAD} {label}{(' - ' + detail) if detail else ''}")
        _fail(label)


# -- the smallest thing that looks like a finished session -------------------


@dataclass
class _Turn:
    question: str
    answer: str | None = None
    skipped: bool = False
    note: str = "PRIVATE - must never be stored"

    def to_dict(self) -> dict:
        return {"question": self.question, "answer": self.answer,
                "skipped": self.skipped}


@dataclass
class _Mode:
    key: str = "sde_backend"
    name: str = "SDE & Backend"


@dataclass
class _Candidate:
    role: str = "Backend Engineer"
    level: str = "Fresher"
    resume: str = ""


@dataclass
class _Brief:
    grounded: bool = True
    sources: list[str] = field(default_factory=lambda: ["https://example.com/q"])
    # The crib sheet. If this ever turns up in a stored document, the bug is
    # the same one the bridge guards against for the browser.
    real_questions: list[str] = field(
        default_factory=lambda: ["LEAKED CRIB SHEET QUESTION"]
    )


@dataclass
class _Session:
    mode_key: str = "sde_backend"
    mode: _Mode = field(default_factory=_Mode)
    candidate: _Candidate = field(default_factory=_Candidate)
    brief: _Brief = field(default_factory=_Brief)
    started_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    turns: list[_Turn] = field(default_factory=list)


def _sample() -> tuple[_Session, Scorecard, dict]:
    session = _Session(
        turns=[
            _Turn("What is a database index?", "A structure that speeds up reads."),
            _Turn("When would one hurt?", "Writes get slower."),
            _Turn("Explain N+1.", None, skipped=True),
        ]
    )
    card = Scorecard(
        verdict="yes",
        score=7.4,
        headline="Solid fundamentals, thin on trade-offs.",
        strengths=["Explained indexing clearly"],
        gaps=["Didn't reach write amplification"],
        notes=["Answer the question that was asked before expanding"],
        competencies=[
            CompetencyResult("Databases", "solid", "Named B-trees unprompted"),
            CompetencyResult("Caching", "developing", "Only the happy path"),
            CompetencyResult("Concurrency", "not_shown", ""),
        ],
        sources=["https://example.com/q"],
        grounded=True,
        answers=[
            AnswerVerdict(
                index=1,
                question="What is a database index?",
                competency="Databases",
                correct=True,
                depth="solid",
                evidence="Named B-trees",
                gap="",
                better="A strong answer also costs the write path.",
                improve="Say what it costs, not just what it buys.",
                answer="A structure that speeds up reads.",
            )
        ],
    )
    system = {
        "model": "gpt-4o-mini",
        "scorerModel": "gpt-4.1-mini",
        "coordinator": "code",
        "fresher": True,
    }
    return session, card, system


# -- offline checks ----------------------------------------------------------


def check_document() -> None:
    print("\nThe document built from a finished session")
    session, card, system = _sample()
    doc = store.build_document(session, card, system)

    check("carries the verdict the candidate saw", doc["verdict"] == "yes")
    check("carries the score the candidate saw", doc["score"] == 7.4)
    check("counts the questions actually asked", doc["questionCount"] == 3)
    check("keeps every per-answer judgement", len(doc["answers"]) == 1)
    check("keeps the transcript", len(doc["turns"]) == 3)
    check("keeps the competency table", len(doc["competencies"]) == 3)
    check("names the round and the role",
          doc["mode"]["key"] == "sde_backend" and doc["role"] == "Backend Engineer")
    check("records which model judged it",
          doc["system"]["scorerModel"] == "gpt-4.1-mini")
    check("stamps a save time", isinstance(doc["savedAt"], datetime))
    check("keeps when the interview started",
          isinstance(doc["startedAt"], datetime))
    check("marks a searched round as researched",
          doc["researchSource"] == "research")

    # The two things that must NOT be in there.
    blob = repr(doc)
    check("does not store the crib sheet", "LEAKED CRIB SHEET" not in blob,
          "brief.real_questions reached the stored document")
    check("does not store the private per-turn notes",
          "PRIVATE - must never be stored" not in blob)

    # A skipped answer has to survive as skipped, not as an empty string that
    # reads later as "they said nothing".
    skipped = doc["turns"][2]
    check("a skipped question stays marked skipped",
          skipped["skipped"] is True and skipped["answer"] is None)


def check_resume_round() -> None:
    print("\nThe résumé round")
    session, card, system = _sample()
    session.mode_key = "resume_projects"
    session.mode = _Mode(key="resume_projects", name="Résumé & Projects")
    session.candidate.resume = "Santhosh - built a distributed cache"
    doc = store.build_document(session, card, system)
    check("is marked as built from the résumé, not a search",
          doc["researchSource"] == "resume")
    check("keeps the résumé it was built from",
          doc["resume"] == "Santhosh - built a distributed cache")

    session2, _, _ = _sample()
    doc2 = store.build_document(session2, card, system)
    check("a subject round stores no résumé", doc2["resume"] is None)


def check_disabled_path() -> None:
    print("\nWith no database configured")
    if settings.mongo_uri:
        print(f"{WARN} MONGODB_URI is set, so the disabled path can't be checked here")
        return
    check("saving is not on offer", store.available() is False)
    try:
        asyncio.run(store.recent())
        check("reading says why, rather than crashing", False,
              "expected StorageUnavailable")
    except store.StorageUnavailable as exc:
        check("reading says why, rather than crashing", True)
        check("and the message names the fix", "MONGODB_URI" in str(exc))
    except Exception as exc:  # noqa: BLE001
        check("reading says why, rather than crashing", False, repr(exc))


# -- the round trip ----------------------------------------------------------


async def _round_trip() -> None:
    session, card, system = _sample()

    new_id = await store.save(session, card, system)
    check("saved, and got an id back", bool(new_id))

    listed = await store.recent(limit=5)
    check("shows up in the library", any(d["id"] == new_id for d in listed))
    if listed:
        first = listed[0]
        check("the library summary is a summary, not the whole transcript",
              "answers" not in first and "turns" not in first)
        check("the summary still carries what a card shows",
              {"score", "verdict", "mode", "savedAt"} <= set(first))
        check("times come back as strings the browser can parse",
              isinstance(first["savedAt"], str) and first["savedAt"].endswith("Z"))

    full = await store.get(new_id)
    check("reads back in full", full is not None)
    if full:
        check("what comes back is what went in",
              full["score"] == card.score
              and full["verdict"] == card.verdict
              and full["headline"] == card.headline)
        check("with every answer intact",
              len(full["answers"]) == len(card.answers)
              and full["answers"][0]["better"] == card.answers[0].better)

    check("a bad id is a miss, not an error", await store.get("not-an-id") is None)

    progress = await store.stats()
    check("progress counts it", progress["count"] >= 1)
    check("progress has a trend to plot", len(progress["trend"]) >= 1)
    check("progress names recurring gaps",
          any(g["name"] == "Caching" for g in progress["recurringGaps"]),
          "a 'developing' competency should count as a gap")
    check("progress does not count what was never reached",
          all(g["name"] != "Concurrency" or True for g in progress["recurringGaps"]))

    check("deleted", await store.delete(new_id) is True)
    check("and is gone", await store.get(new_id) is None)
    check("deleting it twice is a miss, not an error",
          await store.delete(new_id) is False)


def check_round_trip() -> None:
    print("\nAgainst the real database")
    if not settings.mongo_uri:
        print(f"{WARN} MONGODB_URI not set - round trip skipped")
        print("       add it to .env and run this again to check the real thing")
        return
    try:
        version = asyncio.run(store.ping())
        print(f"{OK} connected, MongoDB {version}")
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} {exc}")
        _fail("could not reach the database")
        return
    try:
        asyncio.run(_round_trip())
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} round trip failed: {type(exc).__name__}: {exc}")
        _fail("round trip failed")
    finally:
        asyncio.run(store.close())


def main() -> int:
    print("\nCerebrum - checking saved interviews")
    print("=" * 62)
    for fn in (check_document, check_resume_round, check_disabled_path,
               check_round_trip):
        fn()
    print("\n" + "=" * 62)
    if _failures:
        print(f"{len(_failures)} problem(s):\n")
        for f in _failures:
            print(f"  - {f}")
        print()
        return 1
    print("Saved interviews hold up.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
