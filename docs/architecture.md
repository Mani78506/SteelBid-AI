# SteelBid AI 2.0 — Architecture

## Overview
SteelBid AI 2.0 is a **modular monolith** "Steel Business Operating System" serving four business profiles on one shared core:

- Steel traders
- Steel distributors
- Steel fabricators
- Railway / infrastructure contractors

A company (organization) can carry **multiple profiles** (`business_profiles: text[]`). Profile membership drives module visibility and dashboard layout — not code duplication. All profiles share the identity, material, inventory, sales, purchasing, market and finance core.

## Repository layout
```
SteelBid/
├── backend/                # Python 3.12 FastAPI modular monolith
│   ├── app/
│   │   ├── main.py         # ASGI app, middleware, router registration
│   │   ├── config.py       # pydantic-settings env validation
│   │   ├── database.py     # engine/session factory
│   │   ├── core/           # security (argon2id, sessions), deps (tenant), errors, pagination, audit
│   │   ├── models/         # SQLAlchemy 2.0 mapped models (one file per domain group)
│   │   ├── schemas/        # Pydantic v2 DTOs
│   │   ├── api/            # FastAPI routers (thin: validate → authorize → call service)
│   │   ├── services/       # domain services (business rules, workflows)
│   │   ├── calc/           # deterministic Decimal calculation services (margins, availability, landed cost)
│   │   ├── ai/             # pluggable LLM provider + extraction/explanation services
│   │   └── seed/           # deterministic, idempotent demo seed
│   ├── alembic/            # migrations
│   └── tests/              # pytest
├── frontend/               # React + Vite + TS + Tailwind + shadcn-style components
│   └── src/
│       ├── api/            # typed fetch client (OpenAPI-shaped types)
│       ├── components/     # ui primitives + shell (sidebar, topbar, tables, KPI cards)
│       ├── pages/          # route pages per module
│       └── lib/            # query client, formatting, session context
├── docs/
├── docker-compose.yml      # web, api, worker, postgres, redis
├── Dockerfile.web / Dockerfile.api
└── railway.json
```

## Layering rules (backend)
1. **Routers** never contain financial arithmetic or workflow logic — they parse, authorize (role + tenant), call a *service*, and serialize.
2. **Services** own transactions and call **calc** functions for arithmetic. All money/quantity math uses `Decimal` (`Numeric(20,6)` quantities, `Numeric(20,4)` money).
3. **Calc** functions are pure and unit-tested in isolation.
4. **AI** services never write financial facts. They read records, propose structured outputs with `extraction_evidence`, and require human approval for binding actions.

## Tenancy model
Every tenant-owned table has `organization_id` as part of its integrity:
- FK to `organizations.id`
- Composite unique constraints include `organization_id` (e.g. material SKU unique per org)
- Every repository query is scoped through a `TenantContext` dependency that resolves the active organization from the session **and validates the membership server-side on every request**.
- Cross-tenant reference protection: service layer validates that related records (material, warehouse, customer, ...) belong to the same organization before linking.

## Auth
- Argon2id password hashing (argon2-cffi).
- Server-side sessions: opaque 256-bit token in an `HttpOnly; SameSite=Lax` cookie (`Secure` in production). No tokens in `localStorage`.
- Session row carries `active_organization_id`; org switching validates membership and invalidates tenant cache on the client (React Query `queryClient.clear()` on switch).
- Roles: ADMIN, SALES, PROCUREMENT, INVENTORY, FABRICATION, ESTIMATOR, FINANCE, VIEWER — enforced by a permission matrix dependency.

## Async work
Celery + Redis for document extraction/AI jobs in deployment. Locally (no Redis) Celery runs in `task_always_eager` fallback so the same code path executes synchronously. `ai_jobs` table records status either way.

## Consistency & safety
- Inventory mutations are single-transaction ledger writes: `inventory_movements` row + locked `stock_lots` update (`SELECT ... FOR UPDATE`), with DB `CHECK` constraints preventing negative on_hand/reserved.
- Idempotency keys on important writes (receipts, POs, reservations) via unique constraint on `(organization_id, idempotency_key)`.
- Approved revisions (quotations, BOMs) are immutable — changes create a new version row.
- Audit: every mutating route writes `audit_events` (actor, org, action, entity, before/after diff, request id).

## Frontend shell
Charcoal sidebar, slate/white content, steel-blue accent, restrained teal highlights, Framer Motion transitions (respecting `prefers-reduced-motion`), TanStack Query for server state, TanStack Table for grids, React Hook Form + Zod for forms, Recharts for trends.
