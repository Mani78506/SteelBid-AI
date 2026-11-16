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


def test_production_worker_does_not_require_browser_only_settings():
    settings = _production_settings(
        service_role="worker",
        secure_cookies=False,
        cors_origins="http://localhost:5173",
    )
    assert settings.is_production and settings.service_role == "worker"


def test_public_demo_can_be_explicitly_enabled_without_enabling_seed_mode():
    settings = _production_settings(public_demo_enabled=True)
    assert settings.public_demo_enabled is True
    assert settings.demo_mode is False
