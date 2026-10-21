"""Tests for enhanced dashboard API (Stage 1)."""
import pytest


class TestEnhancedDashboard:
    def test_enhanced_endpoint_exists(self, apex_client):
        """Test that the enhanced endpoint is accessible."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        assert response.status_code == 200

    def test_enhanced_response_structure(self, apex_client):
        """Test that enhanced response contains all new fields."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        data = response.json()

        # Base fields should still exist
        assert "organization" in data
        assert "kpis" in data
        assert "priorities" in data

        # New market intelligence fields
        assert "market_trends" in data
        assert "market_comparisons" in data
        assert "scenario_summary" in data

        # New tender intelligence fields
        assert "new_tenders" in data
        assert "tender_pipeline" in data
        assert "tender_amendments" in data

        # New BOQ/BOM fields
        assert "boq_review_status" in data
        assert "bom_readiness" in data
        assert "tender_shortages" in data

        # New inventory breakdown
        assert "inventory_breakdown" in data
        assert "atp_by_material" in data

        # New tender costing fields
        assert "active_costing_quotes" in data
        assert "margin_exposure" in data
        assert "pricing_scenarios" in data

        # New procurement intelligence
        assert "open_rfqs" in data
        assert "pending_quotes" in data
        assert "delivery_risks" in data

        # New approvals queue
        assert "approval_queue" in data
        assert "price_alerts" in data

    def test_market_trends_structure(self, apex_client):
        """Test that market trends have required fields."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        data = response.json()
        trends = data["market_trends"]

        for trend in trends:
            assert "form" in trend
            assert "grade" in trend
            assert "latest_price" in trend
            assert "currency" in trend
            assert "unit" in trend
            assert "observed_on" in trend
            assert "is_synthetic" in trend
            # Synthetic flag must be boolean
            assert isinstance(trend["is_synthetic"], bool)
            assert trend["source"]
            assert "region" in trend and "price_basis" in trend and "freshness_days" in trend

    def test_global_observations_render_as_market_trends(self, metro_client):
        """Global demo/provider observations are valid tenant-visible market data."""
        trends = metro_client.get("/api/v1/dashboard/enhanced").json()["market_trends"]
        assert trends
        assert all(t["source"] for t in trends)

    def test_inventory_breakdown_structure(self, apex_client):
        """Test that inventory breakdown has all states."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        data = response.json()
        breakdown = data["inventory_breakdown"]

        assert "on_hand" in breakdown
        assert "available" in breakdown
        assert "reserved" in breakdown
        assert "quality_held" in breakdown
        assert "unit" in breakdown

    def test_tender_pipeline_structure(self, apex_client):
        """Test that tender pipeline has all status keys."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        data = response.json()
        pipeline = data["tender_pipeline"]

        # Match the persisted Tender state machine (BID_SUBMITTED -> WON/LOST).
        expected_statuses = ["DRAFT", "IN_REVIEW", "ESTIMATING", "BID_SUBMITTED", "WON", "LOST"]
        for status in expected_statuses:
            assert status in pipeline
            assert isinstance(pipeline[status], int)

    def test_price_alerts_structure(self, apex_client):
        """Test that price alerts have threshold information."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        data = response.json()
        alerts = data["price_alerts"]

        assert "stale_observations" in alerts
        assert "stale_threshold_days" in alerts
        assert isinstance(alerts["stale_observations"], int)
        assert isinstance(alerts["stale_threshold_days"], int)

    def test_cross_tenant_isolation(self, metro_client):
        """Test that enhanced dashboard respects tenant isolation."""
        response = metro_client.get("/api/v1/dashboard/enhanced")
        data = response.json()

        # Should return Metro's data, not Apex's
        assert data["organization"]["name"] == "[DEMO] Metro Steel Distributors Pvt Ltd"

        # Tender pipeline should be scoped to Metro
        pipeline = data["tender_pipeline"]
        # Verify we got numbers (not None or empty)
        assert isinstance(pipeline.get("DRAFT", 0), int)

    def test_enhanced_preserves_base_functionality(self, apex_client):
        """Test that enhanced endpoint still provides all base dashboard data."""
        response = apex_client.get("/api/v1/dashboard/enhanced")
        data = response.json()

        # Verify all base fields exist
        assert "recent_inquiries" in data
        assert "procurement_shortages" in data
        assert "price_observations" in data
        assert "upcoming_dispatches" in data
        assert "production_status" in data
        assert "tender_deadlines" in data
        assert "recent_activity" in data

        # Verify KPIs still exist
        assert "inventory_valuation" in data["kpis"]
        assert "open_sales_order_value" in data["kpis"]
