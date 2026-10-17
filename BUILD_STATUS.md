# SteelBid AI 2.0 — Build Status

Last updated: 2026-10-17 (final verification pass)

## Legend
- ✅ Verified working (evidence noted)
- 🔨 In progress
- ⬜ Not started
- ⚠️ Blocked / limitation (documented)

## Repository inspection
- Workspace started **empty** (no existing code, no git history). Initialized fresh per Part B architecture. Nothing was deleted.
- Local environment: Windows, Python 3.12.10, Node 22.15, PostgreSQL 17.4 running locally (databases `steelbid` and `steelbid_test` created), **no Docker CLI available locally**, no Redis locally.
- `git init` performed at repo root; `.gitignore` excludes `.env`, `node_modules`, `dist`, test artifacts, debug scripts.

## Module status

| Area | Status | Evidence |
|---|---|---|
| Docs (architecture/data-model/api-contracts) | ✅ | `docs/architecture.md`, `docs/data-model.md`, `docs/api-contracts.md` |
| Backend scaffold (FastAPI, SQLAlchemy 2.0, Alembic) | ✅ | `uvicorn app.main:app` boots; `/api/health` → 200 |
| Database models + migrations | ✅ | `alembic upgrade head` → 60 tables in `steelbid` DB |
| Auth (session cookies, Argon2id) | ✅ | login/me/refresh/logout/switch-org verified via curl + Playwright |
| Tenant isolation enforcement | ✅ | Apex admin guessing a Metro lot ID → uniform 404 (verified) |
| Calculation services (Decimal) | ✅ | margin 12% exact on QTN-2026-0005; WAC, landed cost used in flows; `test_calc.py` unit tests pass |
| Command Center dashboard | ✅ | `/api/v1/dashboard/summary` returns DB-derived KPIs; renders in browser (Playwright) |
| CRM / Customer inquiries | ✅ | inquiry create/persist verified (INQ-DEMO-100MT); UI page live |
| Quotations / Sales orders / Reservations | ✅ | full chain QTN-2026-0005 → SO-2026-0003 + 40 MT reservation (idempotent replay verified) |
| Procurement (PR → comparison → PO → GRN) | ✅ | PR-2026-0002 created; landed-cost compare verified (Sahyadri 56,200 rank 1); GRN covered by tests |
| Inventory ledger | ✅ | receipt/issue/adjust/reserve verified; over-issue 409; quarantined reserve 409 |
| Fabrication (BOM, work orders, inspections) | ✅ | router + UI implemented; seeded BOM/WO; `test_modules.py` covers WO/BOM |
| Projects & Tenders (upload, extraction, BOQ) | ✅ | upload → extract → BOQ-item review flow; extraction evidence stored; tests pass |
| Market intelligence | ✅ | trends/scenarios return labeled synthetic data (verified via API + UI) |
| AI services (briefing, extraction, explanations) | ✅ | briefing + shortage/supplier/price explanations grounded in records |
| Logistics (dispatch) | ✅ | dispatch create/ship flow; covered in `test_modules.py` |
| Finance (invoices, receivables/payables) | ✅ | receivables/payables/valuation/invoices endpoints live; KPIs on dashboard |
| Frontend (React/Vite/TS/Tailwind) | ✅ | all 18 module pages wired to real API contracts; typecheck clean |
| Seed data (4 fictional companies) | ✅ | ran twice identical counts: 4 orgs / 11 users / 57 lots / 5 quotations / 30 price obs |
| pytest suite | ✅ | **68 passed** (`pytest` in `backend/`, warnings only) |
| Playwright e2e | ✅ | **5 passed** — login, live KPIs, materials, inquiry→quotation→sales order, org switch, logout |
| Docker / Railway deployment config | ✅ | **Deployed live on Railway** — see below |

## Verified runtime checks (2026-10-17)
- `GET /api/health` → `{"status":"ok","service":"steelbid-api","version":"2.0.0"}`; `/api/health/ready` → DB ok.
- Login `admin@apex.demo` → session cookie; `/auth/me` returns `{user, active_organization, role, memberships}`.
- Dashboard summary: inventory_valuation=11,408,700 INR; open SO=1,293,200 (2); purchase commitments=1,024,000 (1); overdue receivables=398,496 (1) — all from DB.
- Availability for ISMB-200: on_hand 55, available 40 (15 quarantined excluded) — matches Part M design.
- Supplier comparison: Sahyadri 56,200 rank 1, Deccan +100, Western +300 premium.
- Quotation QTN-2026-0005: 100 MT × 56,200 = 5,620,000 cost → selling 6,386,363.6364 at exactly 12.0000% margin; shortage snapshot 60.
- Reserve 40 MT: idempotent replay returned same reservation; availability dropped 40→0. Over-issue 25/20 → 409 INSUFFICIENT_STOCK. Quarantined reserve → 409 LOT_NOT_ELIGIBLE.
- Customer quotation export contains selling price only (`56200` cost string absent).
- Org switching: `admin@railbuild.demo` is ADMIN in all 4 orgs; browser-verified — switcher text and dashboard scope update.
- VIEWER role POST /customers → 403 FORBIDDEN.
- Cross-tenant stock lot ID guess → 404 NOT_FOUND (uniform).

## Frontend verification (2026-10-17)
- `npx tsc --noEmit` → clean.
- `npm run build` → `✓ built` (1,055 kB main bundle; gzip 299 kB — chunk-size warning only, non-blocking; consider route-level code splitting later).
- Vite dev server on `127.0.0.1:5173` proxies `/api` → `127.0.0.1:8001`.
- Playwright `frontend/e2e/smoke.spec.ts` — 5/5 passing:
  - login → Command Center renders live KPIs
  - materials navigation shows seeded catalog
  - inquiry → quotation → sales order chain persists
  - organization switching changes dashboard scope (railbuild admin, 4-org membership)
  - logout returns to login page

### Bugs found & fixed during e2e
- Command Center crash on `/dashboard/summary` response-shape mismatch → `types.ts`, `CommandCenter.tsx`, `Briefing.tsx` rewritten to real contract.
- `post()` helper defaulted to GET when `body` was undefined → logout sent GET → 405. Fixed `post` to always set method POST.
- `/auth/me` shape is nested (`user`/`active_organization`/`role`) — `Me` type and all call sites updated.
- Org objects carry `business_profiles` (not `profiles`) — fixed in `Org` type, `AppLayout`, `CommandCenter`.
- `qc.clear()` removed mounted queries so they never refetched after org switch → `switchOrg` now uses `removeQueries` + `invalidateQueries` so identity queries refetch and tenant data reloads.
- Added `aria-label="User menu"` / `aria-label="Organization switcher"` for stable a11y targeting.

## Railway deployment (LIVE — verified 2026-10-17)

Project: https://railway.com/project/98a7ecaa-a005-4eb9-b798-8acaa062069b (`steelbid-ai`)

| Service | Status | URL / notes |
|---|---|---|
| `web` | ● Online | **https://web-production-972cd.up.railway.app** — React UI + nginx `/api/*` proxy |
| `api` | ● Online | https://api-production-51c1.up.railway.app — `/api/health` ✓ `/api/health/ready` ✓ |
| `worker` | ● Online | Celery, concurrency=2, connected to `redis.railway.internal` |
| `Postgres` | ● Online | Postgres 18 + 500MB volume |
| `Redis` | ● Online | session-free cache + Celery broker |

Verified live:
- `GET web/api/health` → `{"status":"ok"}` through the nginx proxy
- `POST web/api/v1/auth/login` → 200 + secure session cookie
- `GET web/api/v1/dashboard/summary` → live seeded KPIs (Apex Steel Traders org)
- Migrations ran on api boot; demo seed ran once via `RUN_SEED=true` (guarded by `DEMO_MODE`)

Deploy issues found & fixed: repo-root build contexts (RAILWAY_DOCKERFILE_PATH per service), missing `email-validator` in requirements.txt, nginx Host-header loop to Railway edge, Celery prefork OOM (48 workers → capped at 2).

## Known limitations (rolling)
- Redis is not installed on this machine; Celery runs in eager/synchronous fallback locally. Redis is provisioned via docker-compose / Railway for deployment.
- Docker CLI is not available on this machine; local image builds unverified, but the same Dockerfiles built successfully on Railway's builders (deployed live).
- AI extraction uses the deterministic built-in provider unless an LLM API key is configured via environment variables.
- Main JS bundle ~1 MB (warning only); route-level code splitting is a follow-up.
