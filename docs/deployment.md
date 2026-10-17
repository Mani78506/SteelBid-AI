# SteelBid AI — Deployment Guide

## Services

| Service | Path | Role |
|---|---|---|
| `api` | `backend/` | FastAPI modular monolith (uvicorn). Runs `alembic upgrade head` on boot. |
| `worker` | `backend/` | Celery worker (document extraction, AI jobs). Same image, different command. |
| `web` | `frontend/` | Static Vite build served by nginx; `/api/*` proxied to `api`. |
| `db` | Postgres 17 | Persistent volume. |
| `redis` | Redis 7 | Session-free cache + Celery broker. |

## Local (Docker Compose)

```bash
cp backend/.env.example backend/.env   # fill values
docker compose up --build
# web: http://localhost:8080   api: http://localhost:8000/api/docs
```

Seed demo data (dev only, never in production):

```bash
docker compose exec api python -m app.seed.run
```

## Railway

1. Create a project; add **PostgreSQL** and **Redis** plugins.
2. Create three services from this repo:
   - `api` — Dockerfile `backend/Dockerfile`, variables from `backend/.env.example`, `railway.toml` pins build.
   - `worker` — same Dockerfile, custom start command `celery -A app.worker:celery_app worker -l info`.
   - `web` — Dockerfile `frontend/Dockerfile`. Point nginx `proxy_pass` at the api service domain (edit `nginx.conf` `api` host or use Railway private networking `http://api.railway.internal:8000`).
3. Set env vars: `DATABASE_URL` (Railway Postgres URL), `REDIS_URL`, `SECRET_KEY`, `COOKIE_SECURE=true`, `CORS_ORIGINS=https://<web-domain>`, `LLM_PROVIDER`.
4. Deploy — migrations run automatically on api boot. To run manually:
   `railway run --service api -- alembic upgrade head`
5. Health checks: `GET /api/health` (liveness), `GET /api/health/ready` (DB+redis readiness).

## Seeding policy

`DEMO_MODE` must be `true` (default); the seed refuses to run when `DEMO_MODE=false` to run `python -m app.seed.run`. The seed is deterministic + idempotent; all demo orgs are prefixed `[DEMO]`.

## Demo credentials

- `admin@apex.demo` / `admin@metro.demo` / `admin@precision.demo` / `admin@railbuild.demo`
- `viewer@apex.demo` (read-only role demo)
- Password = `DEMO_ADMIN_PASSWORD` env var (`SteelBid#Demo2026` in the default `.env.example`).

## Known deployment notes

- Multi-org users log in once; organization switching is server-side via `POST /api/v1/auth/switch-organization` — no localStorage tokens.
- Cookie auth requires `COOKIE_SECURE=false` on plain HTTP; set `true` behind HTTPS.
- `worker` service is optional for the POC (extraction runs synchronously in the api) but recommended at scale.
