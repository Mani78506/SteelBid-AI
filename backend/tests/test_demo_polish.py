from uuid import UUID

from sqlalchemy import delete

from app.models.market import MarketIngestionRun, MarketPriceAlertEvent, PriceObservation
from app.models.ops import Notification


def _showcase(client):
    org = next(item for item in client.get("/api/v1/auth/organizations").json() if "Market Showcase" in item["name"])
    assert client.post("/api/v1/auth/switch-organization", json={"organization_id": org["id"]}).status_code == 200
    return org


def test_showcase_demo_alert_replay_and_notification_drawer_data(railbuild_client, db):
    org = _showcase(railbuild_client)
    replay = railbuild_client.post("/api/v1/market/demo/trigger-alert")
    assert replay.status_code == 200, replay.text
    assert replay.json()["inserted"] in (0, 1)
    notifications = railbuild_client.get("/api/v1/notifications")
    assert notifications.status_code == 200
    market = next(item for item in notifications.json()["items"] if item["kind"] == "MARKET_ALERT")
    assert market["link"].startswith("/market?observation_id=")
    assert railbuild_client.post(f"/api/v1/notifications/{market['id']}/read").status_code == 200

    # Tests share the seeded database.  Remove only replay artifacts, leaving
    # the baseline data available for existing alert tests.
    org_id = UUID(org["id"])
    db.execute(delete(MarketPriceAlertEvent).where(MarketPriceAlertEvent.organization_id == org_id))
    db.execute(delete(Notification).where(Notification.organization_id == org_id, Notification.kind == "MARKET_ALERT"))
    db.execute(delete(PriceObservation).where(PriceObservation.organization_id == org_id,
        PriceObservation.external_observation_id.like("showcase-alert-replay-%")))
    db.execute(delete(MarketIngestionRun).where(MarketIngestionRun.organization_id == org_id,
        MarketIngestionRun.provider_key == "DEMO_PROVIDER"))
    db.commit()


def test_demo_replay_is_not_available_to_normal_demo_org(apex_client):
    assert apex_client.post("/api/v1/market/demo/trigger-alert").status_code == 404
