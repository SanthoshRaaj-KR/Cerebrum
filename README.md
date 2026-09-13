# Cerebrum

**A mock technical interviewer that behaves like one.** Pick a round —
that is the whole of setup — and it runs a real interview of about half an
hour. No question list. No script to fall back to. Before it asks anything
it goes and looks up what that role is actually being asked *right now*,
turns that into the areas worth examining, and from there it reacts to
what you just said.

Answer well and it goes **up** on that same ground — the trade-off behind
your choice, the case where your answer stops working. Answer badly and it
comes at the idea from a more concrete angle to find what you *do* have,
instead of piling on a gap it has already found. It ends when it has a read
on everything worth asking about, not when a timer runs out.

Nothing is scored to your face. No score, no rubric, no hint of a verdict
mid-interview — because no real interviewer grades you while you're still
in the room. It all arrives at the end, as a report that goes through every
answer one at a time: what you said, what it showed, what was missing, what
a strong answer to that question sounds like, and one thing to do
differently next time.

---

## Why this isn't another question generator

Most "AI interview" tools generate ten questions, read them out in order,
and score you on keywords. Five decisions make this one different, and each
of them is enforced in code rather than asked for in a prompt.

**The round is the role.** Picking "SDE & Backend" already says Backend
Engineer. Each round module carries its own `DEFAULT_ROLE`, and that is
what gets researched — so five of the six rounds start on a single click
with nothing typed in. Only Résumé & Projects asks for anything else, and
only because a résumé is that round's entire syllabus.

**The questions are current, not remembered.** `research.py` searches what
that role is being asked this year, distils it into a competency map with a
`fresher_bar` for each — what counts as *having* it at entry level, not at
a senior level — and keeps real questions found in the wild purely for
calibration. Those real questions are never rendered to the browser and
never read out; shipping them mid-interview would hand you the answer key.

**Difficulty moves with you, in both directions.** Every competency carries
a rung: `basics → applied → edge cases and trade-offs`. An answer that
genuinely holds up climbs it — the next question on that ground is harder
and often quotes your own words back at you. The rung never falls, so a bad
answer at `applied` gets you a different angle at the same level rather
than a demotion. That distinction is the whole difference between an
interviewer probing for your ceiling and one grinding on your floor.

**It ends when it's satisfied, not when the clock says.** There is no
timer. The interview runs until every competency has a read — shown at
thin-or-better, or pushed until the edge of what you know was found — with
a question budget as the only floor and ceiling. Nothing is ever scored on
how long an answer took.

**The judging is real, and it happens off the critical path.** As each
answer comes in, a stronger model judges it properly in the background
while you're already reading the next question. A verdict of `wrong` — the
one thing ever put to your face — gets a second focused opinion before it
counts, because telling a candidate they're wrong when they're right is the
worst thing this system can do.

**And it keeps them, if you ask it to.** One report tells you how a round
went. A shelf of them tells you whether the thing you were told to work on
last time actually moved — which is the only question a practice tool is
really for. Press **Store** on a finished report and it goes to MongoDB;
the library then shows your score trend, your strongest rounds, and the
competencies that keep coming back as gaps. Nothing is ever saved without
that press, and nothing mid-interview is saved at all.

---

## The shape of an interview

```
  pick a round                  the round IS the role. Researched before
      │                         question one - what that role is asked right
      │                         now (Tavily → Brave), distilled into a
      ▼                         competency map with a fresher bar on each
  the interview loop            one turn at a time, full history in context
      │
      ├── evaluator             how did that answer go, privately - and is a
      │                         `wrong` call worth a second opinion first
      ├── the move              challenge / redirect / dig / ease_off / advance
      ├── questionnaire         writes the one question you actually see
      └── coverage ledger       which competencies still have nothing shown,
      │                         and how hard each has been pushed. A strong
      │                         answer buys a harder question on that ground
      │                         next time. When nothing is left open, it wraps
      ▼
  the report                    built from per-answer judgements made in the
                                background as you went - a verdict, then every
                                question taken apart, calibrated to "would a
                                company hire this fresher", not a senior bar
```

### The six rounds

| Round | Researched as | What it's for |
|---|---|---|
| **Résumé & Projects** | *your own work* | Your own work, pulled apart one level deeper than you expect. The near-universal opening round |
| **SDE & Backend** | Backend Engineer | APIs, databases, caching and the code you have actually shipped |
| **Computer Fundamentals** | Software Engineer | OS, networks and DBMS — the core-subjects round almost every early-career process runs |
| **System Design — HLD** | Software Engineer | Scoping, data modelling and trade-off reasoning at whiteboard pace |
| **System Design — LLD** | Software Engineer | Class design, SOLID and object modelling — the machine-coding round |
| **AI Engineer — LLM & GenAI** | AI Engineer | RAG, agents, evaluation and shipping with LLMs. Probes whether you built something real or followed a tutorial |

All six are calibrated for a fresher by default (`candidate.fresher` in
`config.yaml`).

---

## Start it

### The desktop launcher

```powershell
.\tools\launcher\build.ps1
```

Builds `dist\Cerebrum.exe` and puts a **Cerebrum** shortcut on your
desktop. Double-click it: it brings up both services, shows you where it
has got to, and opens the tab when they're genuinely ready — not when a log
line claims they are, but when the ports actually accept a connection.

Closing its window is the important half. It takes the whole process tree
down, then checks the ports and clears anything still holding 7332 or 3000,
because a stale `node` process is the difference between "click it again"
and "why is it broken".

It builds with the C# compiler that already ships inside Windows
(`%WINDIR%\Microsoft.NET\...\csc.exe`), so there is no SDK to install and
no toolchain to keep current. It is a window around `start.ps1`, not a
second copy of it — one place knows how to start this thing.

### The command line

```bash
./start.sh          # Git Bash, MSYS, WSL
```
```powershell
.\start.ps1         # PowerShell
```

On a clean checkout this builds the virtualenv, installs the Python and
Node dependencies, writes a `.env` for you to fill in, checks every key,
then brings up the bridge and the console and opens the browser. Ctrl-C
stops both.

| | Git Bash | PowerShell |
|---|---|---|
| Verify keys, then exit | `./start.sh --check` | `.\start.ps1 -Check` |
| Bridge only | `./start.sh --no-web` | `.\start.ps1 -NoWeb` |
| Don't open a tab | `./start.sh --no-browser` | `.\start.ps1 -NoBrowser` |
| Start even though the checks failed | `./start.sh --force` | `.\start.ps1 -Force` |

If the checks fail it does not start. A failed check means the interviewer
can't actually hold a session — starting anyway only moves the discovery
from a preflight message to a dead mic mid-interview.

`start.sh` is a thin wrapper around `start.ps1`. If PowerShell refuses to
run the script at all ("running scripts is disabled on this system"), that
is the default execution policy; `./start.sh` already passes
`-ExecutionPolicy Bypass`, or run it directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

### Docker

```bash
cp .env.example .env     # then fill in your keys
docker compose up
```

Console on **http://localhost:3000**, backend on **http://localhost:7332**.
`config.yaml` and the source are bind-mounted, so changing a mode, the
interview length or any backend code is a `docker compose restart`, not a
rebuild.

One limitation: **the microphone doesn't work in Docker.** The typed
interview is fully functional, but WebRTC media is UDP on ephemeral ports
and aiortc advertises the container's own `172.x` addresses, which your
browser can't route to. Run on the host if you want to dictate answers.

---

## What it costs

**Nothing to run beyond the providers' usage.**

| Piece | What | Cost |
|---|---|---|
| The interviewer | OpenAI (default) | Your existing credits — [platform.openai.com](https://platform.openai.com/api-keys) |
| The interviewer (faster alternative) | Cerebras | Set `interviewer.provider: cerebras` — [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| Role research | Tavily | Free tier — [tavily.com](https://tavily.com) |
| Speech, both directions | Deepgram | Free tier — [console.deepgram.com](https://console.deepgram.com) |
| Keeping your interviews (optional) | MongoDB | Free tier on Atlas, or a local `mongod` — it is only a URI |

**Three keys, not five.** One Deepgram key covers both directions of
speech, and the LLM needs only whichever provider you select. Every swap is one line in `config.yaml`; set
`research.enabled: false` to skip Tavily entirely and fall back to the
model's own knowledge of the role.

Keys go in `.env` — see `.env.example`:

- **The LLM key** for whichever `interviewer.provider` you selected:
  `OPENAI_API_KEY` (the default) or `CEREBRAS_API_KEY`. `doctor.py` checks
  it with a real 1-token completion, not a format check — listing models
  succeeds on an account with no credit left, running an interview doesn't.
- **`DEEPGRAM_API_KEY`** — speech, both ways: dictation so you can speak
  an answer instead of typing it, and Aura so the question is read aloud.
  `doctor.py` checks the two separately, because they are separate
  entitlements and both fail as silence.
- **`TAVILY_API_KEY`** — the role research. Required unless
  `research.enabled` is `false`.
- **`MONGODB_URI`** — optional. Where a stored interview goes. Leave it
  blank and everything still runs; the console simply never offers to keep
  anything. Atlas (`mongodb+srv://…`) and a local `mongod`
  (`mongodb://127.0.0.1:27017/`) both work.

The provider you *didn't* pick can stay blank. Startup demands only the
keys your config actually uses, and names the missing one if you switch
providers without adding its key.

```powershell
.\start.ps1 -Check      # check all of them before relying on them
```

---

## Your library

Everything you chose to keep, and what it adds up to.

```
  a finished report ──[ Store ]──► MongoDB
                                     │
                                     ▼
  the library      score trend · average · best · direction of travel
      │            by round: where you are strong
      │            keeps coming back: the competencies that are still gaps
      ▼
  any saved report, re-read in full - same screen, same detail
```

**The saved copy is the report you read.** Writing a scorecard is an LLM
call, so it is written once and kept on the session; a second read hands
back the same object rather than a fresh opinion. Without that, Store
would save a verdict nobody ever saw.

**What is stored** is a snapshot, not a set of references — it has to
render the same in a year, after the prompts have moved on and the model
has been swapped. That includes which model judged it. The transcript,
every per-answer judgement, the competency table, the sources, and (for
the résumé round) the CV it was built from.

**What is not stored**: the crib sheet of real questions found during
research, and the private per-turn notes. They are kept out of the
database for the same reason they are kept out of the browser.

Turning it off is the default. With no `MONGODB_URI` the button never
appears, the library explains how to switch it on, and nothing else
changes. `python tools/store_check.py` verifies both paths — with a URI it
does the whole round trip and asserts that what comes back out is what
went in; without one it checks the document shape and that nothing private
leaks into it.

---

## How the interview logic actually works

### Before question one

`research.py` searches the round's role (Tavily, falling back to Brave —
see `search.py`) and distils a `RoleBrief`: a competency map, each with a
`fresher_bar`, plus real questions found in the wild for calibration,
framed explicitly as *don't read these out, don't work through them in
order*. One of the four queries is dated, and the distillation is told
today's date and told to prefer what is recurring now — which is what keeps
this from being a snapshot of whatever the model remembers.

Alongside it, `resume.py` turns the résumé into a structured digest once,
so no turn has to re-parse noisy PDF text.

For `resume_projects` there is no external syllabus to search, so
`gateway.py` replaces `research.py` entirely and builds the brief *from the
résumé*: the competencies are the candidate's own projects, and the red
flags are claims in their own document.

### The three agents

Which of them is in charge is a config switch (`interviewer.coordinator`).

- **questionnaire** (`questionnaire.py`, or `gateway.py` for the résumé
  round) writes one question, and is the only thing allowed to produce
  words the candidate sees. It works from the mode's focus, the role brief,
  the résumé digest, and the coverage ledger — so "advance" means picking a
  real gap rather than the next line of a script.
- **evaluator** (`evaluator.py`) reads each answer privately:
  strong / thin / wrong / dodged / dont_know, which competency it bears on,
  and the gap between what was said and what a correct answer contains.
- **main agent** (`agent.py`) calls those two as tools and decides the move
  in between — `challenge`, `redirect`, `dig`, `ease_off`, `advance`. It
  never writes to the candidate, can't skip judging an answer, can't loop,
  and doesn't own the question cap, the ledger, or the scorer. Off by
  default; `coordinator: code` runs the deterministic ladder instead.

### The ledger is the end condition

`coverage.py` holds, per competency, whether anything has been shown and
how hard it has been pushed (`BASICS`, `APPLIED`, `EDGE`). A `strong` read
climbs the rung; nothing lowers it. When no competency is left open the
interview wraps up — bounded below by `min_questions` and above by
`max_questions`, sized for about thirty minutes.

### The report

Nothing evaluative reaches the candidate until the end. As each answer
lands, a background task judges it properly (`scorecard.RunningScore`)
while they're reading the next question; at the end that accumulated
per-answer analysis plus the transcript becomes the scorecard — calibrated
explicitly to *would a company hire this fresher*, not a senior bar. Naming
a concept, plus one worked example, plus reasoning about a trade-off out
loud is a solid 7–8, and an honest "I don't know" costs far less than a
confidently wrong claim.

---

## The console

Two processes. The bridge (`interview_agent.bridge`, on 127.0.0.1:7332)
holds the résumé profile, the session state and the mic's dictation
pipeline; the web console walks rounds → interview → report, talking to the
bridge over REST and to the mic over WebRTC. `page.tsx` owns the state
machine; each screen is its own file, built on shared primitives in
`ui.tsx` and the tokens in `tokens.css`.

- **Rounds** — six cards, and for five of them that is the entire setup:
  one click and the interview starts. Résumé & Projects gets a second
  screen — drop a PDF, choose one, or paste the text.
- **Interview** — one question at a time, with answered turns receding
  behind it. A progress bar against the *expected* length rather than the
  hard ceiling, and once, before the first answer, the plan: how many
  questions, roughly how long, which areas. Type an answer or dictate it.
  Nothing evaluative appears here at any point.
- **Library** — every interview you kept: score trend, per-round
  breakdown, recurring gaps, and a way back into any single report.
- **Report** — the only evaluative screen. Verdict and score, what held up
  and what didn't, then **every question taken apart**: what you said, what
  it showed, what went wrong or was still missing, what a strong answer
  sounds like, and one thing for next time. Then the per-area table, coach
  notes, how it was judged, and the sources it researched.

The console shows the machinery rather than hiding it: the setup screen
renders the actual pipeline — which module runs at each stage, on which
model, with which coordinator driving — and the interview keeps a compact
version on screen throughout. Every value there is read from `/api/health`
and the live session, so the diagram cannot drift from the configuration
the way a hand-drawn one would. It shows the machinery and none of the
judgements: which agents run is fine to see mid-interview, how any given
answer was read is not.

It is built to be looked at, not just read. Obsidian, vibranium and gold:
a black ground with a violet undertone, one accent that carries every
deliberate action, and gold for chrome and nothing else. The score is an
animated ring with the number inside it, the competencies a radar beside
the table that carries the actual reading, and the questions sit on a
timeline rail rather than as a stack of detached cards. The live question
types itself in at reading pace — click to skip it.

**Nothing behind the console is a gradient patch.** Every coloured thing
in the background is a one-pixel line or a two-pixel point: a horizon, a
set of concentric hairlines radiating from above the masthead, a
triangular lattice etched full-bleed across the page, and nine points of
charge breathing out of phase. The field between them is obsidian and
stays obsidian. There is no blur filter anywhere, which also makes it the
cheapest that layer has ever been.

**Gold is never a status colour.** It names sections, rules and corner
brackets, and it never appears on anything evaluative — pale gold and
amber are close enough to be confused, so "developing" moved onto a
saturated orange and gold was kept off every surface a verdict can reach.
You should never have to work out whether a gold thing is telling you
something went badly.

None of that is allowed to say anything. The coverage constellation in the
interview bar uses exactly one colour: a node is lit or it is not. A
second colour would come to mean *and it went well*, and the whole
judge/speak split exists so that opinion cannot reach you mid-interview.

There is one deliberate exception to all of it. Every section label in the
console is gold; the interviewer label on the live screen is not. Gold is
how this theme says *look here*, and that label sits directly above the
question you are being asked.

**The question is also read aloud**, by the speaker button in the bar —
on by default, remembered, and it stops mid-sentence when you mute it.
When the voice is on the question simply appears rather than typing
itself in: two things pacing the same sentence at two different speeds is
worse than either alone, so the voice carries the pace and the text is
there to read along with. **Again** replays it. The good voice is
Deepgram Aura on the key dictation already uses; if that is missing or
unreachable your browser's own voice takes over, which is worse but
always there — a silent interview is the outcome actually worth avoiding.

The ambient layer is tuned for reading rather than for a first
impression. Texture that looks good in a screenshot is not the same as
texture you can read through for twenty minutes, and everything back
there is set to be noticed once and then not again.

Motion is defined once, in `web/app/motion.ts`, and honoured once —
`<MotionConfig reducedMotion="user">` at the root, so
`prefers-reduced-motion` turns every transform into an opacity change and
leaves the layout alone. Charts render at their final state; the charge in
the background settles but the lattice stays, because structure is not
motion.

Both themes, obsidian by default, remembered per browser and applied
before first paint. Day is not an inversion of it — bone and ink with a
deep violet and an antique gold, contrast verified on its own surfaces,
because the report is long-form reading and daylight deserves a design
rather than a courtesy. Everything reads down to 375px, with the radar and the
constellation dropped on narrow screens — both are the impressionistic
read, and the list beside each one names every area in full. Nothing is authenticated — the
bridge binds to `127.0.0.1` only, the same posture as any single-user local
tool.

The interview itself still doesn't persist: the résumé profile and the
live session die with the bridge process. Two things outlive it — the
research cache under `.cache/` (14-day TTL, keyed per role/level/mode), so
a second session on the same role doesn't pay for the search again, and
any interview you explicitly pressed Store on.

---

## Repo map

| Path | What lives there |
|---|---|
| `backend/interview_agent/` | The interviewer: agents, coverage, research, scorecard, bridge |
| `backend/interview_agent/prompts/` | One module per round — name, blurb, default role, focus |
| `web/app/` | The console: state machine, three screens, tokens, primitives |
| `tools/coordinator_check.py` | Drives a whole interview through both coordinators with every model call stubbed. No keys needed |
| `tools/store_check.py` | Checks the saved-interview layer, with or without a database |
| `tools/quality_check.py` | Scripted end-to-end runs against a real model |
| `tools/launcher/` | The desktop launcher and its build script |
| `design-system/cerebrum/` | The design system the console is built to |
| `config.yaml` | Everything tunable by ear. Secrets live in `.env` |

---

## Status — what's verified, and what isn't

The full loop — research → conversation → end-of-interview scorecard — has
been run end to end against a live bridge. The interviewer challenges wrong
claims by name, digs into thin answers, moves to new ground once satisfied
rather than working down a list, and wraps itself up rather than running
on. Typed interview and dictation are both verified working.

**The adaptive ladder has been watched doing both directions.** A good
answer on processes vs threads that mentioned the GIL was followed by a
harder question quoting that back — *"you mentioned the GIL affects
CPU-bound work; elaborate on how it impacts multi-threaded applications and
what you'd do about it."* An honest "I don't know" on the follow-up moved
it sideways to deadlock basics instead of grinding.

**Both coordinators hold their structural invariants** under
`tools/coordinator_check.py`, which drives a whole interview through each
of them with every model call stubbed and asserts what is meant to be true
by construction: the question cap is honoured, a wrap-up turn actually
reaches the candidate, the questionnaire is steered by the read on the
answer it is reacting to, and no question is written and then thrown away.
It needs no API keys and no running bridge. Three real control-flow bugs in
the agent path were found and fixed this way.

**Open, and named honestly:**

- The quality comparison between coordinators hasn't been run — flipping
  `interviewer.coordinator` and diffing two `tools/quality_check.py hostile`
  transcripts to see whether the LLM main agent actually interviews better
  than the deterministic ladder, or just costs three more round-trips a
  question. `code` stays the default until that says otherwise.
- That comparison should look at one case specifically: in a live run, a
  confidently wrong claim ("SQLite handles concurrent writes better than
  Postgres") was read as *thin* rather than *wrong* on the critical path,
  so the agent dug instead of challenging it in the room. The background
  scorer on the stronger model caught it and it landed in the scorecard —
  but catching it a turn earlier is the whole point of the `challenge` rung.
- Whether the *quality* of real Tavily results is good for a given role is
  worth a look once a funded key is in `.env`. The code path (search →
  digest → distillation → cached brief) is verified; the usefulness of what
  comes back for each role is a judgement call nobody has made yet.
- Cerebras is wired up and substantially faster, which matters when a
  person is waiting for the next question. That account currently returns
  `402 Payment required` on completions, which is why OpenAI is the default.

A fully spoken interview — one you could do with the screen off — isn't
built. Speech goes both ways now but not symmetrically, and the asymmetry
is deliberate rather than unfinished. Out, the interviewer reads its
question aloud and that is the only thing it will ever say. In,
`pipeline.py`'s mic path turns what you say into text in the answer box
and the normal typed flow takes over. The voice is a rehearsal aid laid
over a written interview, not a conversation.
