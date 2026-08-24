"""The one LLM client, shared by everything that makes a plain (non-pipeline)
model call - resume structuring and the text-harness interview loop.

Cerebras's API is OpenAI-compatible, so both providers are the same client
with a different base_url and key. pipeline.py doesn't use this: pipecat has
its own per-provider service classes for the voice path.
"""

from __future__ import annotations

from openai import AsyncOpenAI

from interview_agent.config import settings

CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"

# A fresh AsyncOpenAI() opens its own httpx connection pool that nothing ever
# closes; an interview runs many turns through here, so a new client per call
# would leak a socket per question. Built once, lazily, and reused.
_client_instance: AsyncOpenAI | None = None


def client() -> AsyncOpenAI:
    global _client_instance
    if _client_instance is None:
        if settings.llm_provider == "cerebras":
            _client_instance = AsyncOpenAI(
                api_key=settings.cerebras_api_key, base_url=CEREBRAS_BASE_URL
            )
        else:
            _client_instance = AsyncOpenAI(api_key=settings.openai_api_key)
    return _client_instance
