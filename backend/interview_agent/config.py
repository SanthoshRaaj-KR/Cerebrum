"""Config loading: secrets from .env, tunables from config.yaml."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent.parent

load_dotenv(ROOT / ".env")

# Only Deepgram is unconditionally required - it does both STT and TTS, so
# every voice session needs it. The LLM key depends on interviewer.provider,
# and Cartesia only matters if voice.tts.provider selects it; both are
# checked against the actual config at load time rather than demanded from
# everyone.
_REQUIRED = ["DEEPGRAM_API_KEY"]


@dataclass
class Settings:
    deepgram_api_key: str
    openai_api_key: str = ""
    cerebras_api_key: str = ""
    cartesia_api_key: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    # -- config.yaml sections -------------------------------------------------

    def _section(self, name: str) -> dict[str, Any]:
        return self.raw.get(name, {})

    @property
    def candidate(self) -> dict[str, Any]:
        return self._section("candidate")

    @property
    def interviewer(self) -> dict[str, Any]:
        return self._section("interviewer")

    @property
    def voice(self) -> dict[str, Any]:
        return self._section("voice")

    @property
    def fresher(self) -> bool:
        return bool(self.candidate.get("fresher", True))

    @property
    def llm_provider(self) -> str:
        return str(self.interviewer.get("provider", "openai")).lower()

    @property
    def model(self) -> str:
        default = "gpt-oss-120b" if self.llm_provider == "cerebras" else "gpt-4o-mini"
        return str(self.interviewer.get("model", default))

    @property
    def llm_api_key(self) -> str:
        """The key for whichever provider is selected."""
        return (
            self.cerebras_api_key
            if self.llm_provider == "cerebras"
            else self.openai_api_key
        )

    @property
    def remember_turns(self) -> int:
        return int(self.interviewer.get("remember_turns", 20))

    @property
    def modes(self) -> list[str]:
        return list(self.interviewer.get("modes", []))

    @property
    def questions_per_session(self) -> int:
        # Below 3 there's no interview to speak of; above 12 the plan and
        # the history stop fitting comfortably in one session.
        return max(3, min(12, int(self.interviewer.get("questions_per_session", 6))))

    @property
    def tts_provider(self) -> str:
        return str((self.voice.get("tts") or {}).get("provider", "deepgram")).lower()

    @property
    def tts_voice_id(self) -> str:
        return str((self.voice.get("tts") or {}).get("voice_id", "")).strip()


def load_settings() -> Settings:
    missing = [k for k in _REQUIRED if not os.environ.get(k)]
    if missing:
        print(
            "\nInterview Agent cannot start - missing environment variables:\n"
            + "".join(f"  {k}\n" for k in missing)
            + "\nCopy .env.example to .env and fill it in.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    config_path = ROOT / "config.yaml"
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

    settings = Settings(
        deepgram_api_key=os.environ["DEEPGRAM_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        cerebras_api_key=os.environ.get("CEREBRAS_API_KEY", "").strip(),
        cartesia_api_key=os.environ.get("CARTESIA_API_KEY", "").strip(),
        raw=raw,
    )

    if not settings.llm_api_key:
        needed = (
            "CEREBRAS_API_KEY" if settings.llm_provider == "cerebras" else "OPENAI_API_KEY"
        )
        other = "openai" if settings.llm_provider == "cerebras" else "cerebras"
        print(
            f"\nInterview Agent cannot start - config.yaml sets"
            f" interviewer.provider to {settings.llm_provider}, but {needed} is"
            f" not in .env.\nEither add the key, or switch the provider to"
            f" {other}.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if settings.tts_provider == "cartesia" and not settings.cartesia_api_key:
        print(
            "\nInterview Agent cannot start - config.yaml sets"
            " voice.tts.provider to cartesia, but CARTESIA_API_KEY is not in"
            " .env.\nEither add the key, or set the provider back to deepgram"
            " (which needs no extra key).\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return settings


settings = load_settings()
