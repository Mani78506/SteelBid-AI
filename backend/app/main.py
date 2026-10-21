from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.core.errors import RequestContextMiddleware, register_error_handlers

settings = get_settings()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SteelBid AI 2.0 API",
        version="2.0.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*", "Idempotency-Key", "X-Request-Id"],
        expose_headers=["X-Request-Id"],
    )
    register_error_handlers(app)

    from app.api import (ai, audit, auth, customers, dashboard, fabrication, finance, notifications,
                         inventory, logistics, market, materials, procurement, projects,
                         quotations, sales_orders, tenders)
    for module in (auth, dashboard, customers, quotations, sales_orders, materials, market,
                   procurement, inventory, fabrication, projects, tenders, logistics,
                   finance, ai, audit, notifications):
        app.include_router(module.router, prefix="/api/v1")

    @app.get("/api/health", tags=["system"])
    def health():
        return {"status": "ok", "service": "steelbid-api", "version": "2.0.0"}

    @app.get("/api/health/ready", tags=["system"])
    def ready():
        from sqlalchemy import text
        from app.database import engine
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}

    return app


app = create_app()
