# Cerebrum

A mock interviewer for entry-level candidates that actually behaves like
one. Pick a mode, paste your résumé, type your target role, and it runs a
real interview of about half an hour: no fixed question list, no plan to
fall back on. Before it starts, it looks up what your target role's
fresher interviews actually cover and researches real questions companies
have asked; from there it reacts to what you just said - challenging a
wrong claim, digging into a thin answer, easing off an honest "I don't
know", moving to new ground once it's satisfied - the way a person running
the room would, not a quiz working down a list. It ends when it has a read
on everything worth asking about, not when a timer runs out. Nothing is
scored to your face: no score, no rubric, no hint of a verdict
mid-interview, because no real interviewer grades you as you go.

```
  target role + résumé       researched before question one - a competency map
      │                      and real fresher questions (Tavily → Brave), plus
      │                      the résumé digested once into a structured view
      ▼
  the interview loop         one turn at a time, full history in context
      │
      ├── evaluator          how did that answer go, privately - and is a
      │                      "wrong" call worth double-checking before it counts
      ├── the move            challenge / redirect / dig / ease off / advance
      ├── questionnaire      writes the one question the candidate sees
      └── coverage ledger    which competencies still have nothing shown;
      │                      when none are left, the interview wraps up
      ▼
  the scorecard              built from per-answer judgements made in the
                              background as you went - calibrated to "would a
                              company hire this fresher", not a senior bar
```

Six modes (Résumé & Projects, SDE & Backend, Computer Fundamentals, System
Design HLD/LLD, AI Engineer), all calibrated for a fresher candidate by
default (`candidate.fresher` in `config.yaml`). There's no separate role
list - you type your own target role and level, and that's what the
research is grounded in.

## What it costs

**Nothing to run beyond the providers' usage.**

| Piece | What | Cost |
|---|---|---|
| The interviewer | OpenAI (default) | Your existing credits - [platform.openai.com](https://platform.openai.com/api-keys) |
| The interviewer (faster alternative) | Cerebras | Set `interviewer.provider: cerebras` - [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| Role research (real fresher questions + competencies) | Tavily | Free tier available - [tavily.com](https://tavily.com) |
| Speech-to-text, so you can speak an answer instead of typing it | Deepgram | Free tier available - [console.deepgram.com](https://console.deepgram.com) |

**Three keys, not five.** The interview is typed - the interviewer never
speaks, so there is no text-to-speech to pay for - and the LLM needs only
whichever provider you select. All swaps are one line in `config.yaml`;
set `research.enabled: false` there to skip Tavily entirely and fall back
to the model's own knowledge of the role.

## Setup

### Docker (recommended)

```bash
cp .env.example .env     # then fill in your keys
docker compose up
```

That's it — console on **http://localhost:3000**, backend on
**http://localhost:7332**. `Ctrl-C` stops both; `docker compose down`
removes the containers.

`config.yaml` and the source are bind-mounted, so changing a mode, the
interview length or any backend code is a `docker compose restart`, not a
rebuild. Only a dependency change needs `docker compose build`.

One limitation: **the microphone doesn't work in Docker.** The typed
interview is fully functional, but WebRTC media is UDP on ephemeral ports
and aiortc advertises the container's own `172.x` addresses, which your
browser can't route to. Run on the host if you want to dictate answers.

### On the host

```bash
./start.sh          # Git Bash, MSYS, WSL
```
```powershell
.\start.ps1         # PowerShell
```

On a clean checkout this builds the virtualenv, installs the Python and
Node dependencies, writes a `.env` for you to fill in, checks all three
keys, then brings up the bridge and the console and opens the browser.
Ctrl-C stops both.

| | Git Bash | PowerShell |
|---|---|---|
| Verify keys, then exit | `./start.sh --check` | `.\start.ps1 -Check` |
| Bridge only | `./start.sh --no-web` | `.\start.ps1 -NoWeb` |
| Start even though the checks failed | `./start.sh --force` | `.\start.ps1 -Force` |

If the checks fail it does not start. A failed check means the interviewer
can't actually hold a session - starting anyway only moves the discovery
from a preflight message to a dead mic mid-interview.

`start.sh` is a thin wrapper around `start.ps1`. If PowerShell refuses to
run the script at all ("running scripts is disabled on this system"), that
is the default execution policy; `./start.sh` already passes
`-ExecutionPolicy Bypass`, or run it directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Three keys go in `.env` - see `.env.example`:

- **The LLM key** for whichever `interviewer.provider` you selected:
  `OPENAI_API_KEY` (the default) or `CEREBRAS_API_KEY`. Either way,
  `doctor.py` checks it with a real 1-token completion, not just a
  valid-key check - listing models succeeds on an account with no credit
  left, but running an interview doesn't.
- **Deepgram** - [console.deepgram.com](https://console.deepgram.com) →
  create an API key. Used for both hearing your answers and speaking the
  questions.
- **Tavily** - [tavily.com](https://tavily.com) → create an API key. Used
  to research the candidate's target role before the interview starts.
  Required unless `research.enabled` is set to `false` in `config.yaml`,
  in which case the interview still runs, just grounded in the model's own
  knowledge of the role instead of a live search.

The remaining key is optional: the LLM provider you *didn't* pick.
Leaving it blank is fine - startup only demands the ones your config
actually uses, and names the missing one if you switch providers without
adding its key.

Check all of them before relying on them:

```powershell
.\start.ps1 -Check
```

## The console

`.\start.ps1` puts it on **http://localhost:3000**. Two processes: the
bridge (`interview_agent.bridge`, on 127.0.0.1:7332) holds the resume
profile, the interview session state, and the mic's dictation pipeline;
the web console (`web/app/page.tsx`) is a single page that walks through
setup → interview → report, talking to the bridge over REST and to the
mic over WebRTC.

- **Setup** - pick a mode, type your target role and level, paste or
  upload a résumé. The résumé is required: it's digested before the first
  question and the interview is built around it.
- **Interview** - the actual thing: how far through you are, the
  competencies research turned up, and the conversation itself. Type an
  answer or dictate it; nothing is scored here.
- **Report** - the scorecard once the interview wraps up or you end it
  early: verdict, per-competency status, strengths, gaps, coach notes, the
  sources it researched from, and the full transcript.

Nothing here is authenticated - the bridge binds to `127.0.0.1` only, same
posture as a single-user local tool with nothing to expose beyond this
machine.

## How the interview logic works

There's no question plan. Before the first question, two things run:
`research.py` searches the candidate's target role (Tavily, falling back
to Brave - see `search.py`) and distills a `RoleBrief`: a competency map,
each with a `fresher_bar` (what counts as *having* it at entry level, not
at a senior level), plus real questions found for calibration, framed
explicitly as "don't read these out, don't work through them in order."
Alongside it, `resume.py` turns the résumé into a structured digest once,
so no turn has to re-parse noisy PDF text. For the `resume_projects` mode
there is no external syllabus to search, so `gateway.py` replaces
`research.py` entirely and builds the brief *from the résumé* - the
competencies are the candidate's own projects and the red flags are
claims in their own document.

Three agents run the interview, and which of them is in charge is a config
switch (`interviewer.coordinator`):

- **questionnaire** (`questionnaire.py`, or `gateway.py` for the résumé
  round) writes one question, and is the only thing allowed to produce
  words the candidate sees. It works from the mode's focus
  (`prompts/sde_backend.py` etc.), the role brief, the résumé digest, and
  `coverage.py`'s ledger - which competencies still have nothing shown, so
  "advance" means picking real gaps rather than the next line of a script.
- **evaluator** (`evaluator.py`) reads each answer privately:
  strong/thin/wrong/dodged/dont_know, which competency it bears on, and
  the gap between what they said and what a correct answer contains. A
  `wrong` verdict - the one thing that gets challenged to their face -
  gets a second focused opinion on a stronger model before it counts,
  because telling a candidate they're wrong when they're right is the
  worst thing this can do.
- **main agent** (`agent.py`) calls those two as tools and decides the move
  in between. It never writes to the candidate, can't skip judging an
  answer, can't loop, and doesn't own the question cap, the ledger, or the
  scorer - those are enforced in code whichever coordinator is driving.
  Off by default; `coordinator: code` runs the deterministic ladder
  instead.

There is no clock. The interview runs until every competency has a read -
shown at thin-or-better, or pushed until the edge of what they know was
found - bounded by a min/max question budget sized for about thirty
minutes. Nothing is ever scored on how long an answer took.

Nothing evaluative reaches the candidate until the end. As each answer
comes in, a background task judges it properly (`scorecard.RunningScore`)
while they're already reading the next question; at the end that
accumulated per-answer analysis plus the transcript becomes the scorecard,
calibrated explicitly to "would a company hire this fresher" rather than a
senior bar - naming a concept plus one worked example plus reasoning about
a trade-off out loud is a solid 7-8, and an honest "I don't know" costs
far less than a confidently wrong claim.

The console shows all of this rather than hiding it: the setup screen
renders the actual pipeline - which module runs at each stage, on which
model, with which coordinator driving - and the interview sidebar keeps a
compact version of it on screen throughout. Every value on those panels is
read from `/api/health` and the live session state, so the diagram cannot
drift from the configuration the way a hand-drawn one would. It shows the
machinery and none of the judgements: which agents run is fine to see
mid-interview, how any given answer was read is not.

The same composition is used whether the interview is running over the
text-and-dictation console (`interviewer.InterviewSession`, a plain
message list) or an internal call from `tools/quality_check.py` - the
transport differs, the interview logic doesn't.

Nothing persists across restarts: no database, no session log. The resume
profile, the active interview session, and the research cache under
`.cache/` all live independently - the first two reset the moment the
bridge process stops, the research cache survives it (14-day TTL, keyed
per role/level/mode) so a second session on the same role doesn't pay for
the search again.

## Status

The full loop - research → conversation → end-of-interview scorecard - has
been run end to end against a live bridge: the interviewer challenges
wrong claims by name, digs into thin answers, moves to new ground once
satisfied rather than working down a list, and wraps itself up rather than
running on. Two real bugs turned up in that pass and were fixed - a topic
could get re-asked indefinitely if the candidate kept dodging it
(`topic_exhausted` now has a deterministic guarantee, not just a model
judgment call), and a confidently wrong claim could get half-credited as a
strength in the scorecard (`scorecard.py`'s prompt now has an explicit
worked example for exactly that case). Typed interview and dictation are
verified working; a fully spoken interview (the interviewer talking back
through TTS) isn't built - `pipeline.py`'s mic path only turns speech into
the answer box's text.

The multi-agent split (`agent.py`, `questionnaire.py`, `gateway.py`,
`evaluator.py`) is built, and both coordinators now hold their structural
invariants under `tools/coordinator_check.py` - which drives a whole
interview through each of them with every model call stubbed, and asserts
the things that are meant to be true by construction: the question cap is
honoured, a wrap-up turn actually reaches the candidate, the questionnaire
is steered by the read on the answer it is reacting to, and no question is
written and then thrown away. It needs no API keys and no running bridge.

`coordinator: agent` has been run live against a real bridge and a real
résumé: the gateway builds its brief from the candidate's own projects,
the main agent logs its move each turn (`main agent: dig @ <competency>`),
and the scorecard comes back written off the background per-answer
judgements. What has *not* been done is the quality comparison - flipping
`interviewer.coordinator` and diffing two `tools/quality_check.py hostile`
transcripts to see whether the LLM main agent actually interviews better
than the deterministic ladder, or just costs three more round-trips a
question. `code` remains the default until that says otherwise.

One thing that comparison should look at specifically: in the live run
above, a confidently wrong claim ("SQLite handles concurrent writes better
than Postgres") was read as thin rather than wrong on the critical path,
so the agent dug rather than challenging it to the candidate's face. The
background scorer on the stronger model caught it and it landed in the
scorecard's gaps and coach notes - but catching it a turn earlier, in the
room, is the whole point of the `challenge` rung.

What hasn't been exercised with a *real* Tavily key is whether the
research it returns is actually good - the code path (search → digest →
distillation call → cached `RoleBrief`) is verified working with an
unfunded/placeholder key and with research disabled, but the quality of
real search results for a given role is worth checking once a working key
is in `.env`.

Cerebras is wired up and worth switching to when its account has credit -
it's substantially faster, which matters when a person is waiting on the
next question. Right now that account returns `402 Payment required` on
completions, which is why OpenAI is the default.
