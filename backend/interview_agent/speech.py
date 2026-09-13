"""Reading a question aloud.

The interviewer used to be silent by design, and the reasoning was sound
for what the product was: the interview is typed and graded, so a voice
bought nothing and `pipeline.py` deliberately negotiates no outbound
audio at all.

What changed is what the voice is *for*. This is not conversation - it
reads out the question that is already on the candidate's screen, so a
practice round feels closer to being asked something by a person than to
reading a form. That is a rehearsal aid. It does not touch the answer
path, and it does not touch the judging path.

**The one rule this module exists to enforce.** It will only speak text
the session has actually asked. Not a summary, not a hint, not a note,
not a score - and crucially, not arbitrary text posted by whatever is on
the other end of the socket. The bridge checks the text against the
session's own questions before a single byte reaches Deepgram, because
"say this out loud" is exactly the shape of request that turns a local
convenience into a way to read back something the candidate was never
meant to hear.

Failure is never fatal. If Deepgram is unreachable, out of credit or
slow, the browser falls back to its own built-in voice. Worse, always
there, and a silent interview is the outcome actually worth avoiding.
"""

from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.deepgram.com/v1/speak"

# Aura is quick, but it is still a network round trip in front of a
# question someone is waiting to hear. Past this the browser voice is the
# better answer - it starts instantly.
_TIMEOUT = 12.0

# Deepgram caps a single request, and a question that long is a bug
# somewhere upstream rather than something to narrate.
MAX_CHARS = 1800


class SpeechError(RuntimeError):
    """Synthesis did not work. The caller should fall back, not fail."""


def available() -> bool:
    """Whether the bridge can synthesise at all. Cheap - no network."""
    return settings.tts_enabled


async def synthesize(text: str) -> bytes:
    """One question to MP3 bytes. Raises SpeechError; never returns empty."""
    if not available():
        raise SpeechError("no Deepgram key, so there is nothing to speak with")

    text = text.strip()
    if not text:
        raise SpeechError("nothing to say")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]

    params = {
        "model": settings.tts_model,
        # MP3 rather than raw PCM: every browser plays it from a blob URL
        # with no decoding of our own, and it is a fraction of the bytes
        # over the wire.
        "encoding": "mp3",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                _ENDPOINT,
                params=params,
                headers={
                    "Authorization": f"Token {settings.deepgram_api_key}",
                    "Content-Type": "application/json",
                },
                json={"text": text},
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not reach Deepgram for speech: %s", exc)
        raise SpeechError("could not reach the speech service") from None

    if r.status_code == 200:
        if not r.content:
            raise SpeechError("the speech service returned no audio")
        return r.content

    # These three are worth telling apart in the log, because the fix for
    # each is different and they all look like "no sound" from the browser.
    if r.status_code in (401, 403):
        logger.error("Deepgram rejected the key for speech")
        raise SpeechError("the speech key was rejected")
    if r.status_code in (402, 429):
        logger.error("Deepgram speech quota or rate limit hit")
        raise SpeechError("the speech service is out of quota")
    logger.error("Deepgram speech failed %s: %s", r.status_code, r.text[:200])
    raise SpeechError("the speech service did not answer properly")
