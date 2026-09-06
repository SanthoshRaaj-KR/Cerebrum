"""Run scripted interviews against a running backend and print transcripts.

    python tools/quality_check.py live               # sit the interview yourself
    python tools/quality_check.py                    # realistic mixed answers
    python tools/quality_check.py hostile            # wrong claims, does it push back?
    python tools/quality_check.py modes              # research brief + opener for every mode
    python tools/quality_check.py hostile --max-questions 6

Interview quality lives almost entirely in prompt wording, which means it
regresses silently - a change that reads like an improvement can quietly
stop the interviewer challenging bad answers, and nothing fails. This
replays fixed candidates so the transcripts can be compared by eye after
any prompt change.

The `hostile` scenario is the important one. Every answer contains a claim
a real interviewer would stop on (plaintext passwords, "POST is more
secure than GET", "indexes slow down the database"). If the transcript
shows the interviewer moving politely to its next question, the reactive
logic in interviewer.py has broken.

`--max-questions` overrides interview.max_questions for the session
(default below) - there's no clock any more, but a scripted run of a dozen
fixed answers doesn't need the full coverage-driven length either.

Every run prints which models and which coordinator produced it. Flipping
interviewer.coordinator between `code` and `agent` in config.yaml and
diffing two `hostile` transcripts is how you tell whether the LLM main
agent is actually interviewing better than the deterministic loop, or just
costing three extra round-trips a question.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("INTERVIEW_AGENT_URL", "http://localhost:7332")

DEFAULT_TEST_CAP = 10
# Runaway guard only - the per-session maxQuestions cap should end things
# well before this.
MAX_TEST_TURNS = 30

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
# strong again - enough range to see whether the interviewer discriminates
# and adapts to each, now that nothing is scored until the very end.
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
    "For rate limiting I'd use a token bucket at the gateway - refill at a "
    "fixed rate, reject once it's empty.",
    "I'd paginate with a cursor rather than offset, because offset re-scans "
    "everything before the page on every request and rows shifting under you "
    "gives duplicates or gaps.",
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

# Any of these appearing in a question the interviewer asks is a scoring
# leak - nothing evaluative should reach the candidate until the report.
_LEAK_PATTERN = re.compile(
    r"\b\d+(\.\d+)?\s*/\s*10\b|\bmissing\s*:|\bscore\s*:|\bverdict\s*:", re.IGNORECASE
)


def post(path: str, payload: dict | None = None) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload or {}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=240) as r:
        return json.loads(r.read())


def post_get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read())


def _check_leak(question: str) -> None:
    if _LEAK_PATTERN.search(question):
        print(f"    !! POSSIBLE SCORE LEAK in question text: {question[:200]}")


def _banner() -> str:
    """What actually ran, so two transcripts can be compared honestly -
    especially when A/B-ing interviewer.coordinator between `code` and
    `agent`, which is invisible from the transcript alone."""
    try:
        sysinfo = post_get("/api/health")["system"]
    except Exception:  # noqa: BLE001
        return "(could not read /api/health)"
    return (
        f"ask={sysinfo.get('model')}  judge={sysinfo.get('scorerModel')}  "
        f"turns-driven-by={sysinfo.get('coordinator')}"
    )


def run(
    mode: str,
    answers: list[str],
    label: str,
    resume: str = RESUME,
    cap: int = DEFAULT_TEST_CAP,
) -> dict:
    post("/api/session/reset")
    print("=" * 76)
    print(f"{label}   [{mode}]  ({cap} question cap)")
    print(_banner())
    print("=" * 76)

    st = post(
        "/api/session/start",
        {
            "mode": mode,
            "role": "Backend Engineer",
            "level": "Fresher",
            "resume": resume,
            "maxQuestions": cap,
        },
    )
    brief = st.get("researchBrief") or {}
    print(
        f"research: grounded={brief.get('grounded')}  "
        f"competencies={', '.join(brief.get('competencies', [])) or '(none)'}"
    )
    print(f"sources : {len(brief.get('sources', []))}\n")

    i = 0
    while not st["finished"] and i < MAX_TEST_TURNS:
        turn = st["turns"][-1]
        _check_leak(turn["question"])
        ans = answers[i] if i < len(answers) else "I'm not totally sure - could you clarify what you're after?"
        skipped = not ans

        pc = st["pacing"]
        tag = "closing" if pc["closing"] else f"{pc['questionsAsked']}/{pc['maxQuestions']}"
        print(f"[{tag}] Q{i + 1}  {turn['question']}")
        print(f"    A: {'(skipped)' if skipped else ans[:180]}\n")

        st = post("/api/session/answer", {"text": ans, "skipped": skipped})
        i += 1

    if i >= MAX_TEST_TURNS and not st["finished"]:
        print(f"!! hit MAX_TEST_TURNS ({MAX_TEST_TURNS}) without coverage ending the interview\n")

    rep = post("/api/session/report")
    sc = rep["scorecard"]
    print(f"VERDICT {sc['verdict']}   SCORE {sc['score']}/10")
    print(f"  {sc['headline']}\n")
    for c in sc["competencies"]:
        print(f"    {c['status']:13} {c['name']}")
    if sc["strengths"]:
        print("\n  strengths:")
        for s in sc["strengths"]:
            print("   -", s)
    if sc["gaps"]:
        print("  gaps:")
        for g in sc["gaps"]:
            print("   -", g)
    print()
    return rep


def survey(cap: int = DEFAULT_TEST_CAP) -> None:
    """Research brief and opening question for every mode, to check they're
    actually different interviews rather than one wearing different hats,
    and that the opener is improvised rather than lifted verbatim from the
    real questions research.py found."""
    modes = [m["key"] for m in post_get("/api/health")["system"]["modes"]]
    resume = (
        "B.Tech CS 2025. Built a RAG chatbot over PDFs with LangChain and "
        "Pinecone, and an e-commerce API in FastAPI."
    )
    for m in modes:
        post("/api/session/reset")
        st = post(
            "/api/session/start",
            {"mode": m, "role": "Backend Engineer", "level": "Fresher", "resume": resume, "maxQuestions": cap},
        )
        brief = st.get("researchBrief") or {}
        opener = st["turns"][0]["question"]
        real_qs = {q.strip() for q in brief.get("realQuestions", [])}
        scripted = opener.strip() in real_qs

        print(f"[{m}]")
        print(f"  grounded    : {brief.get('grounded')}")
        print(f"  competencies: {', '.join(brief.get('competencies', []))}")
        print(f"  sources     : {len(brief.get('sources', []))}")
        print(f"  opener      : {opener[:150]}")
        print(f"  scripted?   : {'YES - REGRESSION' if scripted else 'no (improvised, good)'}\n")


def live() -> None:
    """Sit the interview yourself from the terminal."""
    modes = post_get("/api/health")["system"]["modes"]
    print("\n  Modes\n")
    for i, m in enumerate(modes, 1):
        print(f"   {i}. {m['name']}")
        print(f"      {m['blurb']}\n")

    while True:
        raw = input(f"  Pick a mode [1-{len(modes)}]: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(modes):
            mode = modes[int(raw) - 1]
            break

    role = input("  Target role  [Backend Engineer]: ").strip() or "Backend Engineer"
    level = input("  Level        [Fresher]: ").strip() or "Fresher"
    cap_raw = input("  Max questions [22]: ").strip()
    cap = int(cap_raw) if cap_raw.isdigit() else 22
    print("  Résumé - paste it, then a blank line (required):")
    resume = ""
    while not resume.strip():
        lines: list[str] = []
        while True:
            line = input()
            if not line:
                break
            lines.append(line)
        resume = "\n".join(lines)
        if not resume.strip():
            print("  ...a résumé is required now. Paste one:")

    print(f"\n  Reading up on what {role} interviews actually cover...\n")
    post("/api/session/reset")
    st = post(
        "/api/session/start",
        {"mode": mode["key"], "role": role, "level": level, "resume": resume, "maxQuestions": cap},
    )

    while not st["finished"]:
        turn = st["turns"][-1]
        pc = st["pacing"]
        tag = "wrapping up" if pc["closing"] else f"question {pc['questionsAsked']} of up to {pc['maxQuestions']}"
        print("=" * 72)
        print(f"  [{tag}]\n")
        print(f"  {turn['question']}\n")
        print("  Your answer - blank line to submit, or 'skip':")

        buf: list[str] = []
        while True:
            line = input()
            if not line:
                break
            buf.append(line)
        text = "\n".join(buf).strip()
        skipped = not text or text.lower() == "skip"

        print("\n  ...\n")
        st = post("/api/session/answer", {"text": "" if skipped else text, "skipped": skipped})

    rep = post("/api/session/report")
    sc = rep["scorecard"]
    print("=" * 72)
    print(f"\n  {sc['headline']}")
    print(f"  Verdict {sc['verdict']}   Score {sc['score']}/10\n")
    for c in sc["competencies"]:
        print(f"    {c['status']:13} {c['name']}")
    print("\n  strengths:")
    for s in sc["strengths"]:
        print("   -", s)
    print("  gaps:")
    for g in sc["gaps"]:
        print("   -", g)
    print("  notes:")
    for n in sc["notes"]:
        print("   -", n)
    print()


def main() -> int:
    args = sys.argv[1:]
    cap = DEFAULT_TEST_CAP
    if "--max-questions" in args:
        idx = args.index("--max-questions")
        try:
            cap = int(args[idx + 1])
        except (IndexError, ValueError):
            print("--max-questions needs an integer argument", file=sys.stderr)
            return 1
        del args[idx : idx + 2]

    scenario = args[0] if args else "realistic"

    try:
        post_get("/api/health")
    except (urllib.error.URLError, OSError) as exc:
        print(f"backend not reachable at {BASE}: {exc}", file=sys.stderr)
        print("start it with `docker compose up` first.", file=sys.stderr)
        return 1

    if scenario == "live":
        try:
            live()
        except (KeyboardInterrupt, EOFError):
            print("\n  ended.\n")
            post("/api/session/reset")
        return 0

    if scenario == "hostile":
        run(
            "sde_backend",
            HOSTILE,
            "HOSTILE - every answer contains a claim that must be challenged",
            resume="B.Tech CS 2025. Built an e-commerce backend with Django and MongoDB.",
            cap=cap,
        )
    elif scenario == "modes":
        survey(cap=cap)
    else:
        run("sde_backend", REALISTIC, "REALISTIC - mixed-quality answers", cap=cap)

    post("/api/session/reset")
    return 0


if __name__ == "__main__":
    sys.exit(main())
