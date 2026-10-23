# All-India Steel Price Intelligence & Forecasting: readiness audit

Date assessed: 2026-10-22  
Scope: authorised, traceable Indian steel prices and forecasts. This document does not treat manual or synthetic demo observations as market data.

## Executive decision

SteelBid is **not ready to claim all-India price coverage or publish forecasts**. The current platform has a sound provenance, provider-gating, tenant-isolation and scheduler foundation, but lacks both (1) authorised Indian steel price history and (2) canonical Indian geography/specification dimensions.

No forecast models should be trained or displayed for Indian steel series at this stage. Forecast availability for every real product/location combination is `LICENCE_BLOCKED` or `NO_SOURCE`.

## Existing platform inventory

| Capability | Current state | Assessment |
| --- | --- | --- |
| Material identity | `MaterialCatalog`, `OrganizationMaterial`, `MaterialSpec`; form, grade, standard, base unit and JSON specification | Supports tenant material master. Product taxonomy needs canonical market-product codes to compare independent sources safely. |
| Actual price model | `PriceObservation`: form, grade, region, dimension note, basis, price, unit, currency, observation date, external ID, source document | Strong provenance baseline; `region` is free text and cannot support reliable all-India geographic aggregation. |
| Provenance | `MarketSource`, `MarketSourceDocument`, extraction, refresh state and provider configuration | Ready for source-document checksum, publication date, extraction status and licence gating. |
| Provider control | Disabled-by-default registry; access/reuse authorisation flags; fixture isolation | Ready. Ministry/JPC remain disabled. |
| Global indicators | World Bank benchmark model is explicitly separate from Indian steel observations | Suitable optional input only after timestamp/alignment review; not an Indian price substitute. |
| Geography | Warehouse/storage locations and some business-address city fields; no canonical Indian market-location table | Insufficient for state/district/city/cluster price observations. |
| Forecasting | No forecast model/run/point/evaluation entities; no rolling-origin validation service | Not implemented, correctly unavailable. |

## Extensible product taxonomy

The future canonical taxonomy must retain `category`, `form`, `grade`, `standard`, `thickness_mm`, `diameter_mm`, dimensions, unit, manufacturer, price basis, GST treatment and freight treatment. It must not collapse the following distinct market products:

1. TMT / reinforcement bars
2. HR coils, sheets and plates
3. CR coils and sheets
4. MS and chequered plates
5. Structural beams, channels and angles
6. Wire rod, rounds and flats
7. Billets, blooms and slabs
8. ERW, seamless and galvanised pipes
9. RHS / SHS hollow sections
10. Galvanised and colour-coated products
11. Stainless steel products and grades
12. Alloy / special steel
13. Scrap and secondary steel
14. Sponge iron and pig iron
15. Iron ore and ferroalloys
16. Configurable other products

Current `material_form`, `grade`, `dimension_note` and `specification` can be mapped into that taxonomy later; no product reclassification should be inferred from text alone.

## Geography readiness

Required future hierarchy: `COUNTRY → STATE/UT → DISTRICT → CITY → INDUSTRIAL_CLUSTER/MARKET`, backed by stable official identifiers and display names.

| Coverage request | Current actual support | Status |
| --- | --- | --- |
| India national | No authorised Indian actual price series | `NO_SOURCE` |
| 28 states / 8 UTs | No canonical geography model or authorised state series | `NO_SOURCE` |
| Districts/cities/clusters | Region free text only; no validated coverage | `NO_SOURCE` |
| Mumbai TMT/HRC/CRC | Genuine Ministry publication exists, but SaaS reuse permission has not been verified | `LICENCE_BLOCKED` |
| JPC four metros / clusters | Price coverage described by JPC, report subscription required | `LICENCE_BLOCKED` |

Never infer a state, city or district price from a national or Mumbai observation.

## Source and data coverage matrix

| Source | Product/location evidence | Frequency | Training / display rights | Integration status |
| --- | --- | --- | --- | --- |
| Ministry of Steel Monthly Economic Reports | TMT 10 mm, HRC 2.50 mm, CRC 0.63 mm; Mumbai retail; INR/tonne; current reports state inclusive GST | Monthly | Copyright policy requires prior permission for reproduction; commercial SaaS/display/training rights not verified | `LICENCE_BLOCKED` |
| JPC Retail Market Price–Fortnightly | Retail market trends for four metros and select clusters | Fortnightly | Subscription report; storage, model-training and tenant redistribution rights need licence | `LICENCE_BLOCKED` |
| data.gov.in | No verified TMT/HRC/CRC price dataset/API | Varies | No eligible price dataset found | `NO_SOURCE` |
| World Bank Pink Sheet | Global commodity input benchmarks only | Monthly | Separate CC BY 4.0 benchmark handling | Not Indian steel price coverage |
| Customer/supplier transaction data | Not assessed as an authorised market-data feed | Transactional | Requires explicit ownership/consent and anonymisation policy | `NOT_ONBOARDED` |

See [Indian steel price source audit](indian-steel-price-source-audit.md) for source URLs and licence evidence.

## Forecast availability

| Product × location series | Actual authorised history | Quality / validation | Status |
| --- | --- | --- | --- |
| All Indian TMT/HRC/CRC series | None | No backtest possible | `LICENCE_BLOCKED` |
| Other Indian steel products | None | No backtest possible | `NO_SOURCE` |
| Manual tenant observations | Not an authorised market feed | May support tenant-internal analysis only after policy approval; not a market forecast | `NOT_ELIGIBLE` |
| Synthetic/demo observations | Explicitly synthetic | Never eligible | `NOT_ELIGIBLE` |
| World Bank benchmarks | Global, not steel retail prices | Potential explanatory indicator only | `NOT_A_PRICE_SERIES` |

No MAE, RMSE, sMAPE, prediction interval coverage, or model ranking exists because no valid Indian target series is eligible for training.

## Minimum safe implementation sequence

1. Obtain Ministry written permission or a JPC licence covering retrieval, storage, customer display, redistribution and model training.
2. Add an additive canonical `IndianMarketLocation` and `SteelProduct` taxonomy migration **only after approval**.
3. Introduce read-only coverage APIs for authorised source/product/location combinations.
4. Ingest documented actual observations with complete provenance; do not migrate demo/manual history into genuine datasets.
5. Establish minimum series-quality thresholds, rolling-origin backtesting and baseline comparison.
6. Add `ForecastModel`, `ForecastRun`, `ForecastPoint` and `ForecastEvaluation` as separate models from actual observations.
7. Enable a forecast only when a product/location/basis/specification series passes validation; otherwise show the factual reason.

## Guardrails retained

- Command Center remains out of scope.
- No nationwide, regional or city prices are generated from another location.
- No forecast is labelled as an observation.
- World Bank benchmarks remain separate from Indian steel prices.
- Paid providers remain disabled.
- No production/default-database migration has been applied for this proposal.
