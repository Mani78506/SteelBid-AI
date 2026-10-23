"""Disabled-by-default activation gate for market-data providers."""
from dataclasses import dataclass
from enum import StrEnum

class ProviderType(StrEnum):
    OFFICIAL_DOCUMENT="OFFICIAL_DOCUMENT"; PUBLIC_DATA_API="PUBLIC_DATA_API"; LICENSED_COMMERCIAL_API="LICENSED_COMMERCIAL_API"; FIXTURE_TEST="FIXTURE_TEST"


class ProviderClass(StrEnum):
    """Commercial/reuse model. It is independent from transport/provider type."""
    FREE_PUBLIC="FREE_PUBLIC"
    PAID_LICENSED="PAID_LICENSED"
    DEMO="DEMO"
    FIXTURE_TEST="FIXTURE_TEST"

@dataclass(frozen=True)
class ProviderConfig:
    provider_id:str; name:str; provider_type:ProviderType; endpoint:str; enabled:bool=False
    credential_reference:str|None=None; requires_auth:bool=False; access_authorized:bool=False; reuse_authorized:bool=False
    refresh_interval_minutes:int=1440; adapter_version:str="v1"
    provider_class:ProviderClass=ProviderClass.PAID_LICENSED
    documentation_url:str|None=None

def activation_error(config:ProviderConfig, *, credential_available:bool=False, publish_genuine:bool=False)->str|None:
    if not config.enabled: return "provider is disabled"
    if config.provider_type is ProviderType.FIXTURE_TEST and publish_genuine: return "fixture providers cannot publish genuine observations"
    if config.provider_class in {ProviderClass.DEMO, ProviderClass.FIXTURE_TEST} and publish_genuine: return "demo and fixture providers cannot publish genuine observations"
    if not config.access_authorized: return "access authorization is required"
    if not config.reuse_authorized: return "reuse/display authorization is required"
    if config.requires_auth and (not config.credential_reference or not credential_available): return "configured credentials are required"
    return None

def require_active(config:ProviderConfig, **kwargs)->None:
    if error:=activation_error(config, **kwargs): raise PermissionError(error)

DEFAULT_PROVIDERS=(
 # Registration does not authorize activation. Every provider remains disabled
 # until a tenant-specific persisted configuration supplies written permissions.
 ProviderConfig("WORLD_BANK_PINK_SHEET","World Bank Commodity Markets Pink Sheet",ProviderType.OFFICIAL_DOCUMENT,
                "https://thedocs.worldbank.org/en/doc/18675f1d1639c7a34d463f59263ba0a2-0050012025/",
                provider_class=ProviderClass.FREE_PUBLIC,
                documentation_url="https://datacatalog.worldbank.org/search/dataset/0038238/commodity-prices-history-and-projections"),
 ProviderConfig("MINISTRY_OF_STEEL","Ministry of Steel",ProviderType.OFFICIAL_DOCUMENT,"https://steel.gov.in/monthly-summary",
                documentation_url="https://steel.gov.in/website-policies"),
 ProviderConfig("JPC","Joint Plant Committee",ProviderType.LICENSED_COMMERCIAL_API,"https://jpcsteel.co.in/",requires_auth=True,
                provider_class=ProviderClass.PAID_LICENSED,documentation_url="https://jpcsteel.co.in/subscription/"),
 ProviderConfig("FASTMARKETS","Fastmarkets",ProviderType.LICENSED_COMMERCIAL_API,"",requires_auth=True,
                provider_class=ProviderClass.PAID_LICENSED,documentation_url="https://help.fastmarkets.com/apis_sub/introduction"),
 ProviderConfig("ARGUS","Argus Media",ProviderType.LICENSED_COMMERCIAL_API,"",requires_auth=True,
                provider_class=ProviderClass.PAID_LICENSED,documentation_url="https://www.argusmedia.com/ja/solutions/products/argus-global-steel"),
 ProviderConfig("EXTERNAL_API_PROVIDER","Commercial provider",ProviderType.LICENSED_COMMERCIAL_API,"",requires_auth=True),
)


def registered_provider(provider_id: str) -> ProviderConfig | None:
    return next((provider for provider in DEFAULT_PROVIDERS if provider.provider_id == provider_id), None)
