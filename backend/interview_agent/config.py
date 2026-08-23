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

_REQUIRED = ["CEREBRAS_API_KEY", "DEEPGRAM_API_KEY", "CARTESIA_API_KEY"]


@dataclass
class Settings:
    cerebras_api_key: str
    deepgram_api_key: str
    cartesia_api_key: str
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
    def model(self) -> str:
        return str(self.interviewer.get("model", "llama-3.3-70b"))

    @property
    def remember_turns(self) -> int:
        return int(self.interviewer.get("remember_turns", 20))

    @property
    def roles(self) -> list[str]:
        return list(self.interviewer.get("roles", []))

    @property
    def modes(self) -> list[str]:
        return list(self.interviewer.get("modes", []))


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

    return Settings(
        cerebras_api_key=os.environ["CEREBRAS_API_KEY"],
        deepgram_api_key=os.environ["DEEPGRAM_API_KEY"],
        cartesia_api_key=os.environ["CARTESIA_API_KEY"],
        raw=raw,
    )


settings = load_settings()
