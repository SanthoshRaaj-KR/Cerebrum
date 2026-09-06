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
    tavily_api_key: str = ""
    brave_api_key: str = ""
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
    def interview(self) -> dict[str, Any]:
        return self._section("interview")

    @property
    def research(self) -> dict[str, Any]:
        return self._section("research")

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
    def scorer_model(self) -> str:
        """The model for evaluation calls that get to take their time - the
        background running score and the wrong-claim double-check. Judging
        subtly-wrong technical claims is where a stronger model earns its
        cost; asking the next question doesn't need one. Must be served by
        the same provider as interviewer.model; falls back to it when unset.
        """
        return str(self.interviewer.get("scorer_model", "") or self.model)

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
    def min_questions(self) -> int:
        # The interview won't wrap up before this many questions even if
        # coverage looks complete early.
        return max(1, int(self.interview.get("min_questions", 8)))

    @property
    def max_questions(self) -> int:
        # Hard ceiling: the interview always wraps by here regardless of
        # coverage. Overridable per session via the start payload (the
        # quality-check harness uses it) - see bridge.start_session.
        return max(self.min_questions, int(self.interview.get("max_questions", 22)))

    @property
    def research_enabled(self) -> bool:
        return bool(self.research.get("enabled", True))

    @property
    def research_provider(self) -> str:
        """Back-compat only: the old singular key. research_providers is
        what the search chain reads now."""
        return str(self.research.get("provider", "tavily")).lower()

    @property
    def research_providers(self) -> list[str]:
        """Search providers to try, in fallback order. Prefers the list key
        research.providers; falls back to the old singular research.provider
        so an existing config.yaml keeps working."""
        raw = self.research.get("providers")
        if isinstance(raw, list) and raw:
            return [str(p).strip().lower() for p in raw if str(p).strip()]
        return [self.research_provider]

    @property
    def research_cache_days(self) -> int:
        return max(0, int(self.research.get("cache_days", 14)))

    @property
    def research_max_results(self) -> int:
        return max(1, min(10, int(self.research.get("max_results", 5))))

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
            "\nCerebrum cannot start - missing environment variables:\n"
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
        tavily_api_key=os.environ.get("TAVILY_API_KEY", "").strip(),
        brave_api_key=os.environ.get("BRAVE_API_KEY", "").strip(),
        raw=raw,
    )

    if not settings.llm_api_key:
        needed = (
            "CEREBRAS_API_KEY" if settings.llm_provider == "cerebras" else "OPENAI_API_KEY"
        )
        other = "openai" if settings.llm_provider == "cerebras" else "cerebras"
        print(
            f"\nCerebrum cannot start - config.yaml sets"
            f" interviewer.provider to {settings.llm_provider}, but {needed} is"
            f" not in .env.\nEither add the key, or switch the provider to"
            f" {other}.\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if settings.tts_provider == "cartesia" and not settings.cartesia_api_key:
        print(
            "\nCerebrum cannot start - config.yaml sets"
            " voice.tts.provider to cartesia, but CARTESIA_API_KEY is not in"
            " .env.\nEither add the key, or set the provider back to deepgram"
            " (which needs no extra key).\n",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if settings.research_enabled:
        _provider_keys = {
            "tavily": settings.tavily_api_key,
            "brave": settings.brave_api_key,
        }
        if not any(_provider_keys.get(p) for p in settings.research_providers):
            listed = ", ".join(settings.research_providers) or "(none)"
            print(
                "\nCerebrum cannot start - config.yaml has research.enabled"
                f" true with providers [{listed}], but none of them have a"
                " key in .env.\nAdd TAVILY_API_KEY or BRAVE_API_KEY, or set"
                " research.enabled to false (the interview still runs, just"
                " without live research grounding).\n",
                file=sys.stderr,
            )
            raise SystemExit(1)

    return settings


settings = load_settings()
