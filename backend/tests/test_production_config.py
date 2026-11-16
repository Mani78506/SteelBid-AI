import pytest

from app.config import Settings


def _production_settings(**overrides):
    values = {
        "environment": "production",
        "database_url": "postgresql+psycopg://release:strong-password@db.example/steelbid_release",
        "secret_key": "a" * 32,
        "secure_cookies": True,
        "cors_origins": "https://steelbid.example",
        "demo_mode": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_production_settings_reject_insecure_defaults():
    with pytest.raises(ValueError, match="Invalid production configuration"):
        _production_settings(secret_key="dev-only-insecure-secret-change-me", secure_cookies=False, demo_mode=True)


def test_production_settings_accepts_explicit_secure_values():
    settings = _production_settings()
    assert settings.is_production and settings.secure_cookies and not settings.demo_mode
