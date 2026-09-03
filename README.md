# Interview Agent

A mock interviewer for entry-level candidates that actually behaves like
one. Pick a mode, type your target role, and it runs a real 40-minute
interview: no fixed question list, no plan to fall back on. Before it
starts, it looks up what your target role's fresher interviews actually
cover and researches real questions companies have asked; from there it
follows the clock and reacts to what you just said - challenging a wrong
claim, digging into a thin answer, easing off an honest "I don't know",
moving to new ground once it's satisfied - the way a person running the
room would, not a quiz working down a list. Nothing is scored until the
40 minutes are up: no score, no rubric, no hint of a verdict mid-interview,
because no real interviewer grades you to your face.

```
  target role                researched before question one - real fresher
      │                      interview questions + a competency map, from Tavily
      ▼
  the interview loop         one turn at a time, full history in context
      │
      ├── react to the last answer   challenge / redirect / dig / ease off / advance
      ├── the clock                  opening → core → depth → closing, 40 min
      └── the coverage ledger        which competencies still have nothing shown
      │
      ▼
  the scorecard               one call, once, at the end - calibrated to
                               "would a company hire this fresher", not a
                               senior bar
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
| Speech-to-text **and** text-to-speech | Deepgram | Free tier available - [console.deepgram.com](https://console.deepgram.com) |
| Text-to-speech (optional alternative) | Cartesia | Only if you switch `voice.tts.provider` - [play.cartesia.ai](https://play.cartesia.ai) |

**Three keys, not five.** Deepgram does both STT and TTS off one key, and
the LLM needs only whichever provider you select. All swaps are one line
in `config.yaml`; set `research.enabled: false` there to skip Tavily
entirely and fall back to the model's own knowledge of the role.

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

The other two keys are optional: the LLM provider you *didn't* pick, and
`CARTESIA_API_KEY` (only read when `voice.tts.provider` is `cartesia`).
Leaving them blank is fine - startup only demands the ones your config
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
  upload a résumé (optional - the questions get a lot more specific with
  one).
- **Interview** - the actual thing: a countdown clock, the competencies
  research turned up, and the conversation itself. Type an answer or
  dictate it; nothing is scored here.
- **Report** - the scorecard once the clock runs out or you end it early:
  verdict, per-competency status, strengths, gaps, coach notes, the
  sources it researched from, and the full transcript.

Nothing here is authenticated - the bridge binds to `127.0.0.1` only, same
posture as a single-user local tool with nothing to expose beyond this
machine.

## How the interview logic works

There's no question plan. `backend/interview_agent/research.py` runs
before the first question - two or three Tavily searches for the
candidate's target role, distilled into a `RoleBrief`: a competency map
(each with a `fresher_bar` - what counts as *having* it at entry level,
not at a senior level) and real questions found for calibration, framed
explicitly as "don't read these out, don't work through them in order."

From there, `interviewer.py` composes one system prompt per turn from: a
fixed reactive ladder (challenge a wrong claim / redirect a dodge / dig
into a thin answer / ease off an honest "I don't know" / only then advance
to new ground), the mode's own focus (`prompts/sde_backend.py` etc.), the
role brief, and two things that change every turn - `clock.py`'s phase
guidance (opening → core → depth → closing, driven by elapsed wall time,
not a turn count) and `notes.py`'s coverage ledger (which competencies
still have nothing shown, so "advance" means picking real gaps, not the
next line of a script).

The cross-questioning behavior isn't a special feature - it's a prompting
and full-history discipline. Every turn the model sees the whole
conversation so far, plus a private read on how the last answer went
(`notes.take()` - strong/thin/wrong/dodged/dont_know, never shown to the
candidate) that decides which of the five options it should take. Nothing
evaluative reaches the candidate until the interview ends: `scorecard.py`
runs once, over the whole transcript, calibrated explicitly to "would a
company hire this fresher" rather than a senior bar - naming a concept
plus one worked example plus reasoning about a trade-off out loud is a
solid 7-8, and an honest "I don't know" costs far less than a confidently
wrong claim.

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

`.\start.ps1 -Check` passes fully green on the default (OpenAI + Deepgram
+ Tavily) setup. The full loop - research → clock-paced conversation →
end-of-interview scorecard - has been run end to end against a live
bridge (with `research.enabled: false`, since this environment has no
Tavily key of its own to test against): the interviewer challenges wrong
claims by name, digs into thin answers, moves to new ground once satisfied
rather than working down a list, and self-terminates in the closing phase
with time still on the clock rather than running past it. Two real bugs
turned up in that pass and were fixed - a topic could get re-asked
indefinitely if the candidate kept dodging it (`notes.py`'s
`topic_exhausted` now has a deterministic guarantee, not just a model
judgment call), and a confidently wrong claim could get half-credited as a
strength in the scorecard (`scorecard.py`'s prompt now has an explicit
worked example for exactly that case). Typed interview and dictation are
verified working; a fully spoken interview (the interviewer talking back
through TTS) isn't built - `pipeline.py`'s mic path only turns speech into
the answer box's text, same as before this change.

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
