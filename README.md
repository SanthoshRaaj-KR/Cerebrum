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
      ├── OpenAI / Cerebras   the interviewer's model - asks, follows up, cross-questions
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
| The interviewer | OpenAI (default) | Your existing credits - [platform.openai.com](https://platform.openai.com/api-keys) |
| The interviewer (faster alternative) | Cerebras | Set `interviewer.provider: cerebras` - [cloud.cerebras.ai](https://cloud.cerebras.ai) |
| Speech-to-text **and** text-to-speech | Deepgram | Free tier available - [console.deepgram.com](https://console.deepgram.com) |
| Text-to-speech (optional alternative) | Cartesia | Only if you switch `voice.tts.provider` - [play.cartesia.ai](https://play.cartesia.ai) |

**Two keys, not four.** Deepgram does both STT and TTS off one key, and the
LLM needs only whichever provider you select. Both swaps are one line in
`config.yaml`.

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
question count or any backend code is a `docker compose restart`, not a
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

Two keys go in `.env` - see `.env.example`:

- **The LLM key** for whichever `interviewer.provider` you selected:
  `OPENAI_API_KEY` (the default) or `CEREBRAS_API_KEY`. Either way,
  `doctor.py` checks it with a real 1-token completion, not just a
  valid-key check - listing models succeeds on an account with no credit
  left, but running an interview doesn't.
- **Deepgram** - [console.deepgram.com](https://console.deepgram.com) →
  create an API key. Used for both hearing your answers and speaking the
  questions.

The other two keys are optional: the LLM provider you *didn't* pick, and
`CARTESIA_API_KEY` (only read when `voice.tts.provider` is `cartesia`).
Leaving them blank is fine - startup only demands the ones your config
actually uses, and names the missing one if you switch providers without
adding its key.

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

`.\start.ps1 -Check` passes fully green on the default (OpenAI + Deepgram)
setup, and the whole text path is verified working end to end: a real
resume PDF uploads and parses into structured projects/skills, the
interviewer opens with a question grounded in one of those actual projects,
and follow-ups reference what the candidate just said rather than jumping
topic. The voice pipeline builds and both Deepgram websockets (STT and TTS)
connect inside the running session.

What hasn't been exercised yet is a **spoken** interview through a real
browser microphone - the WebRTC handshake has only been driven by synthetic
offers, never by an actual mic. That's the part to try first, and the most
likely place to find something still rough.

Cerebras is wired up and worth switching to when its account has credit -
it's substantially faster, which matters when a person is waiting for the
next question out loud. Right now that account returns `402 Payment
required` on completions, which is why OpenAI is the default.
