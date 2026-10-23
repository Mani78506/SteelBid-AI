# Genuine Market Provider Onboarding Checklist

Complete every item before setting a real `MarketSourceProviderConfig.enabled` value to `true`.

## Commercial and legal approval

- [ ] Provider legal name, stable provider ID, and named business owner recorded.
- [ ] Official API/feed documentation and a support contact recorded.
- [ ] Written authorization for automated retrieval obtained.
- [ ] Contract explicitly permits server-side storage and the intended historical retention period.
- [ ] Contract explicitly permits display in SteelBid to the intended tenant users.
- [ ] SaaS redistribution/derivative-display rights confirmed; if absent, keep data owner-only or do not publish.
- [ ] Permitted instruments, regions, grade/specification mappings, and attribution text approved.

## Feed contract

- [ ] Authentication method, secret reference name, token rotation and expiry documented. Never store secret values in the database.
- [ ] Endpoint(s), content type, API version, rate limits, pagination and conditional-retrieval support documented.
- [ ] Product/material category, grade, dimensions, geographic region, currency, unit and price-basis mappings approved.
- [ ] Observation timestamp, publication timestamp, reporting period and source record/document ID fields identified.
- [ ] Correction/revision semantics and historical backfill policy documented.
- [ ] Provider frequency and configured `refresh_interval_seconds` approved.

## Technical activation gate

- [ ] `MarketSource` has the correct tenant owner, licence status, attribution and redistribution setting.
- [ ] `MarketSourceProviderConfig` has `access_authorized=true` and `reuse_authorized=true` only after the written approval is recorded.
- [ ] A `PriceSource` owned by the same tenant uses `source_type=PROVIDER` and the matching `provider_key`.
- [ ] Adapter validates every required comparable field and rejects missing, ambiguous or incompatible records.
- [ ] Each observation receives its provider external record ID and a validated `source_document_id` in the same transaction.
- [ ] Provider response fixtures/contract tests cover valid records, corrections, duplicates, rate limits and authentication failure.
- [ ] First production activation is reviewed against a non-production database and remains disabled until explicit deployment approval.
