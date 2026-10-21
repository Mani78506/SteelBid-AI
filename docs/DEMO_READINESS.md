# SteelBid AI — Customer demo readiness

Audit date: 21 October 2026. Scope: isolated `[DEMO] SteelBid Market Showcase` only. No production data was changed or deployed.

## Final polish update — 21 October 2026

The four customer-facing gaps identified in this report are now resolved and verified.

- **Supplier comparison:** Tender detail opens an in-application comparison for each persisted requirement snapshot. It shows supplier, quoted price, freight/tax where recorded, landed unit price, derived total landed cost, quantity, validity, compatibility, and the persisted selected supplier. Missing fields remain blank rather than being invented.
- **Tender costing:** Tender detail now shows the linked persisted draft estimate, its recorded material/fabrication/freight/overhead components, total estimated cost, and an explicit draft-only disclosure. It does not present a quotation as approved.
- **Notifications:** The header bell now displays tenant-scoped persisted notifications, unread count, timestamp, read state, empty/loading states, and links to the related record.
- **Safe alert demo:** Only `[DEMO] SteelBid Market Showcase` users with market-write permission see **Run simulated alert demo**. It creates one deterministic synthetic observation through the ingestion pipeline per user, evaluates that user's threshold alert, persists the linked notification, and is idempotent on repeat. It cannot be called for customer organizations and never creates a genuine market observation.

Final verification results:

- Focused backend demo/alert/ingestion tests: **9 passed**.
- TypeScript validation: **passed**.
- Production build in an unrestricted local Windows shell: **passed** (2,653 modules transformed).
- Customer browser regression: **5 passed**, including the new supplier, costing, notification, and alert-trigger flow.

New screenshots:

- [Supplier comparison](../frontend/e2e/demo-supplier-comparison.png)
- [Tender draft costing](../frontend/e2e/demo-tender-costing.png)
- [Safe alert trigger](../frontend/e2e/demo-alert-trigger.png)
- [Notification drawer](../frontend/e2e/demo-notification-drawer.png)

## Single-company historical market and multi-tender update

- The isolated Showcase fixture now contains **9,441** persisted synthetic observations spanning **12 steel material series**, **5 Indian regions**, and the 2026 one-year demonstration window. West India has daily chart detail; other regions have weekly comparable observations. The deterministic pricing pattern includes recoveries, temporary highs/lows, corrections and stable periods.
- The same organization now has **7** fictional persisted tenders: the original 200 MT tender plus six dated Q1–Q4 portfolio tenders. No other organization was seeded or changed by this update.
- Each portfolio tender has a tenant-scoped draft estimate with a persisted historical benchmark in its existing estimate context. The benchmark is the latest exact material/grade/region/currency/unit/price-basis observation on or before its recorded costing-reference date. The Tender detail displays this as a reference market price, not a supplier purchase price.
- There are **5** Showcase notifications, including deterministic new-tender, deadline, procurement-shortage and market-movement demo events. They are seeded demo events, not portal-discovery claims.
- The Showcase-only seed was run twice against the local development database; observation and tender counts remained **9,441 / 7**.

Additional screenshots:

- [One-year market history](../frontend/e2e/demo-quarterly-market-history.png)
- [Tender historical benchmark](../frontend/e2e/demo-tender-benchmark.png)

## Ready for the customer demo

- Organization switching is tenant-safe. Switching to the Showcase reloads its own persisted dashboard values: 75 MT eligible inventory and 125 MT procurement shortage.
- Command Center loads, includes the shared Market Intelligence panel, and renders persisted market charts.
- Market Intelligence supports persisted analytics: 7D/30D/90D/1Y history, regional comparison, movers, source/freshness context, alert creation/listing/disable controls, and alert-history links.
- One clear disclosure, `Market Showcase — Simulated Market Data`, identifies the demo price history. No Live/Verified claim is presented for that history.
- `TND-DEMO-200MT` opens through the actual Tender UI. Its persisted requirements render as Beams 100 MT / 40 MT available / 60 MT shortage, Plates 60 / 25 / 35, and Channels 40 / 10 / 30 — 200 MT required, 75 MT eligible, 125 MT shortage.
- Tender detail displays persisted supplier allocations and selected landed costs.
- The local production build passes in an unrestricted Windows shell.

## Historical audit findings — resolved by the final polish update above

- The Tender detail does **not** currently display its persisted draft cost estimate. Do not claim that approved tender costing/quotation is visible from this screen.
- `View compatible supplier offers` in Tender detail opens the raw API response in a new browser tab, rather than a polished supplier-comparison screen. Supplier selections/landed costs are visible in Tender detail, but the interactive comparison view is incomplete.
- The header notification bell is decorative: it has no notification drawer. Market alert history is available inside Market Intelligence; seeded demo notifications are visible through existing dashboard/briefing content, not a notification panel.
- A browser user can create and save a price alert, but there is no UI action to submit a new observation through the Stage B ingestion path. Alert-triggering is covered by backend tests; do not demonstrate a claimed live alert trigger through the UI.
- No licensed external market-price provider is connected. All Showcase price data is simulated/persisted demo data.

## Reproduce the verified flow

1. Start the existing backend and frontend, then open `http://127.0.0.1:5173`.
2. Sign in using the existing demo login procedure.
3. Use the organization switcher and choose `[DEMO] SteelBid Market Showcase`.
4. On Command Center, verify `75 MT` eligible inventory and `125 MT` procurement shortage.
5. Open **Market Prices**. Confirm the simulated-data disclosure; choose 7D, 30D, 90D, or 1Y; then use **Regional View**, **Movers**, and **Alerts**.
6. Open **Tenders & BOQ**, select `TND-DEMO-200MT`, and inspect the Material requirements vs stock and Supplier allocations sections.

## Test results

- Backend focused market suite: **23 passed**.
- TypeScript validation: **passed**.
- Production build in normal Windows shell: **passed** (`vite build`, 2653 modules transformed).
- Playwright current customer-flow suite: **4 passed**:
  - enhanced Command Center API rendering
  - organization-switch isolation
  - Market Intelligence controls
  - Showcase Command Center → Market → Tender workflow

The prior build error is reproducible only inside the restricted sandbox: esbuild cannot read parent directories and therefore cannot resolve the local Vite config. The same command succeeds outside that sandbox; no security/configuration workaround was applied.

## Screenshots

- [Command Center](../frontend/e2e/demo-command-center.png)
- [Market Intelligence](../frontend/e2e/demo-market-intelligence.png)
- [Tender detail](../frontend/e2e/demo-tender-detail.png)
- [Market alert panel](../frontend/e2e/market-intelligence-alerts.png)

## Five-minute walkthrough

**0:00–0:30 — Command Center.** Select the Showcase organization. Explain that all displayed operational values are persisted in the isolated demo organization. Point out the 200 MT tender, 75 MT eligible stock and 125 MT procurement gap.

**0:30–1:45 — Market Intelligence.** Open Market Prices. State clearly that the Showcase is simulated market data, not a live commercial feed. Select HRC, change the history range from 7D through 1Y, then show region comparison, movers, source, observed date and freshness.

**1:45–2:30 — Alert workflow.** Create an above/below threshold alert from the selected comparable series and show it in the Alerts tab. Explain that alerts are persisted and evaluated on authorized ingestion; no real provider is connected in this demo.

**2:30–3:45 — Tender readiness.** Open `TND-DEMO-200MT`. Walk through Beams (100/40/60), Plates (60/25/35), and Channels (40/10/30). Relate the totals to the Command Center procurement shortage.

**3:45–4:30 — Procurement.** Show selected supplier allocations and landed costs in the Tender detail. Be transparent that the dedicated compatible-offer view is currently an API handoff, not a polished UI.

**4:30–5:00 — Close.** Return to the Command Center. Reinforce tenant isolation, persisted audit-ready data, simulated price disclosure, and the future provider integration boundary.
