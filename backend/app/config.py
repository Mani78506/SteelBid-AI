"""Environment-validated settings. All configuration flows through here."""
from functools import lru_cache
from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    environment: str = "development"  # development | test | production
    database_url: str = "postgresql+psycopg://steelbid:steelbid_dev_password@127.0.0.1:5432/steelbid"
    redis_url: str = "redis://127.0.0.1:6379/0"
    celery_always_eager: bool = True  # local dev default; deployment sets False
    # API instances serve browser traffic; worker instances only process jobs.
    # Railway sets this to "worker" for the Celery service via SERVICE_ROLE.
    service_role: str = "api"

    session_cookie_name: str = "steelbid_session"
    session_ttl_hours: int = 72
    # Keep COOKIE_SECURE as a backwards-compatible alias for existing local
    # environment files while exposing the field's canonical name.
    secure_cookies: bool = Field(default=False, validation_alias=AliasChoices("SECURE_COOKIES", "COOKIE_SECURE"))
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    secret_key: str = "dev-only-insecure-secret-change-me"
    request_body_limit_bytes: int = 25 * 1024 * 1024

    # Development-only demo credentials (never used in production seed guard)
    demo_mode: bool = True
    demo_admin_email: str = "admin@railbuild.demo"
    demo_admin_password: str = "DemoAdmin#2026"
    # Public viewing is independently opt-in.  It never enables seeding or
    # write-capable demo users, and production still requires DEMO_MODE=false.
    public_demo_enabled: bool = False
    public_demo_viewer_email: str = "viewer@apex.demo"
    demo_viewer_email: str = "viewer@apex.demo"

    # Pluggable LLM provider: "mock" (deterministic, offline),
    # "openai-compatible", or "gemini".  Credentials remain environment-only.
    llm_provider: str = "mock"
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    gemini_api_key: str = Field(default="", validation_alias=AliasChoices("GEMINI_API_KEY", "GOOGLE_API_KEY"))
    gemini_model: str = "gemini-2.5-flash"

    s3_endpoint_url: str = ""
    s3_bucket: str = "steelbid-documents"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    upload_dir: str = "uploads"  # local object-storage stand-in

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        # Hosting providers (Railway/Heroku) hand out bare postgres(s):// URLs;
        # this app ships psycopg 3 only, so pin the driver.
        if isinstance(v, str):
            for scheme in ("postgres://", "postgresql://"):
                if v.startswith(scheme):
                    return "postgresql+psycopg://" + v[len(scheme):]
        return v

    @model_validator(mode="after")
    def _reject_insecure_production_defaults(self) -> "Settings":
        """Production must never silently fall back to local demo settings."""
        if self.environment.lower() != "production":
            return self
        problems: list[str] = []
        if self.database_url == "postgresql+psycopg://steelbid:steelbid_dev_password@127.0.0.1:5432/steelbid":
            problems.append("DATABASE_URL must be explicitly configured")
        if self.secret_key == "dev-only-insecure-secret-change-me" or len(self.secret_key) < 32:
            problems.append("SECRET_KEY must be a non-default value of at least 32 characters")
        if self.demo_mode:
            problems.append("DEMO_MODE must be false")
        # Cookie and CORS requirements apply only to the HTTP service. A Celery
        # worker neither emits cookies nor accepts browser requests.
        if self.service_role.lower() != "worker":
            if not self.secure_cookies:
                problems.append("SECURE_COOKIES must be true")
            if not self.cors_origin_list or any(origin.startswith("http://") for origin in self.cors_origin_list):
                problems.append("CORS_ORIGINS must contain explicit HTTPS origins")
        if problems:
            raise ValueError("Invalid production configuration: " + "; ".join(problems))
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
