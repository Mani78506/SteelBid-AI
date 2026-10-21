"""Test CSV import for price observations"""
import io
from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import select

from app.models.market import PriceObservation, PriceSource


def test_csv_import_success(apex_client, db):
    """Test successful CSV import with valid data"""
    csv_content = """material_form,grade,region,dimension_note,price_basis,price_per_unit,unit,currency,observed_on
HRC,E250,West India,2.0mm,EX_WORKS,56000,MT,INR,2026-10-15
CRC,E350,North India,1.5mm,DELIVERED,58500,MT,INR,2026-10-16
BILLET,Fe500,South India,,EX_WORKS,52000,MT,INR,2026-10-17"""
    csv_file = io.BytesIO(csv_content.encode('utf-8'))
    csv_file.name = 'test.csv'

    response = apex_client.post(
        "/api/v1/market/observations/import",
        files={"file": (csv_file.name, csv_file, "text/csv")}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["imported"] == 3
    assert data["errors"] == []

    # Verify records were created
    hrc_obs = db.scalar(
        select(PriceObservation).where(
            PriceObservation.material_form == "HRC",
            PriceObservation.grade == "E250",
            PriceObservation.price_basis == "EX_WORKS"
        )
    )
    assert hrc_obs is not None
    assert hrc_obs.price_per_unit == Decimal("56000")
    assert hrc_obs.is_synthetic is False  # Manual import is non-synthetic
    assert hrc_obs.dimension_note == "2.0mm"


def test_csv_import_invalid_file_type(apex_client):
    """Test that non-CSV files are rejected"""
    txt_file = io.BytesIO(b"not a csv")
    txt_file.name = 'test.txt'

    response = apex_client.post(
        "/api/v1/market/observations/import",
        files={"file": (txt_file.name, txt_file, "text/plain")}
    )

    assert response.status_code == 400
    assert "INVALID_FILE" in str(response.json())


def test_csv_import_validation_errors(apex_client, db):
    """Test that invalid rows are skipped and errors reported"""
    csv_content = """material_form,grade,region,dimension_note,price_basis,price_per_unit,unit,currency,observed_on
BEAM,E250,West India,,EX_WORKS,56000,MT,INR,2026-10-15
,E350,North India,,DELIVERED,58500,MT,INR,2026-10-16
BILLET,Fe500,South India,,EX_WORKS,0,MT,INR,2026-10-17"""  # empty form and price=0 should fail
    csv_file = io.BytesIO(csv_content.encode('utf-8'))
    csv_file.name = 'test.csv'

    response = apex_client.post(
        "/api/v1/market/observations/import",
        files={"file": (csv_file.name, csv_file, "text/csv")}
    )

    assert response.status_code == 201
    data = response.json()
    assert data["imported"] == 1  # Only first row valid
    assert len(data["errors"]) == 2  # Missing form + zero price


def test_csv_import_uses_manual_source(apex_client, db):
    """Test that imported observations use the organization's MANUAL source"""
    csv_content = """material_form,grade,region,dimension_note,price_basis,price_per_unit,unit,currency,observed_on
SCRAP,IS2062,East India,,EX_WORKS,42000,MT,INR,2026-10-18"""
    csv_file = io.BytesIO(csv_content.encode('utf-8'))
    csv_file.name = 'test.csv'

    response = apex_client.post(
        "/api/v1/market/observations/import",
        files={"file": (csv_file.name, csv_file, "text/csv")}
    )

    assert response.status_code == 201

    scrap_obs = db.scalar(
        select(PriceObservation).where(
            PriceObservation.material_form == "SCRAP"
        )
    )
    assert scrap_obs is not None

    # Check source is MANUAL
    source = db.get(PriceSource, scrap_obs.source_id)
    assert source is not None
    assert source.source_type == "MANUAL"
    assert source.is_synthetic is False
