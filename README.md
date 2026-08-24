# Interview Agent

A voice-based mock interviewer for entry-level candidates. Pick a role and a
mode, talk to it like a real interview, and it asks follow-up and
cross-questions grounded in what you just said - not a random next question
off a list.

```
  you, on the mic
      │
      ▼
  the voice pipeline        one PipeCat pipeline per session, over WebRTC
      │
      ├── Deepgram            speech-to-text
      ├── Cerebras            the interviewer's model - asks, follows up, cross-questions
      └── Deepgram            text-to-speech (or Cartesia, if you switch it)
      │
      ▼
  resume/projects            uploaded once, structured, grounds resume_projects mode
```

Three roles (AI Engineer, Backend Engineer, Full Stack Developer) and three
modes (Resume & Projects, Computer Fundamentals, System Design), all
calibrated for a fresher candidate by default (`candidate.fresher` in
`config.yaml`).

## What it costs

**Nothing to run beyond the three providers' usage.**

| Piece | What | Cost |
|---|---|---|
| The interviewer | Cerebras | Pay-as-you-go - [cloud.cerebras.ai](https://cloud.cerebras.ai) billing |
| Speech-to-text **and** text-to-speech | Deepgram | Free tier available - [console.deepgram.com](https://console.deepgram.com) |
| Text-to-speech (optional alternative) | Cartesia | Only if you switch `voice.tts.provider` - [play.cartesia.ai](https://play.cartesia.ai) |

**Two keys, not three.** Deepgram does both STT and TTS off one key, so the
voice pipeline needs no third account. Cartesia stays wired up as an option
if you prefer its voices - set `voice.tts.provider: cartesia` in
`config.yaml` and add `CARTESIA_API_KEY` to `.env`.

## Setup

One command, whichever shell you live in:

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

Two keys go in `.env` - see `.env.example`:

- **Cerebras** - [cloud.cerebras.ai](https://cloud.cerebras.ai) → create an
  API key, and make sure the account has credit. `doctor.py` checks this
  with a real (1-token) completion call, not just a valid-key check -
  listing models succeeds on an unfunded account, but running an interview
  doesn't.
- **Deepgram** - [console.deepgram.com](https://console.deepgram.com) →
  create an API key. Used for both hearing your answers and speaking the
  questions.

`CARTESIA_API_KEY` is optional and only read when `voice.tts.provider` is
set to `cartesia`; leaving it blank is fine.

Check all three before relying on them:

```powershell
.\start.ps1 -Check
```

## The console

`.\start.ps1` puts it on **http://localhost:3000**. Two processes: the
bridge (`interview_agent.bridge`, on 127.0.0.1:7332) holds the resume
profile, the interview session state, and the PipeCat voice pipeline; the
web console is a window onto it over REST + WebRTC.

- **`/`** - upload a resume PDF, see it parsed into a structured profile
  (education, skills, projects, experience).
- **`/voice`** - the actual interview: pick a role and mode, start, and talk.
  Live transcript, mute toggle, resume status shown before you start.
- **`/interview`** - a text-only harness kept around for debugging the
  interview logic without audio in the loop.

Nothing here is authenticated - the bridge binds to `127.0.0.1` only, same
posture as a single-user local tool with nothing to expose beyond this
machine.

## How the interview logic works

`backend/interview_agent/interviewer.py` composes one system prompt per
session from four pieces: a fixed set of interviewer-behavior rules (ask one
question at a time, cross-question the last answer before moving on, no
live grading, stay in character), the selected role's focus
(`prompts/ai_engineer.py` etc.), the selected mode's focus
(`prompts/system_design.py` etc. - `resume_projects` also injects the
parsed resume), and a fresher/experienced calibration note.

The cross-questioning behavior isn't a special feature - it's a prompting
and full-history discipline. Every turn, the model sees the whole
conversation so far and is explicitly instructed to dig into the
candidate's last answer before moving to a new topic. The same composition
is used whether the interview is running over the text harness
(`interviewer.InterviewSession`, a plain message list) or the voice
pipeline (`pipeline.py`, pipecat's `LLMContext` fed by the STT/TTS
turn-taking machinery instead) - the transport differs, the interview logic
doesn't.

Nothing persists across restarts: no database, no session log. The resume
profile and the active interview session both live in the bridge process's
memory and reset the moment it stops.

## Status

Every phase up through the voice pipeline and web UI is built and, where a
real key made it possible, verified live - not just structurally. Both
Deepgram websockets (STT and TTS) have been confirmed connecting inside the
running pipeline.

The one remaining blocker is **Cerebras account credit**: the key
authenticates and the model is available, but completions return `402
Payment required`, so a full spoken interview hasn't been run end to end
yet. Top up at [cloud.cerebras.ai](https://cloud.cerebras.ai) and
`.\start.ps1 -Check` will go green. The commit history has the specifics of
what was and wasn't testable at each step.
