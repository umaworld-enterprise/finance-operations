"""FastAPI application factory with lifespan, middleware, and global error handling."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

settings = get_settings()
logger = get_logger(__name__)

# ── Scheduler (analytics snapshot refresh every 30 minutes) ──────────────────
_scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: configure logging and start scheduler. Shutdown: stop scheduler."""
    configure_logging(debug=settings.app_debug)
    logger.info("Starting Advance Deposit Tracker API", env=settings.app_env)

    from app.core.database import AsyncSessionFactory
    from app.analytics.snapshot_job import refresh_all_snapshots

    _scheduler.add_job(
        refresh_all_snapshots,
        "interval",
        minutes=30,
        args=[AsyncSessionFactory],
        id="analytics_snapshot_refresh",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Analytics snapshot scheduler started")

    yield

    _scheduler.shutdown(wait=False)
    logger.info("Scheduler stopped")


# ── Application ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Advance Deposit Tracker API",
        version="1.0.0",
        description="Enterprise API for managing supplier advance deposits at Sunshine.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS ─────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Global error handlers ─────────────────────────────────────────────────
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error_code": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled exception",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
        )

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["health"])
    async def health() -> dict:
        return {"status": "ok", "env": settings.app_env}

    # ── Register API routers ──────────────────────────────────────────────────
    from app.api.v1.auth import router as auth_router
    from app.api.v1.requests import router as requests_router
    from app.api.v1.payment import router as payment_router
    from app.api.v1.analytics import router as analytics_router
    from app.api.v1.reports import router as reports_router
    from app.api.v1.webhooks import router as webhooks_router
    from app.api.v1.admin import router as admin_router
    from app.api.v1.masters.suppliers import router as suppliers_router
    from app.api.v1.masters.customers import router as customers_router
    from app.api.v1.masters.verticals import router as verticals_router
    from app.api.v1.masters.users import router as users_router

    prefix = "/api/v1"
    for r in [
        auth_router,
        requests_router,
        payment_router,
        analytics_router,
        reports_router,
        webhooks_router,
        admin_router,
        suppliers_router,
        customers_router,
        verticals_router,
        users_router,
    ]:
        app.include_router(r, prefix=prefix)

    return app


app = create_app()
