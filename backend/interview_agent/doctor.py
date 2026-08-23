"""CLI: check everything before you rely on it mid-interview.

    python -m interview_agent.doctor

Validates the three API keys (Cerebras, Deepgram, Cartesia) against the
real services, so a bad key surfaces here rather than as a dead mic or a
silent interviewer mid-session.
"""

from __future__ import annotations

import sys

import httpx

from interview_agent.config import settings

OK = "  [ ok ]"
BAD = "  [FAIL]"
WARN = "  [warn]"

_failures: list[str] = []


def _fail(msg: str) -> None:
    _failures.append(msg)


def check_cerebras() -> None:
    print("\nCerebras (the interviewer's model)")
    try:
        r = httpx.get(
            "https://api.cerebras.ai/v1/models",
            headers={"Authorization": f"Bearer {settings.cerebras_api_key}"},
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} could not reach Cerebras: {exc}")
        _fail("Cerebras unreachable")
        return

    if r.status_code == 200:
        wanted = settings.model
        available = {m["id"] for m in r.json().get("data", [])}
        print(f"{OK} key valid")
        if wanted in available:
            print(f"{OK} model {wanted} available")
        else:
            print(f"{WARN} model {wanted} not in your account's model list")
    elif r.status_code == 401:
        print(f"{BAD} key rejected. Make a new one at cloud.cerebras.ai")
        _fail("CEREBRAS_API_KEY invalid")
    elif r.status_code == 429:
        print(f"{BAD} rate limited or out of credit - check your usage")
        _fail("Cerebras quota")
    else:
        print(f"{WARN} unexpected response {r.status_code}: {r.text[:120]}")


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


def check_cartesia() -> None:
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

    if r.status_code == 200:
        print(f"{OK} key valid")
    elif r.status_code in (401, 403):
        print(f"{BAD} key rejected. Check CARTESIA_API_KEY")
        _fail("CARTESIA_API_KEY invalid")
    else:
        print(f"{WARN} unexpected response {r.status_code}: {r.text[:120]}")


def check_roles_and_modes() -> None:
    print("\nInterview surface (config.yaml)")
    if not settings.roles:
        print(f"{BAD} no roles configured under interviewer.roles")
        _fail("no roles configured")
    else:
        print(f"{OK} {len(settings.roles)} role(s): {', '.join(settings.roles)}")
    if not settings.modes:
        print(f"{BAD} no modes configured under interviewer.modes")
        _fail("no modes configured")
    else:
        print(f"{OK} {len(settings.modes)} mode(s): {', '.join(settings.modes)}")


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
    print("\nInterview Agent - checking your setup")
    print("=" * 62)

    for check in (
        check_cerebras,
        check_deepgram,
        check_cartesia,
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
