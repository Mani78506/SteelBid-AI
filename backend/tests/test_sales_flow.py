"""Primary workflow + CRUD: inquiries → quotations → approval → SO → reserve → shortage PR.
Also: materials, customers, suppliers CRUD, dashboard aggregation, audit events."""
from decimal import Decimal as D

from tests.conftest import unique


def _customer(apex_client, search="Konkan"):
    return apex_client.get(f"/api/v1/customers?search={search}").json()["items"][0]


def _beam(apex_client):
    return apex_client.get("/api/v1/materials?search=ISMB 200").json()["items"][0]


class TestPrimaryWorkflow:
    """Part M: 100 MT inquiry → 40 available → 60 shortage → compare 3 offers →
    quotation at target margin → approve → SO → reserve 40 → PR for 60 → dashboard updates."""

    def test_full_chain(self, apex_client, railbuild_client):
        customer = _customer(apex_client)
        beam = _beam(apex_client)
        ref = unique("INQ-WF")

        av_before = apex_client.get(
            f"/api/v1/materials/availability?material_id={beam['id']}").json()[0]
        assert D(av_before["available"]) == D("40")
        assert D(av_before["quality_held"]) == D("15")

        # 1. Inquiry for 100 MT
        inq = apex_client.post("/api/v1/inquiries", json={
            "customer_id": customer["id"], "reference": ref,
            "items": [{"material_id": beam["id"],
                       "description": "ISMB 200 Beam E250 — 100 MT",
                       "form": "BEAM", "grade": "E250", "quantity": "100", "unit": "MT"}]})
        assert inq.status_code == 201, inq.text
        inq_id = inq.json()["id"]

        # 2. Supplier comparison for the 60 MT shortfall (3 offers)
        cmp_ = apex_client.get(f"/api/v1/procurement/compare?material_id={beam['id']}").json()
        assert len(cmp_["items"]) == 3
        assert cmp_["items"][0]["landed_cost"] == "56200.0000"

        # 3. Quotation at 12% target margin using best landed cost
        qt = apex_client.post("/api/v1/quotations", json={
            "inquiry_id": inq_id, "customer_id": customer["id"], "target_margin": "0.12",
            "items": [{"material_id": beam["id"], "description": "ISMB 200 Beam E250",
                       "quantity": "100", "unit": "MT", "unit_cost": "56200"}]})
        assert qt.status_code == 201
        q = qt.json()
        assert q["versions"][-1]["total_estimated_cost"] == "5620000.0000"
        assert q["versions"][-1]["total_selling_price"] == "6386363.6364"
        assert q["versions"][-1]["gross_margin_pct"] == "0.120000"
        assert q["items"][0]["available_qty"] == "40.000000"
        assert q["items"][0]["shortage_qty"] == "60.000000"

        # invalid transition guard: convert before approval must fail
        assert apex_client.post(f"/api/v1/quotations/{q['id']}/convert").status_code == 409

        # 4. Submit + approve (immutability)
        assert apex_client.post(f"/api/v1/quotations/{q['id']}/submit").json()["status"] == "PENDING_APPROVAL"
        appr = apex_client.post(f"/api/v1/quotations/{q['id']}/approve", json={"comment": "ok"})
        assert appr.json()["status"] == "APPROVED"
        assert appr.json()["versions"][-1]["is_immutable"] is True

        # 5. Convert → sales order; idempotent re-convert returns same SO
        so1 = apex_client.post(f"/api/v1/quotations/{q['id']}/convert").json()
        so2 = apex_client.post(f"/api/v1/quotations/{q['id']}/convert").json()
        assert so1["id"] == so2["id"]
        assert so1["total_value"] == "6386363.6364"

        # 6. Reserve the 40 MT of eligible stock
        ok_lot = apex_client.get(
            f"/api/v1/inventory/stock-lots?material_id={beam['id']}&quality_status=OK"
        ).json()["items"][0]
        res = apex_client.post(f"/api/v1/sales-orders/{so1['id']}/reserve", json={
            "sales_order_item_id": so1["items"][0]["id"],
            "lot_id": ok_lot["id"], "quantity": "40"})
        assert res.status_code == 201, res.text
        av = apex_client.get(
            f"/api/v1/materials/availability?material_id={beam['id']}").json()[0]
        assert D(av["available"]) == D("0")

        # 7. Purchase request for the 60 MT shortage
        pr = apex_client.post("/api/v1/procurement/purchase-requests",
                              headers={"Idempotency-Key": unique("PRIDEM")}, json={
                                  "source_type": "SHORTAGE",
                                  "context": {"sales_order_id": so1["id"]},
                                  "items": [{"material_id": beam["id"], "quantity": "60",
                                             "unit": "MT"}]})
        assert pr.status_code == 201
        assert pr.json()["items"][0]["quantity"] == "60.000000"

        # dashboard already reflects the open shortage PR (before it is fulfilled below)
        dash_mid = apex_client.get("/api/v1/dashboard/summary").json()
        assert any(p["pr_number"] == pr.json()["number"]
                   for p in dash_mid["procurement_shortages"])

        # 8. Upload a PO from the best-ranked supplier, receive goods, stock updates
        suppliers = apex_client.get("/api/v1/suppliers?search=Sahyadri").json()["items"]
        po = apex_client.post("/api/v1/procurement/purchase-orders", json={
            "supplier_id": suppliers[0]["id"], "purchase_request_id": pr.json()["id"],
            "items": [{"material_id": beam["id"], "quantity": "60", "unit": "MT",
                       "unit_price": "56200"}]})
        assert po.status_code == 201
        po_id = po.json()["id"]
        assert apex_client.post(f"/api/v1/procurement/purchase-orders/{po_id}/approve").status_code == 200
        wh = apex_client.get("/api/v1/inventory/warehouses").json()[0]
        grn = apex_client.post("/api/v1/procurement/goods-receipts",
                               headers={"Idempotency-Key": unique("GRNIDEM")}, json={
                                   "purchase_order_id": po_id, "warehouse_id": wh["id"]})
        assert grn.status_code == 201, grn.text
        av = apex_client.get(
            f"/api/v1/materials/availability?material_id={beam['id']}").json()[0]
        # 40 reserved + 60 newly received eligible; the fulfilled PR left shortages
        assert D(av["available"]) == D("60")

        # 9. Dashboard reflects the new state (PO received → PR fulfilled)
        dash = apex_client.get("/api/v1/dashboard/summary").json()
        assert "open_sales_order_value" in dash["kpis"]
        pr_after = apex_client.get(f"/api/v1/procurement/purchase-requests/{pr.json()['id']}").json()
        assert pr_after["status"] == "FULFILLED"

        # 10. Audit trail contains the key business events
        events = apex_client.get("/api/v1/audit/events?page_size=100").json()["items"]
        actions = {e["action"] for e in events}
        assert {"quotation.create", "quotation.approve", "quotation.convert",
                "sales_order.reserve", "purchase_request.create",
                "goods_receipt.post"}.issubset(actions)

        # 11. Persistence across new client (browser-refresh equivalent)
        from fastapi.testclient import TestClient
        from app.main import create_app
        fresh = TestClient(create_app())
        fresh.post("/api/v1/auth/login",
                   json={"email": "admin@apex.demo", "password": "SteelBid#Demo2026"})
        got = fresh.get(f"/api/v1/sales-orders/{so1['id']}")
        assert got.status_code == 200
        assert D(got.json()["items"][0]["reserved_qty"]) == D("40")

        # 12. Cross tenant cannot see this inquiry by ID
        assert railbuild_client.get(f"/api/v1/inquiries/{inq_id}").status_code == 404


class TestMaterialsCrud:
    def test_create_search_update_deactivate(self, apex_client):
        sku = unique("TST-MAT")
        resp = apex_client.post("/api/v1/materials", json={
            "sku": sku, "name": "Test Plate E350 25mm", "form": "PLATE", "grade": "E350",
            "standard": "IS 2062", "specification": {"thickness_mm": 25}})
        assert resp.status_code == 201
        mat = resp.json()
        dup = apex_client.post("/api/v1/materials", json={
            "sku": sku, "name": "duplicate", "form": "PLATE", "grade": "E350"})
        assert dup.status_code == 409
        found = apex_client.get(f"/api/v1/materials?search={sku}").json()
        assert found["total"] == 1
        upd = apex_client.patch(f"/api/v1/materials/{mat['id']}",
                                json={"low_stock_threshold": "5", "is_active": False})
        assert upd.status_code == 200
        assert upd.json()["is_active"] is False


class TestSuppliersCrud:
    def test_supplier_crud_and_capability_filter(self, apex_client):
        code = unique("SUP-T")
        created = apex_client.post("/api/v1/suppliers", json={
            "code": code, "name": "[DEMO] Test Supplier", "city": "Testville",
            "material_capabilities": ["BEAM", "TESTCAP"]})
        assert created.status_code == 201
        sup = created.json()
        apex_client.patch(f"/api/v1/suppliers/{sup['id']}", json={"rating": "4.75"})
        filtered = apex_client.get("/api/v1/suppliers?capability=TESTCAP").json()
        assert any(s["id"] == sup["id"] for s in filtered["items"])
        detail = apex_client.get(f"/api/v1/suppliers/{sup['id']}").json()
        assert detail["rating"] == "4.75"


class TestDashboardAggregation:
    def test_kpis_are_db_derived(self, apex_client):
        dash = apex_client.get("/api/v1/dashboard/summary").json()
        kpis = dash["kpis"]
        # sanity: counts match seeded org (Apex)
        assert kpis["material_count"] >= 12
        assert kpis["warehouse_count"] == 2
        assert kpis["supplier_count"] >= 3
        assert D(kpis["inventory_valuation"]["value"]) > 0
        assert sum(kpis["quotation_status_distribution"].values()) >= 4
        for section in ("priorities", "recent_inquiries", "price_observations",
                        "upcoming_dispatches", "recent_activity"):
            assert section in dash

    def test_briefing_grounded(self, apex_client):
        b = apex_client.get("/api/v1/dashboard/briefing").json()
        assert "items" in b and "generated_at" in b
        assert all("text" in i for i in b["items"])

    def test_dashboard_consistent_with_valuation_endpoint(self, apex_client, metro_client):
        # dashboard KPI equals the inventory valuation endpoint for each org independently
        for c in (apex_client, metro_client):
            dash = c.get("/api/v1/dashboard/summary").json()
            val = c.get("/api/v1/inventory/valuation").json()
            assert dash["kpis"]["inventory_valuation"]["value"] == val["total_value"]


class TestAudit:
    def test_material_create_writes_audit(self, apex_client):
        sku = unique("AUD-MAT")
        created = apex_client.post("/api/v1/materials", json={
            "sku": sku, "name": "Audit Test", "form": "ANGLE", "grade": "E250"}).json()
        events = apex_client.get(
            "/api/v1/audit/events?action=material.create&page_size=50").json()["items"]
        assert any(str(created["id"]) == str(e["entity_id"]) for e in events)
        assert all(e["request_id"] for e in events[:5])
