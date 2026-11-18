from app.ai import providers


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"candidates": [{"content": {"parts": [{"text": '{"candidates": []}'}]}}]}


class _Client:
    def __init__(self):
        self.request = None

    def post(self, url, *, headers, json):
        self.request = {"url": url, "headers": headers, "json": json}
        return _Response()


def test_gemini_provider_requests_json_without_exposing_key(monkeypatch):
    monkeypatch.setattr(providers.settings, "gemini_api_key", "test-secret")
    monkeypatch.setattr(providers.settings, "gemini_model", "gemini-test")
    provider = providers.GeminiProvider()
    client = _Client()
    provider._client = client

    assert provider.complete("fixed system", "filtered context") == '{"candidates": []}'
    assert client.request["url"].endswith("/gemini-test:generateContent")
    assert client.request["headers"]["x-goog-api-key"] == "test-secret"
    assert client.request["json"]["generationConfig"]["responseMimeType"] == "application/json"
    assert client.request["json"]["contents"][0]["parts"][0]["text"] == "filtered context"


def test_gemini_provider_is_selected_only_when_configured(monkeypatch):
    monkeypatch.setattr(providers.settings, "llm_provider", "gemini")
    monkeypatch.setattr(providers.settings, "gemini_api_key", "configured")
    assert providers.get_provider().name == "gemini"

    monkeypatch.setattr(providers.settings, "gemini_api_key", "")
    assert providers.get_provider().name == "mock-deterministic"
