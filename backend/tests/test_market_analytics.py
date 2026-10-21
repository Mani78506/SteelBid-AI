from datetime import date, timedelta


def _add(client, *, price: str, observed_on: date, material: str, region: str = "West India", currency: str = "INR"):
    response = client.post("/api/v1/market/observations", json={
        "material_form": material, "grade": "E250", "region": region,
        "price_basis": "EX_WORKS", "price_per_unit": price,
        "currency": currency, "unit": "MT", "observed_on": observed_on.isoformat(),
    })
    assert response.status_code == 201, response.text
    return response.json()


class TestMarketAnalytics:
    def test_latest_history_and_movement_are_comparable(self, apex_client):
        today = date.today()
        _add(apex_client, price="50000.00", observed_on=today - timedelta(days=40), material="ANALYTICS_MOVEMENT")
        _add(apex_client, price="52000.00", observed_on=today - timedelta(days=20), material="ANALYTICS_MOVEMENT")
        _add(apex_client, price="55000.00", observed_on=today, material="ANALYTICS_MOVEMENT")
        params = "material_form=ANALYTICS_MOVEMENT&grade=E250&region=West%20India&price_basis=EX_WORKS&currency=INR&unit=MT"

        latest = apex_client.get(f"/api/v1/market/intelligence/latest?{params}")
        assert latest.status_code == 200
        data = latest.json()
        assert data["status"] == "ok"
        assert data["latest"]["price_per_unit"] == "55000.0000"
        assert data["movement"]["30"]["status"] == "ok"
        assert float(data["movement"]["30"]["percentage_change"]) == 0.1

        history = apex_client.get(f"/api/v1/market/intelligence/history?{params}&days=30").json()
        assert history["status"] == "ok"
        assert len(history["points"]) == 2

    def test_insufficient_history_never_fabricates_movement(self, apex_client):
        _add(apex_client, price="50000", observed_on=date.today(), material="ANALYTICS_SPARSE")
        params = "material_form=ANALYTICS_SPARSE&grade=E250&region=West%20India&price_basis=EX_WORKS"
        data = apex_client.get(f"/api/v1/market/intelligence/latest?{params}").json()
        assert data["movement"]["7"]["status"] == "insufficient_data"

    def test_regions_and_movers_do_not_cross_tenant_boundary(self, apex_client, metro_client):
        today = date.today()
        _add(apex_client, price="50000", observed_on=today - timedelta(days=35), material="ANALYTICS_REGIONAL", region="West India")
        _add(apex_client, price="55000", observed_on=today, material="ANALYTICS_REGIONAL", region="West India")
        _add(apex_client, price="53000", observed_on=today, material="ANALYTICS_REGIONAL", region="North India")

        regions = apex_client.get("/api/v1/market/intelligence/regions?material_form=ANALYTICS_REGIONAL&grade=E250&price_basis=EX_WORKS").json()
        assert regions["status"] == "ok"
        assert {row["region"] for row in regions["regions"]} >= {"West India", "North India"}
        movers = apex_client.get("/api/v1/market/intelligence/movers?days=30").json()
        assert any(row["material_form"] == "ANALYTICS_REGIONAL" for row in movers["increases"])

        other = metro_client.get("/api/v1/market/intelligence/latest?material_form=ANALYTICS_REGIONAL&grade=E250&region=West%20India&price_basis=EX_WORKS").json()
        assert other["status"] == "insufficient_data"
