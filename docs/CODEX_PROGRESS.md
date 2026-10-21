# Codex progress

## Market import database foundation

- Added persisted MarketSource, MarketImportBatch and MarketImportStagedRow models.
- Added reversible Alembic revision `market_reviewed_import`; no observations are published or altered by it.

## Customer demonstration fixture

- Added an idempotent, isolated `[DEMO] SteelBid Market Showcase` seed organization with persisted synthetic market history, a 200 MT tender (75 MT eligible inventory and 125 MT sourced shortage), supplier offers/selections, draft tender costing, and seeded demo notifications.
- All market-price fixture data is stored as synthetic observations; no external provider or real quotation is implied.
- Fixed Command Center enhanced-dashboard handling for persisted tender timestamps and tender-id shortage iteration; showcase data now returns 6 market series, 75 MT eligible inventory, and 125 MT tender shortage through the backend computation.
- Verified the foundation models with the repository backend virtual environment: 2 focused tests pass.
  Disposable migration-cycle verification remains blocked because the configured PostgreSQL role
  lacks CREATE DATABASE; no development or production database was migrated as a substitute.
- A dedicated empty local PostgreSQL database was subsequently verified and used only for the
  market migration cycle: upgrade to head, schema/constraint inspection, downgrade one revision,
  and upgrade to head again all completed successfully.
- Added `POST /v1/market/imports/preview`: an authenticated, idempotent CSV preview that accepts
  an approved tenant-visible MarketSource, persists a MarketImportBatch plus staged rows, records
  raw/normalized values and row validation errors, and never publishes PriceObservation records.

## Stage 3 — in progress

- Replaced the stale port-8001 backend listener with the current repository backend.
- Verified authenticated enhanced dashboard rendering with a Playwright test that waits for a 200 response from `/api/v1/dashboard/enhanced?days=30`; it fails if the fallback is used.
- Extended the market trend API and workspace so a selected price basis is retained in the historical series, with 7-, 30-, and 90-day controls.
- Pipeline valuation now uses active persisted tender estimates only, reports missing estimates explicitly, and aligns the dashboard with the persisted `WON` tender state.
- Added route-level lazy loading for authenticated pages to split the initial application bundle.
- Added migration `tender_commercial_links`: nullable, indexed tender foreign keys on cost estimates and customer quotations. Finance estimate creation validates tender tenancy; no existing association is inferred.
- Added migration `tender_costing_foundation` and tender endpoints for immutable, versioned snapshots of confirmed, mapped BOQ requirements. Snapshotting refuses unapproved/incomplete BOQ lines and records an audit event.
- Added compatible-offer comparison and persisted tender supplier allocations with server-side expiry/compatibility/quantity validation, row locking of the requirement snapshot, over-allocation and duplicate-allocation rejection, and audit events.
- Added active-selection listing, history, and cancellation APIs. Cancellation is blocked once an approved tender cost estimate exists; the tender workspace displays snapshots, allocated quantities, costs, and compatible-offer links.
- Fixed Command Center market data omission: the enhanced API previously constrained global observations with an impossible tenant predicate while freshness correctly included them. Market trends now derive comparable tenant-or-global series and include region, price basis, source, and freshness.
- Reworked the Command Center into a responsive enterprise operations view: executive KPIs, a lazy-loaded real-observation market chart with 7/30/90-day controls, persisted tender pipeline bars, inventory state bars, procurement/readiness, commercial completeness, approvals, and source-backed AI actions. The chart intentionally reports insufficient history instead of fabricating data.
- Refined the visual hierarchy for sparse and empty states: compact real-price cards replace chart-sized sparse-history placeholders; zero-tender organizations get create/import onboarding instead of empty pipeline bars; and inventory now includes persisted material-level ATP comparison bars while explicitly retaining overlapping-state semantics.
- Continued the reference-aligned Command Center build with a data-driven tender pipeline donut, persisted status legend, and upcoming-deadline list. It renders only from actual tender-status counts and retains the working no-tender onboarding state.
- Fixed organization switching in the Command Center: tenant-scoped React Query entries are cleared, the still-observed session identity is force-refetched, and dashboard/briefing/market-panel cache keys include the active organization id. This prevents one company’s cached cards from appearing under another company.
- Added Playwright coverage for an organization switch to `[DEMO] SteelBid Market Showcase`; the verified response and rendered dashboard show its persisted 75 MT eligible inventory and 125 MT shortage. TypeScript validation and the existing enhanced-dashboard Playwright test also pass.
- Expanded the isolated Market Showcase fixture with deterministic, persisted 366-day histories for HRC, CRC, TMT, billet, scrap, plate, structural steel, channel, angle, wire rod and galvanized steel across the supported Indian regions. Fixture identities now include form, grade, region and date, preventing cross-series UUID collisions; two consecutive seed runs completed successfully.
- Added the 1Y control and extended product choices in the Market workspace. The currently requested UI removes the visible synthetic-demo tag while retaining neutral source and observation-date context; no live/verified claim is shown in the Command Center panel.

## Market Intelligence backend — Stage A complete

- Audited the existing market implementation: `PriceObservation`, `PriceSource`, reviewed import models, CSV preview, `/market/trends`, freshness warnings, enhanced dashboard queries, Celery configuration, and frontend consumers already existed. No provider adapter or persisted price-alert rule exists yet, so neither was duplicated in Stage A.
- Added authenticated analytics APIs under the existing market router:
  - `GET /api/v1/market/intelligence/overview`
  - `GET /api/v1/market/intelligence/latest`
  - `GET /api/v1/market/intelligence/history`
  - `GET /api/v1/market/intelligence/regions`
  - `GET /api/v1/market/intelligence/movers`
  - `GET /api/v1/market/intelligence/sources`
  - `GET /api/v1/market/intelligence/freshness`
- Movement, min/max, and averages use `Decimal` from persisted observations only. Every comparison is locked to material, grade, region, price basis, currency, unit, and one source; a missing or ambiguous comparison returns an explicit `insufficient_data` response and never interpolates points.
- Stage A analytics deliberately exposes only organization-owned observations. Existing global-observation visibility does not yet have explicit source-entitlement records, so Stage B must add those rules before analytics can safely redistribute a global/provider source.
- Added `tests/test_market_analytics.py`; focused market/dashboard suite result: **16 passed**. Pytest emitted only existing cache-permission and third-party deprecation warnings.

## Market Intelligence backend — Stage B complete

- Added `MarketDataProvider` contracts and safe adapters in `app/services/market_providers.py`: `DEMO_PROVIDER` reads existing persisted fixture data, `CSV_PROVIDER` explicitly remains preview/review-only, and `EXTERNAL_API_PROVIDER` is disabled until licensed provider documentation and credentials are supplied. No URL, credentials, response schema, or live provider was invented.
- Added canonical `ProviderObservation` normalization and the atomic `ingest_observations` service in `app/services/market_ingestion.py`. It validates required identity, date, region, Decimal price, allowed currency/unit/basis, source ownership and synthetic provenance; it deduplicates using the complete comparable observation identity and records inserted/duplicate/rejected counts.
- Added `MarketIngestionRun` and nullable `PriceObservation.external_observation_id`, with reversible migration `market_ingestion_foundation`. Run history has provider/source/organization, deterministic idempotency key, lifecycle timestamps, status, counts, and bounded diagnostic error summaries. It never stores credentials or raw secrets.
- Added a Celery `steelbid.ingest_market_observations` task with bounded exponential retry/backoff for transient connection errors. There is no periodic external polling configuration; concurrent/repeated calls return the same idempotent run through the database uniqueness constraint.
- Added `tests/test_market_ingestion.py` for normalization precision, duplicate/idempotent runs, partial rejection without losing valid rows, tenant/source/provenance isolation, and unconfigured provider behavior. Stage B focused result: **20 passed**; `alembic heads` reports `market_ingestion_foundation (head)`.

## Market Intelligence backend — Stage C complete

- Confirmed the configured local development database was behind Stage B at `tender_costing_foundation`, then applied only non-destructive forward revisions. It is now `market_price_alerts (head)`; no reset, downgrade, test database, or production database was used.
- Added tenant- and user-scoped `MarketPriceAlertRule` and deduplicated `MarketPriceAlertEvent` persistence, with migration `market_price_alerts`. Rules support exact material/grade/region/currency/unit/basis compatibility, optional owned source, ABOVE/BELOW Decimal price thresholds, optional Decimal movement percentage, and active state.
- Added authenticated API endpoints: `POST /api/v1/market/alerts`, `GET /api/v1/market/alerts`, `PATCH /api/v1/market/alerts/{id}`, `DELETE /api/v1/market/alerts/{id}`, and `GET /api/v1/market/alerts/history`.
- Integrated evaluation into the Stage B ingestion transaction after a new row is flushed. It ignores rejected/duplicate/stale observations, applies exact compatibility and source scoping, requires a threshold crossing to avoid repeated-above/below spam, stores a stable event identity, and creates a linked in-app `MARKET_ALERT` notification.
- Seeded one deterministic, tenant-isolated HRC alert rule for `[DEMO] SteelBid Market Showcase`; existing seeded demo notices remain clearly demo fixtures and are not presented as a live provider trigger.
- Added `tests/test_market_alerts.py` for above crossing/linked notification, repeated-above de-duplication, below/mismatch/stale non-triggering, API tenant isolation, plus Stage A/B coverage. Result: **23 passed** (existing cache-permission and third-party deprecation warnings only).

## Market Intelligence frontend — Stage D complete

- Audited the shared Command Center/Market panel and replaced legacy `/market/trends` usage plus decorative comparison controls with the real Stage A analytics API. The approved panel remains shared by Command Center and Market Prices, preventing divergent market experiences.
- Connected overview, history, regional comparison, movers, sources and freshness queries, plus Stage C alert create/list/disable/history APIs. The panel supports 7D, 30D, 90D and 1Y data, interactive Recharts tooltips, compatible regional data, backend-calculated movers, exact source context, explicit insufficient-data states, and linked triggered-notification navigation.
- Added a single Market Showcase disclosure for synthetic demo history; there are no per-card synthetic badges and no Live/Verified claims.
- Added Playwright browser coverage and screenshot `frontend/e2e/market-intelligence-alerts.png` for demo organization switching, disclosure, 1Y history, regional view and alerts. Browser result: **1 passed**. TypeScript result: **passed**.
- Production build was attempted and remains blocked before application compilation by the existing esbuild sandbox filesystem restriction: `Cannot read directory \"../../../..\": Access is denied` followed by inability to resolve the local Vite config. This is an environment restriction, not a TypeScript source error.

## Customer demo readiness audit

- Added and passed a current Showcase Playwright workflow with Command Center, Market Intelligence and persisted tender checks. Captured Command Center, Market Intelligence and tender-detail screenshots; full current browser suite result: **4 passed**.
- Confirmed the Vite build succeeds in a normal unrestricted Windows shell (`2653 modules transformed`); the former esbuild failure is limited to the restricted sandbox. No configuration/security change was made.
- Documented verified features, known demo limitations, screenshots and a five-minute walkthrough in `docs/DEMO_READINESS.md`.

## Final customer demo polish

- Replaced Tender's raw compatible-offer API handoff with a tenant-scoped supplier comparison modal. It renders persisted supplier/quote/freight/tax/compatibility data, derived landed totals, and the selected allocation without creating a new procurement flow.
- Added the persisted linked draft cost estimate to Tender detail, with material, fabrication, freight, overheads, total and an explicit draft-only disclaimer.
- Added the authenticated `/api/v1/notifications` list and `/api/v1/notifications/{id}/read` routes and connected the header bell to tenant-scoped persisted records, unread count, timestamp and deep-link navigation.
- Added the restricted `POST /api/v1/market/demo/trigger-alert` action. It is available only to `[DEMO] SteelBid Market Showcase` users with `market:write`, runs a deterministic synthetic HRC observation through the existing ingestion service, creates/uses that user's demo alert, and returns the same idempotent replay on repeat. Customer organizations receive not found.
- Added `backend/tests/test_demo_polish.py` and `frontend/e2e/demo-polish.spec.ts`. Focused backend result: **9 passed**. TypeScript: **passed**. Normal-shell production build: **passed** (2,653 modules). Browser regression result: **5 passed** and captured the supplier comparison, tender costing, alert trigger and notification drawer screenshots.

## Single-company historical market and multi-tender demo

- Extended only `[DEMO] SteelBid Market Showcase` with deterministic synthetic market history: twelve materials (including HRC, CRC, TMT, billet, scrap, plate, structural, beam, channel, angle, wire rod and galvanized) across five regions. West India is daily and other regions weekly; the pattern is deliberately non-monotonic.
- Added six fictional Q1–Q4 tender records while preserving the existing 200 MT tender. Every new tender has confirmed requirements, a draft estimate and exact historical benchmark metadata stored in the existing `CostEstimate.context`; no migration or market-engine change was required.
- Tender detail now presents the persisted benchmark with observation date and costing reference date, explicitly distinguishing the reference market price from confirmed supplier procurement pricing.
- Added `test_showcase_historical_portfolio.py`: isolated showcase coverage, non-monotonic history, multi-tender count, notification count, and no-future-observation benchmark selection. Combined historical/analytics backend result: **5 passed**. The targeted local Showcase seed was verified idempotent at **9,441 observations and 7 tenders**. TypeScript and the expanded browser workflow pass.

Remaining Stage 3 work: tender valuation, landed-cost comparison, tender profitability, workflow progress, and route-level code splitting.
