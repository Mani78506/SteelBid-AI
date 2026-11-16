import pytest

from app.services.tender_source_registry import TenderSourceRegistryError, validate_profile_values


def test_fixture_profile_must_use_fixture_method_and_stays_disabled():
    validate_profile_values(
        source_category="MANUAL_UPLOAD", permitted_ingestion_method="FIXTURE_TEST",
        data_classification="FIXTURE_TEST", enabled_for_tender_ingestion=False,
        authorization_evidence_reference=None,
    )
    with pytest.raises(TenderSourceRegistryError, match="FIXTURE_TEST ingestion method"):
        validate_profile_values(
            source_category="MANUAL_UPLOAD", permitted_ingestion_method="MANUAL_UPLOAD",
            data_classification="FIXTURE_TEST", enabled_for_tender_ingestion=False,
            authorization_evidence_reference=None,
        )
    with pytest.raises(TenderSourceRegistryError, match="cannot be enabled"):
        validate_profile_values(
            source_category="MANUAL_UPLOAD", permitted_ingestion_method="FIXTURE_TEST",
            data_classification="FIXTURE_TEST", enabled_for_tender_ingestion=True,
            authorization_evidence_reference=None,
        )


def test_authentic_profile_requires_evidence_and_known_policy_values():
    with pytest.raises(TenderSourceRegistryError, match="authorization evidence"):
        validate_profile_values(
            source_category="CPPP", permitted_ingestion_method="OFFICIAL_DOCUMENT",
            data_classification="AUTHENTIC", enabled_for_tender_ingestion=False,
            authorization_evidence_reference=None,
        )
    validate_profile_values(
        source_category="CPPP", permitted_ingestion_method="OFFICIAL_DOCUMENT",
        data_classification="AUTHENTIC", enabled_for_tender_ingestion=False,
        authorization_evidence_reference="internal-legal-record-123",
    )
    with pytest.raises(TenderSourceRegistryError, match="Unsupported tender source category"):
        validate_profile_values(
            source_category="UNREVIEWED_PORTAL", permitted_ingestion_method="OFFICIAL_DOCUMENT",
            data_classification="AUTHENTIC", enabled_for_tender_ingestion=False,
            authorization_evidence_reference="internal-legal-record-123",
        )
