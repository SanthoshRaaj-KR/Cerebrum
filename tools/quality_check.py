"""Run scripted interviews against a running backend and print transcripts.

    python tools/quality_check.py                 # realistic mixed answers
    python tools/quality_check.py hostile         # wrong claims, does it push back?
    python tools/quality_check.py modes           # plan + opener for every mode

Interview quality lives almost entirely in prompt wording, which means it
regresses silently - a change that reads like an improvement can quietly
stop the interviewer challenging bad answers, and nothing fails. This
replays fixed candidates so the transcripts can be compared by eye after
any prompt change.

The `hostile` scenario is the important one. Every answer contains a claim
a real interviewer would stop on (plaintext passwords, "POST is more
secure than GET", "indexes slow down the database"). If the transcript
shows the interviewer moving politely to its next planned question, the
reactive logic in interviewer.py has broken.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("INTERVIEW_AGENT_URL", "http://localhost:7332")

RESUME = """Santhosh Raaj K R - B.Tech Computer Science, 2025

PROJECTS
Friday AI - a personal assistant over Gmail and Google Calendar. FastAPI
backend with a WebSocket bridge to a Next.js console, an LLM agent loop
and a sandboxed tool registry. Python, OpenAI API, SQLite.
Algo Lens - visualises sorting and graph algorithms step by step. React.

SKILLS
Python, FastAPI, React, PostgreSQL, Docker, Git, LangChain
"""

# Strong, thin, an honest "I don't know", a skip, a confident error, then
# strong again - enough range to see whether grading discriminates and
# whether the interviewer adapts to each.
REALISTIC = [
    "Friday AI is a personal assistant I built. The backend is FastAPI and it "
    "talks to a Next.js console over a WebSocket so the assistant can push "
    "messages without the browser polling. The interesting part was the agent "
    "loop: the model gets tool schemas, and I check every tool call against an "
    "allowlist in config before dispatching, so a hallucinated tool name can't "
    "reach real code. SQLite because it's a single-user local tool.",
    "I used WebSockets because I wanted the server to push. Polling would have "
    "worked but it wastes requests.",
    "I don't really know that one, sorry.",
    "",
    "Indexes make everything faster so I'd add indexes on all the columns. "
    "There's no real downside, that's why databases have them.",
    "I'd use Redis with a TTL and check it before hitting the database. The "
    "tricky part is invalidation - if the row changes before the TTL expires "
    "you serve stale data, so for anything the user just edited I'd write "
    "through or delete the key on write rather than waiting for expiry.",
]

# Every one of these should be challenged by name.
HOSTILE = [
    "I built an e-commerce backend. I chose MongoDB because it's web scale and "
    "handles any amount of traffic.",
    "For checkout I just used a normal database write. If two people buy the "
    "last item at the same time it's fine, that basically never happens.",
    "I store the user's password in the database so I can email it to them if "
    "they forget it.",
    "I made every endpoint a POST because POST is more secure than GET.",
    "I don't use indexes because they slow down the database.",
    "For scaling I'd just buy a bigger server. Horizontal scaling is "
    "over-engineering.",
]


def post(path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def run(mode: str, answers: list[str], label: str, resume: str = RESUME) -> None:
    post("/api/session/reset")
    print("=" * 76)
    print(f"{label}   [{mode}]")
    print("=" * 76)

    st = post(
        "/api/session/start",
        {"mode": mode, "role": "Backend Engineer", "level": "Fresher", "resume": resume},
    )
    print("PLAN:", " -> ".join(p["short"] for p in st["plan"]), "\n")

    for i in range(st["total"]):
        turn = st["turns"][i]
        ans = answers[i] if i < len(answers) else ""
        skipped = not ans

        print(f"Q{i + 1}  {turn['question']}")
        print(f"    A: {'(skipped)' if skipped else ans[:180]}")

        st = post("/api/session/answer", {"text": ans, "skipped": skipped})
        g = st["turns"][i]["grade"]
        dims = "  ".join(f"{r['name']} {r['score']}" for r in g["rubric"])
        print(f"    {g['score']}/10  {g['verdict']}   [{dims}]")
        print(f"    worked : {g['strength']}")
        print(f"    missing: {g['gap']}\n")
        if st["finished"]:
            break

    rep = post("/api/session/report")
    print(f"AVERAGE {rep['average']}   {rep['report']['headline']}")
    for n in rep["report"]["notes"]:
        print("  -", n)
    print()


def survey() -> None:
    """Plan and opening question for every mode, to check they're actually
    different interviews rather than one wearing different hats."""
    modes = [m["key"] for m in post_get("/api/health")["system"]["modes"]]
    resume = (
        "B.Tech CS 2025. Built a RAG chatbot over PDFs with LangChain and "
        "Pinecone, and an e-commerce API in FastAPI."
    )
    for m in modes:
        post("/api/session/reset")
        st = post(
            "/api/session/start",
            {"mode": m, "role": "Engineer", "level": "Fresher", "resume": resume},
        )
        print(f"[{m}]")
        print("  plan:", " | ".join(p["short"] for p in st["plan"]))
        print("  Q1  :", st["turns"][0]["question"][:150], "\n")


def post_get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read())


def main() -> int:
    scenario = sys.argv[1] if len(sys.argv) > 1 else "realistic"
    try:
        post_get("/api/health")
    except (urllib.error.URLError, OSError) as exc:
        print(f"backend not reachable at {BASE}: {exc}", file=sys.stderr)
        print("start it with `docker compose up` first.", file=sys.stderr)
        return 1

    if scenario == "hostile":
        run(
            "sde_backend",
            HOSTILE,
            "HOSTILE - every answer contains a claim that must be challenged",
            resume="B.Tech CS 2025. Built an e-commerce backend with Django and MongoDB.",
        )
    elif scenario == "modes":
        survey()
    else:
        run("sde_backend", REALISTIC, "REALISTIC - mixed-quality answers")

    post("/api/session/reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
