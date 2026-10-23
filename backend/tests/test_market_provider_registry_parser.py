from app.services.market_provider_registry import (ProviderClass, ProviderConfig,
    ProviderType, activation_error, registered_provider)
from app.services.market_document_parser import parse_fixture_csv

VALID=b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,E250,West India,50000,INR,MT,EX_WORKS,2026-01-01\n"

def test_provider_activation_gate():
    external=ProviderConfig("x","X",ProviderType.OFFICIAL_DOCUMENT,"https://x",enabled=True)
    assert activation_error(external) == "access authorization is required"
    allowed=ProviderConfig("x","X",ProviderType.OFFICIAL_DOCUMENT,"https://x",enabled=True,access_authorized=True,reuse_authorized=True)
    assert activation_error(allowed) is None
    auth=ProviderConfig("x","X",ProviderType.PUBLIC_DATA_API,"https://x",enabled=True,access_authorized=True,reuse_authorized=True,requires_auth=True)
    assert activation_error(auth) == "configured credentials are required"
    fixture=ProviderConfig("f","Fixture",ProviderType.FIXTURE_TEST,"fixture://x",enabled=True,access_authorized=True,reuse_authorized=True)
    assert activation_error(fixture,publish_genuine=True) == "fixture providers cannot publish genuine observations"

def test_fixture_parser_validation_and_isolation():
    result=parse_fixture_csv(VALID,parser_version="test-v2")
    assert result.status == "VALID" and result.publishable is False and result.parser_version == "test-v2"
    assert len(result.checksum) == 64
    assert parse_fixture_csv(b"x\n1\n").status == "REJECTED"
    bad=b"material_form,grade,region,price_per_unit,currency,unit,price_basis,observed_on\nHRC,AMBIGUOUS,W,0,INR,TONNE,EX_WORKS,nope\n"
    assert parse_fixture_csv(bad).status == "QUARANTINED"
    assert parse_fixture_csv(VALID+VALID.split(b"\n",1)[1]).status == "QUARANTINED"


def test_free_and_paid_provider_registrations_remain_disabled():
    free = registered_provider("WORLD_BANK_PINK_SHEET")
    assert free and free.provider_class is ProviderClass.FREE_PUBLIC and free.enabled is False
    for provider_id in ("FASTMARKETS", "JPC", "ARGUS"):
        provider = registered_provider(provider_id)
        assert provider and provider.provider_class is ProviderClass.PAID_LICENSED
        assert provider.enabled is False and activation_error(provider) == "provider is disabled"
