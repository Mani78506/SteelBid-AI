"""pytest fixtures — tests run against the steelbid_test database, fully reset per session."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = (
    "postgresql+psycopg://steelbid:steelbid_dev_password@127.0.0.1:5432/steelbid_test")
os.environ["CELERY_ALWAYS_EAGER"] = "true"
os.environ["DEMO_MODE"] = "true"
os.environ["DEMO_ADMIN_PASSWORD"] = "SteelBid#Demo2026"

from app.database import Base, engine, SessionLocal  # noqa: E402
from app.main import create_app  # noqa: E402


def reset_database():
    # deterministic full reset between suites (test DB only, never dev/prod DB)
    assert "steelbid_test" in engine.url.database
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="session")
def seeded():
    reset_database()
    from app.seed.run import run_seed
    run_seed()
    yield SessionLocal
    reset_database()


@pytest.fixture()
def db(seeded):
    session = seeded()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(seeded):
    app = create_app()
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str = "SteelBid#Demo2026") -> TestClient:
    resp = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return client


def _fresh_client(seeded, email: str, org_name: str | None = None) -> TestClient:
    """Independent TestClient (own cookie jar), optionally switched to a named org."""
    c = TestClient(create_app())
    login(c, email)
    if org_name:
        orgs = c.get("/api/v1/auth/organizations").json()
        target = next(o for o in orgs if org_name in o["name"])
        c.post("/api/v1/auth/switch-organization", json={"organization_id": target["id"]})
    c.__enter__()  # keep open until test end (test-only convenience)
    return c


@pytest.fixture()
def apex_client(seeded):
    yield _fresh_client(seeded, "admin@apex.demo")


@pytest.fixture()
def metro_client(seeded):
    yield _fresh_client(seeded, "admin@metro.demo")


@pytest.fixture()
def precision_client(seeded):
    yield _fresh_client(seeded, "admin@precision.demo")


@pytest.fixture()
def railbuild_client(seeded):
    yield _fresh_client(seeded, "admin@railbuild.demo", org_name="RailBuild")


@pytest.fixture()
def viewer_client(seeded):
    yield _fresh_client(seeded, "viewer@apex.demo")


def unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}".upper()
