"""Pluggable LLM provider interface.

Default provider is deterministic and offline ("mock"): structured extraction is performed
with rule-based parsing and explanations are generated strictly from database records.
Configure llm_provider=openai-compatible or gemini to plug a real LLM. Credentials
are read only from process environment and are never logged or persisted.
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


class GeminiProvider:
    """Gemini's JSON-mode REST API behind the same narrow provider contract.

    The application sends only the locally filtered BOQ excerpt, not the complete
    tender document.  Downstream schema validation still rejects unsupported or
    implausible material values before any review candidates are persisted.
    """
    name = "gemini"

    def __init__(self):
        import httpx
        self._client = httpx.Client(timeout=60)
        self._key = settings.gemini_api_key
        self._model = settings.gemini_model

    def complete(self, system: str, user: str) -> str:
        response = self._client.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent",
            headers={"x-goog-api-key": self._key, "Content-Type": "application/json"},
            json={
                "systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
            },
        )
        response.raise_for_status()
        payload = response.json()
        parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        content = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        if not content:
            raise ValueError("Gemini returned no structured content")
        return content


def get_provider() -> LLMProvider:
    if settings.llm_provider == "gemini" and settings.gemini_api_key:
        return GeminiProvider()
    if settings.llm_provider == "openai-compatible" and settings.llm_base_url and settings.llm_api_key:
        return OpenAICompatibleProvider()
    return MockProvider()
