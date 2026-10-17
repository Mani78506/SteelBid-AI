# SteelBid AI — Steel Business Operating System

A multi-tenant B2B SaaS platform for **steel traders, distributors, fabricators, and railway/infrastructure contractors**. It manages the daily operations of a steel business end-to-end — from customer inquiry through quotation, sales order, procurement, inventory, fabrication, tenders, logistics, and finance — on one shared, PostgreSQL-backed foundation.

**Live demo (Railway):** https://web-production-972cd.up.railway.app
**API:** https://api-production-51c1.up.railway.app (`/docs` for Swagger)

> All demo data is fictional and clearly labeled `[DEMO]`.

---

## Highlights

- **Steel Business Command Center** homepage — live KPIs (inventory valuation, open orders, purchase commitments, margins, overdue receivables, at-risk orders, pending approvals), priorities, shortages, price observations, dispatches, production status, tender deadlines, AI daily briefing, and audit activity — all computed from tenant-scoped DB records.
- **Connected workflows**, not disconnected screens:
  - Customer inquiry → stock availability → supplier comparison → quotation → approval → sales order → reservation → shortage → purchase request → PO → goods receipt
  - Sales order → BOM → material allocation → work order → operations → QC → finished goods
  - Tender upload → AI/structured extraction → BOQ review → cost estimate
- **Multi-tenant** — strict organization isolation on every query, org switching, role-based permissions (ADMIN / SALES / PROCUREMENT / INVENTORY / FABRICATION / FINANCE / ESTIMATOR / VIEWER), session-cookie auth (Argon2id, no localStorage tokens).
- **Decimal-exact money & quantity math** — margin, landed cost, weighted-average cost, shortages. No floats for finance.
- **Concurrency-safe inventory ledger** — transactional movements, no negative stock, quarantined lots never count as available.
- **AI with guardrails** — extraction produces *reviewable evidence* (page, raw vs normalized value, confidence, warnings); deterministic Python services own all arithmetic; approvals stay human.
- **Market intelligence** — labeled synthetic price observations, trends, scenarios, freshness warnings (pluggable provider for real feeds).

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, shadcn-style components, Lucide, Framer Motion, TanStack Query, React Router, Recharts |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Data | PostgreSQL 17+, Redis 7, Celery (document extraction / AI jobs) |
| Docs processing | PyMuPDF, pdfplumber, openpyxl, pandas (OCR fallback) |
| Tests | pytest (68 tests), Playwright (5 e2e), `tsc --noEmit` |
| Deploy | Docker, docker-compose, Railway |

## Repository Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          # 16 FastAPI router groups
│   │   ├── models/       # SQLAlchemy 2.0 models (60 tables)
│   │   ├── schemas/      # Pydantic v2 DTOs
│   │   ├── services/     # domain services (inventory, quotations, audit…)
│   │   ├── calc/         # pure Decimal calculation services
│   │   ├── ai/           # briefing, extraction, providers, copilot
│   │   ├── seed/         # deterministic, idempotent demo seed
│   │   └── worker.py     # Celery app
│   ├── alembic/          # migrations
│   └── tests/            # pytest suite
├── frontend/
│   ├── src/pages/        # 18 module pages + Command Center + Login
│   ├── src/components/   # AppLayout, DataTable, UI primitives, Toast
│   ├── src/lib/          # typed API client, auth ctx, types, formatting
│   └── e2e/              # Playwright smoke suite
├── docs/                 # architecture, data-model, api-contracts, deployment
├── docker-compose.yml
├── railway.toml
└── BUILD_STATUS.md       # evidence-backed build/verification log
```

## Demo Accounts

| Login | Scope |
|---|---|
| `admin@railbuild.demo` | ADMIN across **all 4** demo orgs (use this to demo org switching) |
| `admin@apex.demo` | ADMIN — Apex Steel Traders (trader+distributor) |
| `admin@metro.demo` | ADMIN — Metro Steel Distributors |
| `admin@precision.demo` | ADMIN — PrecisionSteel Fabricators |
| `viewer@apex.demo` | VIEWER (read-only role demo) |

Password: `SteelBid#Demo2026` (the `DEMO_ADMIN_PASSWORD` env var).

## Quick Start (local)

Prerequisites: Python 3.12+, Node 22+, PostgreSQL 17. Redis optional (Celery falls back to eager mode).

```bash
# backend
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # Windows
cp .env.example .env          # set DATABASE_URL + DEMO_ADMIN_PASSWORD
alembic upgrade head
python -m app.seed.run        # idempotent demo data (requires DEMO_MODE=true)
uvicorn app.main:app --port 8001

# frontend (new terminal)
cd frontend
npm install
npx vite --port 5173          # proxies /api → 127.0.0.1:8001
```

Or with Docker (context is the repo root for both services):

```bash
docker compose up --build     # web :8080 · api :8000 · postgres :5433 · redis :6380
```

## The Primary Demo (100 MT inquiry)

1. Command Center → notice shortage priorities.
2. **Inquiries** → new inquiry: 100 MT structural steel.
3. Availability check → 40 MT eligible (15 MT quarantined excluded).
4. **Supplier comparison** → 3 offers ranked by landed cost.
5. **Quotation** → cost ₹56,200/MT × 100 = ₹5,620,000 → 12% target margin → ₹6,386,363.64 sell.
6. Submit → approve → **convert to sales order** (idempotent).
7. Reserve 40 MT → **purchase request auto-created for the 60 MT shortage**.
8. Procurement → PO → approve → **goods receipt** → availability updates everywhere.

Fabricator demo: BOM → allocation → work order → production status.
Contractor demo: tender upload → BOQ extraction → item-by-item review.

## Testing

```bash
cd backend && .venv/Scripts/python -m pytest        # 68 tests
cd frontend && npx tsc --noEmit && npm run build    # typecheck + prod build
cd frontend && npx playwright test                  # 5 e2e (needs dev servers running)
```

Covered: auth, tenant isolation (cross-org ID guessing → 404), role enforcement, Decimal calc correctness, concurrent stock mutations, negative-stock prevention, quotation lifecycle + immutability, idempotent conversion/reservation, the full 100 MT workflow, tender extraction review, dashboard aggregation.

## Railway Deployment

Two methods (full steps in `docs/deployment.md`):

- **CLI**: `railway init` → add Postgres + Redis → `railway add -s api|worker|web` → `railway up -s <svc>` (repo root). Each service sets `RAILWAY_DOCKERFILE_PATH` (`backend/Dockerfile` ×2, `frontend/Dockerfile`).
- **GitHub**: push this repo → create services in the dashboard with the same Dockerfile paths.

Key env vars — api: `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENVIRONMENT=production`, `SECURE_COOKIES=true`, `CELERY_ALWAYS_EAGER=false`, `CORS_ORIGINS=<web domain>`; worker: same minus CORS + `SERVICE_ROLE=worker`; web: `API_UPSTREAM=https://<api domain>`.

## Known Limitations

- AI extraction uses a deterministic built-in provider unless an LLM key is configured.
- Tender/BOQ extraction requires human review by design — extracted values are evidence, never silently confirmed.
- Frontend bundle is a single ~1 MB chunk (route-level code splitting is a follow-up).
- No statutory accounting/tax filing — finance module covers invoices, receivables/payables, valuation, and margins only.

## Docs

- `docs/architecture.md` · `docs/data-model.md` · `docs/api-contracts.md` · `docs/deployment.md`
- `BUILD_STATUS.md` — full evidence trail of what was verified and how.
