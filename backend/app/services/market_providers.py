"""Provider contracts only.  No licensed provider is configured in this repository."""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable, Protocol


@dataclass(frozen=True)
class ProviderObservation:
    material_form: str
    grade: str
    region: str
    price_per_unit: Decimal | str
    currency: str
    unit: str
    price_basis: str
    observed_on: date | str
    dimension_note: str | None = None
    external_observation_id: str | None = None


class MarketDataProvider(Protocol):
    key: str
    def fetch_observations(self) -> Iterable[ProviderObservation]: ...
    def normalize_observations(self) -> Iterable[ProviderObservation]: ...
    def validate_observations(self) -> Iterable[ProviderObservation]: ...
    def identify_source(self) -> str: ...
    def report_ingestion_status(self) -> dict: ...


class DemoProvider:
    """Reads existing deterministic demo observations; it never creates external data."""
    key = "DEMO_PROVIDER"
    def fetch_observations(self): return ()
    normalize_observations = fetch_observations
    validate_observations = fetch_observations
    def identify_source(self): return "persisted-demo-fixture"
    def report_ingestion_status(self): return {"configured": True, "mode": "persisted-demo"}


class CsvProvider:
    """CSV rows remain in MarketImportStagedRow until an authorized publisher exists."""
    key = "CSV_PROVIDER"
    def fetch_observations(self): return ()
    normalize_observations = fetch_observations
    validate_observations = fetch_observations
    def identify_source(self): return "reviewed-csv-preview"
    def report_ingestion_status(self): return {"configured": True, "publishes": False, "reason": "review required"}


class ExternalApiProvider:
    """Future provider contract. Disabled until licensed documentation/configuration exists."""
    key = "EXTERNAL_API_PROVIDER"
    def __init__(self, *, configured: bool = False): self.configured = configured
    def fetch_observations(self):
        if not self.configured: raise RuntimeError("External market provider is not configured")
        raise RuntimeError("No licensed provider adapter is installed")
    normalize_observations = fetch_observations
    validate_observations = fetch_observations
    def identify_source(self): return "unconfigured-external-provider"
    def report_ingestion_status(self): return {"configured": False, "reason": "credentials and provider specification required"}
