"""Pluggable LLM provider interface.

Default provider is deterministic and offline ("mock"): structured extraction is performed
with rule-based parsing and explanations are generated strictly from database records.
Configure llm_provider=openai-compatible with base_url/api_key/model to plug a real LLM.
"""
from typing import Protocol

from app.config import get_settings

settings = get_settings()


class LLMProvider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        ...


class MockProvider:
    name = "mock-deterministic"

    def complete(self, system: str, user: str) -> str:
        # Intentionally never inventing data; callers build grounded content themselves.
        return ""


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self):
        import httpx
        self._client = httpx.Client(timeout=60)
        self._base = settings.llm_base_url.rstrip("/")
        self._key = settings.llm_api_key
        self._model = settings.llm_model

    def complete(self, system: str, user: str) -> str:
        resp = self._client.post(
            f"{self._base}/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={"model": self._model, "temperature": 0,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]})
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


def get_provider() -> LLMProvider:
    if settings.llm_provider == "openai-compatible" and settings.llm_base_url and settings.llm_api_key:
        return OpenAICompatibleProvider()
    return MockProvider()
