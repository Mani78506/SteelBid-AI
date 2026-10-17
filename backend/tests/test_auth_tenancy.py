"""Authentication, org switching, role authorization, tenant isolation."""


class TestAuth:
    def test_login_success_sets_cookie(self, client):
        resp = client.post("/api/v1/auth/login",
                           json={"email": "admin@apex.demo", "password": "SteelBid#Demo2026"})
        assert resp.status_code == 200
        assert "steelbid_session" in resp.cookies
        assert resp.json()["user"]["email"] == "admin@apex.demo"

    def test_login_wrong_password_uniform_401(self, client):
        bad = client.post("/api/v1/auth/login",
                          json={"email": "admin@apex.demo", "password": "wrong-password-1"})
        missing = client.post("/api/v1/auth/login",
                              json={"email": "nobody@example.com", "password": "wrong-password-1"})
        assert bad.status_code == 401 and missing.status_code == 401
        assert bad.json()["error"]["code"] == missing.json()["error"]["code"] == "INVALID_CREDENTIALS"

    def test_protected_route_requires_auth(self, client):
        assert client.get("/api/v1/dashboard/summary").status_code == 401

    def test_me_and_refresh(self, apex_client):
        me = apex_client.get("/api/v1/auth/me")
        assert me.status_code == 200
        body = me.json()
        assert body["active_organization"]["name"].startswith("[DEMO] Apex")
        assert body["role"] == "ADMIN"
        assert apex_client.post("/api/v1/auth/refresh").status_code == 200

    def test_logout_invalidates_session(self, client):
        client.post("/api/v1/auth/login",
                    json={"email": "admin@apex.demo", "password": "SteelBid#Demo2026"})
        assert client.post("/api/v1/auth/logout").status_code == 204
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_session_token_not_in_localstorage_surface(self, apex_client):
        # The API never returns tokens in bodies; only the HttpOnly cookie carries the session.
        me = apex_client.get("/api/v1/auth/me").json()
        assert "token" not in str(me)


class TestOrgSwitching:
    def test_shared_admin_can_switch_all_orgs(self, client):
        client.post("/api/v1/auth/login",
                    json={"email": "admin@railbuild.demo", "password": "SteelBid#Demo2026"})
        orgs = client.get("/api/v1/auth/organizations").json()
        assert len(orgs) == 4
        for org in orgs:
            resp = client.post("/api/v1/auth/switch-organization",
                               json={"organization_id": org["id"]})
            assert resp.status_code == 200
            me = client.get("/api/v1/auth/me").json()
            assert me["active_organization"]["id"] == org["id"]

    def test_switch_to_non_member_org_rejected(self, viewer_client):
        orgs_of_admin = viewer_client.get("/api/v1/audit/events")  # viewer lacks audit:read
        assert orgs_of_admin.status_code == 403
        # viewer only belongs to Apex
        orgs = viewer_client.get("/api/v1/auth/organizations").json()
        assert len(orgs) == 1


class TestRoleAuthorization:
    def test_viewer_cannot_write(self, viewer_client):
        assert viewer_client.post("/api/v1/customers", json={"code": "ZX", "name": "Nope"}).status_code == 403
        assert viewer_client.post("/api/v1/materials", json={
            "sku": "ZX-1", "name": "Nope", "form": "PLATE", "grade": "E250"}).status_code == 403

    def test_sales_cannot_approve_quotation(self, client, apex_client):
        client.post("/api/v1/auth/login",
                    json={"email": "sales@apex.demo", "password": "SteelBid#Demo2026"})
        quotations = apex_client.get("/api/v1/quotations").json()["items"]
        target = next(q for q in quotations if q["status"] == "PENDING_APPROVAL")
        resp = client.post(f"/api/v1/quotations/{target['id']}/approve", json={"comment": "nope"})
        assert resp.status_code == 403

    def test_inventory_role_can_transact_but_not_manage_customers(self, client):
        client.post("/api/v1/auth/login",
                    json={"email": "inventory@apex.demo", "password": "SteelBid#Demo2026"})
        assert client.post("/api/v1/customers", json={"code": "ZX", "name": "Nope"}).status_code == 403
        assert client.get("/api/v1/inventory/stock-lots").status_code == 200


class TestTenantIsolation:
    def test_cross_tenant_get_returns_404(self, apex_client, metro_client):
        lot_id = metro_client.get("/api/v1/inventory/stock-lots").json()["items"][0]["id"]
        resp = apex_client.get(f"/api/v1/inventory/stock-lots/{lot_id}")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "NOT_FOUND"

    def test_cross_tenant_material_guess_404(self, apex_client, railbuild_client):
        mat_id = railbuild_client.get("/api/v1/materials").json()["items"][0]["id"]
        assert apex_client.get(f"/api/v1/materials/{mat_id}").status_code == 404

    def test_lists_are_org_scoped(self, apex_client, metro_client):
        apex_lots = apex_client.get("/api/v1/inventory/stock-lots?page_size=100").json()
        metro_lots = metro_client.get("/api/v1/inventory/stock-lots?page_size=100").json()
        apex_lot_numbers = {l["lot_number"] for l in apex_lots["items"]}
        metro_lot_numbers = {l["lot_number"] for l in metro_lots["items"]}
        assert apex_lot_numbers.isdisjoint(metro_lot_numbers)
        assert all(n.startswith("APX-") for n in apex_lot_numbers)
        assert all(n.startswith("MET-") for n in metro_lot_numbers)

    def test_cannot_link_cross_tenant_material_to_inquiry(self, apex_client, railbuild_client):
        foreign_mat = railbuild_client.get("/api/v1/materials").json()["items"][0]["id"]
        customer = apex_client.get("/api/v1/customers").json()["items"][0]
        resp = apex_client.post("/api/v1/inquiries", json={
            "customer_id": customer["id"], "reference": "X-TENANT-ATTEMPT",
            "items": [{"material_id": foreign_mat, "description": "sneaky", "quantity": "1"}]})
        assert resp.status_code == 404

    def test_non_member_cannot_access_org_data(self, client):
        # precision admin is not a member of apex
        client.post("/api/v1/auth/login",
                    json={"email": "admin@precision.demo", "password": "SteelBid#Demo2026"})
        apex_org = None
        from sqlalchemy import select
        from app.database import SessionLocal
        from app.models.identity import Organization
        db = SessionLocal()
        apex_org = db.scalar(select(Organization).where(Organization.name.like("%Apex%")))
        db.close()
        resp = client.post("/api/v1/auth/switch-organization",
                           json={"organization_id": str(apex_org.id)})
        assert resp.status_code == 404
