"""CLI: check everything before you rely on it mid-interview.

    python -m interview_agent.doctor

Validates the API keys (the LLM provider, Deepgram, Cartesia, and the
role-research search providers) against the real services, so a bad key
surfaces here rather than as a dead mic, a silent interviewer, or an
ungrounded set of questions mid-session.
"""

from __future__ import annotations

import shutil
import sys

import httpx

from interview_agent.config import ROOT, settings

OK = "  [ ok ]"
BAD = "  [FAIL]"
WARN = "  [warn]"

_failures: list[str] = []


def _fail(msg: str) -> None:
    _failures.append(msg)


# Both providers speak the OpenAI API shape (Cerebras is OpenAI-compatible),
# so one check covers whichever config.yaml selects.
_LLM_PROVIDERS = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "key_name": "OPENAI_API_KEY",
        "console": "platform.openai.com/api-keys",
        "billing": "platform.openai.com/account/billing",
    },
    "cerebras": {
        "label": "Cerebras",
        "base_url": "https://api.cerebras.ai/v1",
        "key_name": "CEREBRAS_API_KEY",
        "console": "cloud.cerebras.ai",
        "billing": "cloud.cerebras.ai (billing)",
    },
}


def check_llm() -> None:
    p = _LLM_PROVIDERS.get(settings.llm_provider)
    if p is None:
        print("\nInterviewer model")
        print(f"{BAD} unknown interviewer.provider: {settings.llm_provider!r}")
        print(f"       expected one of: {', '.join(_LLM_PROVIDERS)}")
        _fail(f"unknown provider {settings.llm_provider!r}")
        return

    label, key = p["label"], settings.llm_api_key
    print(f"\n{label} (the interviewer's model)")

    try:
        r = httpx.get(
            f"{p['base_url']}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not reach {label}: {exc}")
        _fail(f"{label} unreachable")
        return

    if r.status_code == 401:
        print(f"{BAD} key rejected. Make a new one at {p['console']}")
        _fail(f"{p['key_name']} invalid")
        return
    if r.status_code != 200:
        print(f"{WARN} unexpected response listing models {r.status_code}: {r.text[:120]}")
        return

    wanted = settings.model
    available = {m["id"] for m in r.json().get("data", [])}
    print(f"{OK} key valid")
    if wanted in available:
        print(f"{OK} model {wanted} available")
    else:
        print(f"{WARN} model {wanted} not in your account's model list")

    # Listing models doesn't touch billing; actually running an interview
    # does. A key can be valid and still be out of credit - that only shows
    # up on a real completion call, so make the smallest one that exists.
    try:
        r = httpx.post(
            f"{p['base_url']}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": wanted,
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            },
            timeout=30.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not run a completion: {exc}")
        _fail(f"{label} completion unreachable")
        return

    if r.status_code == 200:
        print(f"{OK} can run a completion")
    elif r.status_code in (402, 429):
        # OpenAI reports an exhausted balance as 429 insufficient_quota;
        # Cerebras uses 402. Same problem, different number.
        body = r.text.lower()
        if r.status_code == 402 or "quota" in body or "billing" in body:
            print(f"{BAD} out of credit - top up at {p['billing']}")
            _fail(f"{label} out of credit")
        else:
            print(f"{BAD} rate limited - check your usage")
            _fail(f"{label} rate limited")
    else:
        print(f"{WARN} unexpected response running a completion {r.status_code}: {r.text[:120]}")


def check_deepgram() -> None:
    print("\nDeepgram (hears your spoken answers)")
    try:
        r = httpx.get(
            "https://api.deepgram.com/v1/projects",
            headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not reach Deepgram: {exc}")
        _fail("Deepgram unreachable")
        return

    if r.status_code == 200:
        print(f"{OK} key valid")
    elif r.status_code in (401, 403):
        print(f"{BAD} key rejected. Check DEEPGRAM_API_KEY")
        _fail("DEEPGRAM_API_KEY invalid")
    else:
        print(f"{WARN} unexpected response {r.status_code}: {r.text[:120]}")


def check_tts() -> None:
    """Checks whichever TTS provider config.yaml actually selects."""
    if settings.tts_provider == "cartesia":
        _check_cartesia()
    else:
        _check_deepgram_tts()


def _check_deepgram_tts() -> None:
    print("\nDeepgram TTS (the interviewer's voice)")
    voice = settings.tts_voice_id or "aura-2-thalia-en"
    try:
        r = httpx.post(
            f"https://api.deepgram.com/v1/speak?model={voice}",
            headers={
                "Authorization": f"Token {settings.deepgram_api_key}",
                "Content-Type": "application/json",
            },
            json={"text": "test"},
            timeout=30.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not reach Deepgram TTS: {exc}")
        _fail("Deepgram TTS unreachable")
        return

    if r.status_code == 200:
        print(f"{OK} can synthesize speech (voice {voice})")
    elif r.status_code in (401, 403):
        print(f"{BAD} key rejected for TTS. Check DEEPGRAM_API_KEY")
        _fail("DEEPGRAM_API_KEY invalid for TTS")
    elif r.status_code == 402:
        print(f"{BAD} out of credit - check billing at console.deepgram.com")
        _fail("Deepgram out of credit")
    else:
        print(f"{WARN} unexpected response synthesizing speech {r.status_code}: {r.text[:150]}")


def _check_cartesia() -> None:
    print("\nCartesia (the interviewer's voice)")
    try:
        r = httpx.get(
            "https://api.cartesia.ai/voices",
            headers={
                "Authorization": f"Bearer {settings.cartesia_api_key}",
                "Cartesia-Version": "2024-06-10",
            },
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not reach Cartesia: {exc}")
        _fail("Cartesia unreachable")
        return

    if r.status_code == 401 or r.status_code == 403:
        print(f"{BAD} key rejected. Check CARTESIA_API_KEY")
        _fail("CARTESIA_API_KEY invalid")
        return
    if r.status_code != 200:
        print(f"{WARN} unexpected response listing voices {r.status_code}: {r.text[:120]}")
        return
    print(f"{OK} key valid")

    # Listing voices doesn't touch billing; actually synthesizing does (same
    # gap the Cerebras check above closed) - a key can list voices fine and
    # still be out of credit for real TTS. Voice id left unset here uses
    # Cartesia's account default, same as the pipeline does when
    # voice.tts.voice_id in config.yaml is blank.
    try:
        r = httpx.post(
            "https://api.cartesia.ai/tts/bytes",
            headers={
                "Authorization": f"Bearer {settings.cartesia_api_key}",
                "Cartesia-Version": "2024-06-10",
                "Content-Type": "application/json",
            },
            json={
                "model_id": "sonic-2",
                "transcript": "hi",
                "voice": {"mode": "id", "id": _default_voice_id()},
                "output_format": {
                    "container": "raw",
                    "encoding": "pcm_s16le",
                    "sample_rate": 16000,
                },
            },
            timeout=30.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not synthesize speech: {exc}")
        _fail("Cartesia synthesis unreachable")
        return

    if r.status_code == 200:
        print(f"{OK} can synthesize speech")
    elif r.status_code == 402:
        print(f"{BAD} out of credit - top up at play.cartesia.ai (billing)")
        _fail("Cartesia out of credit")
    elif r.status_code in (401, 403):
        print(f"{BAD} key rejected during synthesis. Check CARTESIA_API_KEY")
        _fail("CARTESIA_API_KEY invalid")
    else:
        print(f"{WARN} unexpected response synthesizing speech {r.status_code}: {r.text[:150]}")


def _default_voice_id() -> str:
    configured = ((settings.voice.get("tts") or {}).get("voice_id") or "").strip()
    # Cartesia's well-known default demo voice, used only for this preflight
    # ping when config.yaml leaves voice_id blank (pipeline.py itself passes
    # voice_id=None in that case, which picks the account default instead).
    return configured or "a0e99841-438c-4a64-b679-ae501e7d6091"


_RESEARCH_QUERY = "backend engineer fresher interview questions"


def check_research() -> None:
    """Role research runs a fallback chain of search providers (see
    config.yaml research.providers). Check each one the same way as
    everything else here: prove the key actually runs a search, not just
    that it parses. A missing fallback key is a warning, not a failure -
    the chain is meant to survive that."""
    print("\nRole research (grounds the questions)")
    if not settings.research_enabled:
        print(f"{WARN} research.enabled is false in config.yaml - skipped")
        return

    providers = settings.research_providers
    known = {"tavily": _check_tavily_key, "brave": _check_brave_key}
    print(f"{OK} providers, in fallback order: {', '.join(providers) or '(none)'}")

    usable = False
    for name in providers:
        checker = known.get(name)
        if checker is None:
            print(f"{WARN} {name}: unknown provider - ignored at runtime")
            continue
        if checker():
            usable = True

    if not usable:
        print(f"{BAD} no research provider is usable - the brief will fall back to model knowledge")
        _fail("no usable research provider")


def _check_tavily_key() -> bool:
    """Returns True if Tavily is usable. A rejected/rate-limited key is a
    hard failure; an absent key is just skipped (it may be the fallback)."""
    if not settings.tavily_api_key:
        print(f"{WARN} tavily: TAVILY_API_KEY not set - skipped")
        return False
    try:
        r = httpx.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": _RESEARCH_QUERY,
                "search_depth": "basic",
                "max_results": 1,
            },
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} tavily: could not reach Tavily: {exc}")
        _fail("Tavily unreachable")
        return False

    if r.status_code == 200:
        print(f"{OK} tavily: key valid, search working")
        return True
    if r.status_code in (401, 403):
        print(f"{BAD} tavily: key rejected. Make a new one at tavily.com")
        _fail("TAVILY_API_KEY invalid")
    elif r.status_code == 429:
        print(f"{BAD} tavily: rate limited or out of search credits - check app.tavily.com")
        _fail("Tavily rate limited or out of credit")
    else:
        print(f"{WARN} tavily: unexpected response {r.status_code}: {r.text[:120]}")
    return False


def _check_brave_key() -> bool:
    """Returns True if Brave is usable. Same rule as Tavily: absent key is a
    skip, rejected key is a failure."""
    if not settings.brave_api_key:
        print(f"{WARN} brave: BRAVE_API_KEY not set - skipped")
        return False
    try:
        r = httpx.get(
            "https://api.search.brave.com/res/v1/web/search",
            params={"q": _RESEARCH_QUERY, "count": 1},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.brave_api_key,
            },
            timeout=20.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} brave: could not reach Brave: {exc}")
        _fail("Brave unreachable")
        return False

    if r.status_code == 200:
        print(f"{OK} brave: key valid, search working")
        return True
    if r.status_code in (401, 403):
        print(f"{BAD} brave: key rejected. Check BRAVE_API_KEY at api-dashboard.search.brave.com")
        _fail("BRAVE_API_KEY invalid")
    elif r.status_code == 429:
        print(f"{BAD} brave: rate limited or out of quota - check api-dashboard.search.brave.com")
        _fail("Brave rate limited or out of quota")
    else:
        print(f"{WARN} brave: unexpected response {r.status_code}: {r.text[:120]}")
    return False


def check_web() -> None:
    print("\nWeb console (web/)")
    if shutil.which("node") is None or shutil.which("npm") is None:
        print(f"{BAD} node/npm not found on PATH")
        _fail("node/npm missing")
        return
    print(f"{OK} node and npm on PATH")

    web_dir = ROOT / "web"
    if not (web_dir / "package.json").exists():
        print(f"{BAD} web/package.json missing - is this a full checkout?")
        _fail("web/package.json missing")
        return

    if not (web_dir / "node_modules").exists():
        print(f"{WARN} web/node_modules missing - start.ps1 installs it on first run")
        return

    print(f"{OK} web dependencies installed")


def check_roles_and_modes() -> None:
    print("\nInterview surface (config.yaml)")
    # There's no configured role list any more - the candidate types their
    # own target role, and it's what drives research.py. Only the mode list
    # is actually fixed configuration worth checking here.
    if not settings.modes:
        print(f"{BAD} no modes configured under interviewer.modes")
        _fail("no modes configured")
    else:
        print(f"{OK} {len(settings.modes)} mode(s): {', '.join(settings.modes)}")
    print(
        f"{OK} interview length: {settings.min_questions}-{settings.max_questions}"
        " questions (coverage-driven, no clock)"
    )


def _run(check) -> None:
    """Run one check. A check that blows up is a failed check, not a crash.

    The whole point of this command is to tell you what is wrong. Letting an
    exception escape means the remaining checks never run and you get a stack
    trace instead of a list - the least useful moment for it to stop talking.
    """
    try:
        check()
    except Exception as exc:  # noqa: BLE001
        name = check.__name__.replace("check_", "")
        print(f"{BAD} {name} check failed: {type(exc).__name__}: {exc}")
        _fail(f"{name} check crashed")


def main(argv: list[str] | None = None) -> int:
    print("\nCerebrum - checking your setup")
    print("=" * 62)

    for check in (
        check_llm,
        check_deepgram,
        check_tts,
        check_research,
        check_web,
        check_roles_and_modes,
    ):
        _run(check)

    print("\n" + "=" * 62)
    if _failures:
        print(f"{len(_failures)} problem(s) to fix:\n")
        for f in _failures:
            print(f"  - {f}")
        print()
        return 1

    print("Everything checks out. Start the bridge:\n")
    print("  python -m interview_agent.bridge\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
