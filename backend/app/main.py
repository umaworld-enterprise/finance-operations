"""FastAPI application factory with lifespan, middleware, and global error handling."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger

settings = get_settings()
logger = get_logger(__name__)


class JSONErrorEnvelopeMiddleware:
    """Convert any unhandled exception into a JSON 500 response.

    Must be registered BEFORE CORSMiddleware (i.e. sit inside it) so the
    error response still passes through CORS and gets its headers. Without
    this, unhandled exceptions escape to Starlette's ServerErrorMiddleware
    which lives OUTSIDE CORS — the browser then reports a bogus CORS/network
    error instead of the real 500.
    """

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message) -> None:  # type: ignore[no-untyped-def]
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            logger.error(
                "Unhandled exception",
                path=scope.get("path"),
                method=scope.get("method"),
                error=str(exc),
                exc_info=True,
            )
            if response_started:
                raise  # Too late to send a new response — let uvicorn close it.
            response = JSONResponse(
                status_code=500,
                content={"error_code": "INTERNAL_ERROR", "message": "An unexpected error occurred."},
            )
            await response(scope, receive, send)

# ── Scheduler (analytics snapshot refresh every 30 minutes) ──────────────────
_scheduler = AsyncIOScheduler()
_scheduler_lock_file = None


def _acquire_scheduler_lock() -> bool:
    """Elect exactly one uvicorn worker to run the scheduler.

    With --workers N, each worker process runs the lifespan and would start
    its own APScheduler, multiplying the snapshot job N-fold. Workers share
    a container, so an exclusive file lock picks a single owner. Held for
    the worker's lifetime; released automatically if the worker dies.
    """
    global _scheduler_lock_file
    try:
        import fcntl
        _scheduler_lock_file = open("/tmp/adt_scheduler.lock", "w")
        fcntl.flock(_scheduler_lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except ImportError:
        return True  # Windows dev — single worker, no election needed
    except OSError:
        if _scheduler_lock_file is not None:
            _scheduler_lock_file.close()
            _scheduler_lock_file = None
        return False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup: configure logging and start scheduler. Shutdown: stop scheduler."""
    configure_logging(debug=settings.app_debug)
    logger.info("Starting Finance Operations API", env=settings.app_env)

    from app.core.database import AsyncSessionFactory
    from app.analytics.snapshot_job import refresh_all_snapshots
    from app.services.notification_service import send_fallback_notifications

    scheduler_owner = _acquire_scheduler_lock()
    if scheduler_owner:
        _scheduler.add_job(
            refresh_all_snapshots,
            "interval",
            minutes=30,
            args=[AsyncSessionFactory],
            id="analytics_snapshot_refresh",
            replace_existing=True,
        )
        _scheduler.add_job(
            send_fallback_notifications,
            "interval",
            minutes=30,
            args=[AsyncSessionFactory],
            id="payment_notification_fallback",
            replace_existing=True,
        )
        _scheduler.start()
        logger.info("Analytics snapshot scheduler started (this worker owns the lock)")
    else:
        logger.info("Scheduler lock held by another worker — skipping scheduler start")

    yield

    if scheduler_owner:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


# ── Application ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    app = FastAPI(
        title="Finance Operations API",
        version="1.0.0",
        description="Enterprise API for managing supplier advance deposits at Sunshine.",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── GZip + Error envelope + CORS ──────────────────────────────────────────
    # Order matters: add_middleware() prepends, so the LAST one added is
    # outermost. The envelope must be added before CORS so it sits INSIDE it —
    # its JSON 500s then pass through CORS and get their headers.
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(JSONErrorEnvelopeMiddleware)
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

    @app.exception_handler(PydanticValidationError)
    async def pydantic_validation_error_handler(_: Request, exc: PydanticValidationError) -> JSONResponse:
        # Raised when an endpoint constructs a Pydantic model manually (outside
        # FastAPI's request validation). Return 422 like normal validation.
        messages = "; ".join(
            str(err.get("ctx", {}).get("error") or err.get("msg", "Invalid value"))
            for err in exc.errors()
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "VALIDATION_ERROR", "message": messages},
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error_code": "CONFLICT", "message": "A record with these details already exists."},
        )

    @app.exception_handler(DBAPIError)
    async def dbapi_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
        # Postgres triggers guard business rules with RAISE EXCEPTION (P0001).
        # Surface the trigger's own message as a 400 instead of a blank 500.
        # SQLAlchemy's asyncpg dialect wraps the driver error, so check both
        # exc.orig and its __cause__ for the sqlstate/message.
        candidates = []
        orig = getattr(exc, "orig", None)
        if orig is not None:
            candidates.append(orig)
            cause = getattr(orig, "__cause__", None)
            if cause is not None:
                candidates.append(cause)
        sqlstate = None
        pg_message = None
        for c in candidates:
            sqlstate = sqlstate or getattr(c, "sqlstate", None) or getattr(c, "pgcode", None)
            pg_message = pg_message or getattr(c, "message", None)
        if not pg_message and orig is not None:
            pg_message = str(orig)
        if sqlstate == "P0001" and pg_message:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"error_code": "BUSINESS_RULE_VIOLATION", "message": pg_message},
            )
        logger.error(
            "Database error",
            path=request.url.path,
            method=request.method,
            error=str(exc),
            exc_info=True,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error_code": "DATABASE_ERROR", "message": "A database error occurred."},
        )

    @app.exception_handler(OperationalError)
    async def operational_error_handler(_: Request, exc: OperationalError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error_code": "SERVICE_UNAVAILABLE", "message": "Database temporarily unavailable."},
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
    from app.api.v1.admin import router as admin_router
    from app.api.v1.masters.suppliers import router as suppliers_router
    from app.api.v1.masters.customers import router as customers_router
    from app.api.v1.masters.verticals import router as verticals_router
    from app.api.v1.masters.payment_terms import router as payment_terms_router
    from app.api.v1.masters.users import router as users_router
    from app.api.v1.ai import router as ai_router
    from app.api.v1.public_form import router as public_form_router
    from app.api.v1.notifications import router as notifications_router

    prefix = "/api/v1"
    for r in [
        auth_router,
        requests_router,
        payment_router,
        analytics_router,
        reports_router,
        admin_router,
        suppliers_router,
        customers_router,
        verticals_router,
        payment_terms_router,
        users_router,
        ai_router,
        public_form_router,
        notifications_router,
    ]:
        app.include_router(r, prefix=prefix)

    return app


app = create_app()
