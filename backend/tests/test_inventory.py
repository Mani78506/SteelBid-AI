"""Inventory ledger: receipts, issues, reservations, adjustments, concurrency, valuation."""
import threading
from decimal import Decimal as D

import pytest
from tests.conftest import unique


def _material(apex_client, search="ISMB 300"):
    return apex_client.get(f"/api/v1/materials?search={search}").json()["items"][0]


def _warehouse(apex_client):
    return apex_client.get("/api/v1/inventory/warehouses").json()[0]


def receipt(apex_client, material_id, warehouse_id, lot, qty, cost="50000", quality="OK"):
    return apex_client.post("/api/v1/inventory/receipts", json={
        "material_id": material_id, "warehouse_id": warehouse_id, "lot_number": lot,
        "quantity": qty, "unit_cost": cost, "quality_status": quality})


class TestReceipts:
    def test_receipt_creates_lot_and_movement(self, apex_client):
        mat = _material(apex_client)
        wh = _warehouse(apex_client)
        lot = unique("LOT-T")
        resp = receipt(apex_client, mat["id"], wh["id"], lot, "25")
        assert resp.status_code == 201
        body = resp.json()
        assert body["lot_number"] == lot
        assert D(body["on_hand_qty"]) == D("25")
        mvs = apex_client.get(
            f"/api/v1/inventory/movements?material_id={mat['id']}&movement_type=RECEIPT").json()
        assert any(m["stock_lot_id"] == body["id"] for m in mvs["items"])

    def test_receipt_negative_rejected(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        assert receipt(apex_client, mat["id"], wh["id"], unique("LOT-T"), "-5").status_code == 422

    def test_receipt_idempotency(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot, key = unique("LOT-T"), unique("IDEM")
        r1 = apex_client.post("/api/v1/inventory/receipts",
                              headers={"Idempotency-Key": key}, json={
                                  "material_id": mat["id"], "warehouse_id": wh["id"],
                                  "lot_number": lot, "quantity": "10", "unit_cost": "51000"})
        r2 = apex_client.post("/api/v1/inventory/receipts",
                              headers={"Idempotency-Key": key}, json={
                                  "material_id": mat["id"], "warehouse_id": wh["id"],
                                  "lot_number": lot, "quantity": "10", "unit_cost": "51000"})
        assert r1.status_code == 201 and r2.status_code == 201
        lot_state = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]
        # replay must not double the quantity
        assert D(lot_state["on_hand_qty"]) == D("10")

    def test_quarantined_excluded_from_available(self, apex_client):
        mat, wh = _material(apex_client, "Chequered"), _warehouse(apex_client)
        before = apex_client.get(
            f"/api/v1/materials/availability?material_id={mat['id']}").json()[0]
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "12", quality="QUARANTINED")
        av = apex_client.get(
            f"/api/v1/materials/availability?material_id={mat['id']}").json()[0]
        # quarantined qty adds to quality_held, NOT to available
        assert D(av["available"]) == D(before["available"])
        assert D(av["quality_held"]) == D(before["quality_held"]) + D("12")


class TestIssuesAndNegativePrevention:
    def test_over_issue_rejected_409(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "8")
        lot_id = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]["id"]
        resp = apex_client.post("/api/v1/inventory/issues",
                                json={"lot_id": lot_id, "quantity": "9"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "INSUFFICIENT_STOCK"

    def test_concurrent_issues_never_oversell(self, apex_client):
        """Two racing issues against one 10 MT lot; total issued must never exceed 10."""
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "10")
        lot_id = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]["id"]
        results = []

        def attempt():
            from app.main import create_app
            from fastapi.testclient import TestClient
            c = TestClient(create_app())
            c.post("/api/v1/auth/login",
                   json={"email": "admin@apex.demo", "password": "SteelBid#Demo2026"})
            results.append(c.post("/api/v1/inventory/issues",
                                  json={"lot_id": lot_id, "quantity": "8"}).status_code)

        t1 = threading.Thread(target=attempt)
        t2 = threading.Thread(target=attempt)
        t1.start(); t2.start(); t1.join(); t2.join()
        assert sorted(results) == [201, 409], f"race won: {results}"
        lot_state = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]
        assert D(lot_state["on_hand_qty"]) == D("2")  # exactly one issue won

    def test_negative_on_hand_impossible_at_row_level(self, apex_client, db):
        """DB CHECK constraint is the backstop even if service logic were bypassed."""
        from sqlalchemy import update
        from sqlalchemy.exc import DBAPIError
        from app.models.inventory import StockLot
        lot = db.query(StockLot).filter(StockLot.on_hand_qty > 0).first()
        with pytest.raises(DBAPIError):
            db.execute(update(StockLot).where(StockLot.id == lot.id).values(on_hand_qty=-1))
            db.flush()
        db.rollback()


class TestReservations:
    def test_reserve_and_release(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "30")
        lot_id = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]["id"]
        res = apex_client.post("/api/v1/inventory/reservations",
                               json={"lot_id": lot_id, "quantity": "10",
                                     "context": {"test": True}})
        assert res.status_code == 201
        state = apex_client.get(f"/api/v1/inventory/stock-lots/{lot_id}").json()
        assert D(state["reserved_qty"]) == D("10")
        assert D(state["available_qty"]) == D("20")
        rel = apex_client.post(f"/api/v1/inventory/reservations/{res.json()['id']}/release")
        assert rel.status_code == 200
        state = apex_client.get(f"/api/v1/inventory/stock-lots/{lot_id}").json()
        assert D(state["reserved_qty"]) == D("0")

    def test_reserve_quarantined_rejected(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "5", quality="QUARANTINED")
        lot_id = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]["id"]
        resp = apex_client.post("/api/v1/inventory/reservations",
                                json={"lot_id": lot_id, "quantity": "1", "context": {}})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "LOT_NOT_ELIGIBLE"


class TestAdjustments:
    def test_adjustment_records_delta_and_reason(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "20")
        lot_id = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]["id"]
        resp = apex_client.post("/api/v1/inventory/adjustments",
                                json={"lot_id": lot_id, "new_on_hand": "17",
                                      "reason": "cycle count variance"})
        assert resp.status_code == 201
        mvs = apex_client.get(
            "/api/v1/inventory/movements?movement_type=ADJUSTMENT").json()["items"]
        mv = next(m for m in mvs if m["stock_lot_id"] == lot_id)
        assert D(mv["quantity"]) == D("-3")
        assert mv["reference"]["reason"] == "cycle count variance"

    def test_adjust_below_reserved_rejected(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "10")
        lot_id = apex_client.get(f"/api/v1/inventory/stock-lots?search={lot}").json()["items"][0]["id"]
        apex_client.post("/api/v1/inventory/reservations",
                         json={"lot_id": lot_id, "quantity": "6", "context": {}})
        resp = apex_client.post("/api/v1/inventory/adjustments",
                                json={"lot_id": lot_id, "new_on_hand": "5", "reason": "bad count"})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "ADJUSTMENT_BELOW_RESERVED"


class TestValuation:
    def test_valuation_sums_lots(self, apex_client):
        mat, wh = _material(apex_client), _warehouse(apex_client)
        lot = unique("LOT-T")
        receipt(apex_client, mat["id"], wh["id"], lot, "10", cost="50000")
        val = apex_client.get("/api/v1/inventory/valuation").json()
        assert D(val["total_value"]) > D("500000")
        assert val["currency"] == "INR"
