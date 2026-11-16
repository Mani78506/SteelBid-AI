"""Database-free safeguards for AI-assisted tender candidate extraction."""
from app.ai import extraction


class Provider:
    name = "openai-compatible"

    def __init__(self, response: str):
        self.response = response

    def complete(self, _system: str, _user: str) -> str:
        return self.response


def test_ai_candidates_are_normalized_and_remain_review_only(monkeypatch):
    monkeypatch.setattr(extraction, "get_provider", lambda: Provider('''{"candidates":[{
        "raw_description":"ISMB 300 beam, IS 2062 E250, 24 MT",
        "form":"BEAM", "grade":"E250", "standard":"IS 2062",
        "dimensions":"300 mm", "quantity":"24", "unit":"MT", "confidence":0.91
    }]}'''))
    rows, method, warnings = extraction.extract_boq_candidates("ISMB 300 beam, IS 2062 E250, 24 MT")
    assert method == "ai-structured" and warnings == []
    assert rows[0]["unit"] == "MT" and rows[0]["quantity"] == "24.000000"
    assert rows[0]["specification"]["standard"] == "IS 2062"


def test_ai_failure_is_explicit_and_uses_grounded_rule_fallback(monkeypatch):
    monkeypatch.setattr(extraction, "get_provider", lambda: Provider("not json"))
    rows, method, warnings = extraction.extract_boq_candidates("ISMC 200 channel, E250, 12 MT")
    assert method == "rule-based-fallback"
    assert rows[0]["form"] == "CHANNEL"
    assert "unavailable" in warnings[0]


def test_ai_cannot_invent_an_unsupported_unit(monkeypatch):
    monkeypatch.setattr(extraction, "get_provider", lambda: Provider('''{"candidates":[{
        "raw_description":"Beam", "quantity":"12", "unit":"TRUCKLOAD", "confidence":1
    }]}'''))
    rows, method, warnings = extraction.extract_boq_candidates("Beam description without quantity")
    assert rows == [] and method == "rule-based-fallback"
    assert warnings
