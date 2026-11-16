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

**Option A — CLI (deploys local source directly, no GitHub needed):**

```bash
railway login                              # browser auth — do this yourself
railway init                               # create project
railway add --database postgres            # Postgres plugin
railway add --database redis               # Redis plugin

# api service
railway add --service api
railway up --service api                   # builds backend/Dockerfile on Railway
railway variables --service api \
  --set "DATABASE_URL=\${{Postgres.DATABASE_URL}}" \
  --set "REDIS_URL=\${{Redis.REDIS_URL}}" \
  --set "SECRET_KEY=<generate-a-long-random-string>" \
  --set "ENVIRONMENT=production" \
  --set "SECURE_COOKIES=true" \
  --set "CELERY_ALWAYS_EAGER=false" \
  --set "DEMO_MODE=false" \
  --set "PUBLIC_DEMO_ENABLED=true" \
  --set "CORS_ORIGINS=https://<web-service-domain>.up.railway.app"

# worker (same image, different command)
railway add --service worker
railway up --service worker
#   Railway dashboard → worker → Settings → Deploy → Custom Start Command:
#   celery -A app.worker:celery_app worker -l info
railway variables --service worker \
  --set "DATABASE_URL=\${{Postgres.DATABASE_URL}}" \
  --set "REDIS_URL=\${{Redis.REDIS_URL}}" \
  --set "SECRET_KEY=<same-secret>" \
  --set "ENVIRONMENT=production" \
  --set "CELERY_ALWAYS_EAGER=false" \
  --set "DEMO_MODE=false" \
  --set "SERVICE_ROLE=worker"

# web service — nginx proxies /api/* to the api service's private domain
railway add --service web
railway up --service web                   # builds frontend/Dockerfile
railway variables --service web \
  --set "API_UPSTREAM=http://api.railway.internal:8000"
#   API CORS is set to the web public domain above.
```

**Option B — GitHub (push repo, then in the Railway dashboard):**

1. Push this repo to GitHub, create a project, add **PostgreSQL** + **Redis** plugins.
2. Create three services from the repo. In each service's Railway **Settings → Build**, set its **Config File Path** so configuration stays service-specific:
   - `api`: `/backend/railway.api.toml`
   - `worker`: `/backend/railway.worker.toml`
   - `web`: `/frontend/railway.web.toml`
   This prevents the API Dockerfile and API HTTP health check from being applied to the worker or web service.
   Also set `RAILWAY_DOCKERFILE_PATH` as a service variable: `backend/Dockerfile` for API and worker, and `frontend/Dockerfile` for web. No repository-root `railway.toml` is used because it would override all three service configurations.
3. Set the same env vars listed in Option A on each service.
4. Deploy — migrations run automatically on api boot.

**Either way, afterwards:**

- Keep `DEMO_MODE=false` in production. Production demo records must be deliberately
  created through the approved, labelled application workflow; automatic seeding is
  intentionally blocked.
- To expose an already-provisioned fictional `VIEWER` identity on the public landing
  page, set `PUBLIC_DEMO_ENABLED=true`. This never enables seeding, admin access, or
  write permissions. It remains unavailable if that labelled viewer record is absent.
- Health checks: `GET /api/health` (liveness), `GET /api/health/ready` (DB+redis readiness).
- Enable private networking on all services so `api.railway.internal` resolves.

## Seeding policy

`DEMO_MODE` must remain `false` in production. The seed command intentionally refuses
to run there. Use a non-production environment for seeded demo fixtures; all fixture
organizations must remain explicitly labelled `[DEMO]`.

## Demo credentials

- `admin@apex.demo` / `admin@metro.demo` / `admin@precision.demo` / `admin@railbuild.demo`
- `viewer@apex.demo` (read-only role demo)
- Password = `DEMO_ADMIN_PASSWORD` env var (`SteelBid#Demo2026` in the default `.env.example`).

## Known deployment notes

- Multi-org users log in once; organization switching is server-side via `POST /api/v1/auth/switch-organization` — no localStorage tokens.
- Cookie auth requires `SECURE_COOKIES=false` on plain HTTP; set `true` behind HTTPS (required on Railway public domains).
- `worker` service is optional for the POC (extraction runs synchronously in the api) but recommended at scale.
