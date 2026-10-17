"""Environment-validated settings. All configuration flows through here."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://steelbid:steelbid_dev_password@127.0.0.1:5432/steelbid"
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_always_eager: bool = True  # local dev default; deployment sets False

    session_cookie_name: str = "steelbid_session"
    session_ttl_hours: int = 72
    secure_cookies: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    secret_key: str = "dev-only-insecure-secret-change-me"
    request_body_limit_bytes: int = 25 * 1024 * 1024

    # Development-only demo credentials (never used in production seed guard)
    demo_mode: bool = True
    demo_admin_email: str = "admin@railbuild.demo"
    demo_admin_password: str = "DemoAdmin#2026"

    # Pluggable LLM provider: "mock" (deterministic, offline) | "openai-compatible"
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    s3_endpoint_url: str = ""
    s3_bucket: str = "steelbid-documents"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    upload_dir: str = "uploads"  # local object-storage stand-in

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
