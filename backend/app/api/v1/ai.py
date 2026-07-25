"""AI Business Intelligence endpoints.

Access model:
  - super_admin  → always allowed, no config needed
  - all others   → need ai_access_enabled = true on their user row (set by super_admin)
  - Provider, API key, and model are stored in system_config (managed via /admin/ai/config)
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireSuperAdmin, get_current_user
from app.core.exceptions import AuthorizationError, BusinessRuleError, ValidationError
from app.core.rate_limit import limiter
from app.models.enums import UserRole
from app.models.masters import User
from app.services.bi_service import run_bi_query

router = APIRouter(prefix="/ai", tags=["ai"])
settings = get_settings()

DB = Annotated[AsyncSession, Depends(get_db_session)]


# ── Permission dependency ─────────────────────────────────────────────────────

async def _require_ai_access(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: DB,
) -> CurrentUser:
    if current_user.role == UserRole.SUPER_ADMIN:
        return current_user
    result = await db.execute(
        select(User.ai_access_enabled).where(User.id == current_user.id)
    )
    enabled = result.scalar_one_or_none()
    if not enabled:
        raise AuthorizationError(
            "AI BI Assistant access not granted. Contact your Super Admin to enable it."
        )
    return current_user


AIUser = Annotated[CurrentUser, Depends(_require_ai_access)]
SuperAdmin = Annotated[CurrentUser, RequireSuperAdmin]


# ── Schemas ───────────────────────────────────────────────────────────────────

class ConvMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class BIQueryRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    history: list[ConvMessage] = []


class BIQueryResponse(BaseModel):
    answer: str
    sql: str
    row_count: int
    rows: list[dict]
    columns: list[str] = []
    provider: str = ""


class AIAccessStatus(BaseModel):
    has_access: bool
    reason: str | None = None


class AIConfigUpdate(BaseModel):
    provider: str = Field(pattern=r"^(groq|openai|claude)$")
    api_key: str = Field(min_length=10)
    model: str | None = None


class AIConfigResponse(BaseModel):
    provider: str
    model: str | None
    api_key_set: bool


class AIAccessPatch(BaseModel):
    ai_access_enabled: bool


# ── User-facing endpoints ─────────────────────────────────────────────────────

@router.get("/access", response_model=AIAccessStatus)
async def check_ai_access(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    db: DB,
) -> AIAccessStatus:
    """Returns whether the calling user has AI BI access."""
    if current_user.role == UserRole.SUPER_ADMIN:
        return AIAccessStatus(has_access=True)
    result = await db.execute(
        select(User.ai_access_enabled).where(User.id == current_user.id)
    )
    enabled = result.scalar_one_or_none() or False
    return AIAccessStatus(
        has_access=enabled,
        reason=None if enabled else "Contact your Super Admin to enable AI BI access.",
    )


@router.post("/query", response_model=BIQueryResponse)
@limiter.limit(settings.rate_limit_ai_query)
async def bi_query(
    request: Request,
    body: BIQueryRequest,
    current_user: AIUser,
    db: DB,
) -> BIQueryResponse:
    """Convert a natural language question into a BI answer."""
    from app.services.audit_service import AuditService
    history = [{"role": m.role, "content": m.content} for m in body.history]
    try:
        result = await run_bi_query(body.question, db, history=history or None)
    except Exception as exc:
        raise BusinessRuleError(str(exc)) from exc

    try:
        forwarded = request.headers.get("x-forwarded-for")
        ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else None)
        await AuditService(db).record_ai_query(
            changed_by=current_user.id,
            question=body.question,
            ip_address=ip,
            user_agent=request.headers.get("user-agent"),
        )
    except Exception:
        await db.rollback()

    try:
        prov_result = await db.execute(
            text("SELECT config_value FROM system_config WHERE config_key = 'ai_provider'")
        )
        provider = (prov_result.scalar_one_or_none() or "groq")
    except Exception:
        provider = "groq"

    return BIQueryResponse(**result, provider=provider)


# ── Super Admin config endpoints ──────────────────────────────────────────────

@router.get("/config", response_model=AIConfigResponse)
async def get_ai_config(current_user: SuperAdmin, db: DB) -> AIConfigResponse:
    """Get current AI provider configuration (Super Admin only)."""
    result = await db.execute(
        text("SELECT config_key, config_value FROM system_config WHERE config_key IN ('ai_provider', 'ai_api_key', 'ai_model')")
    )
    cfg = {row.config_key: row.config_value for row in result.fetchall()}
    return AIConfigResponse(
        provider=cfg.get("ai_provider", "groq"),
        model=cfg.get("ai_model") or None,
        api_key_set=bool(cfg.get("ai_api_key")),
    )


@router.put("/config", response_model=AIConfigResponse)
async def set_ai_config(
    body: AIConfigUpdate, current_user: SuperAdmin, db: DB
) -> AIConfigResponse:
    """Set AI provider, API key, and optional model (Super Admin only)."""
    async def _upsert(key: str, value: str, desc: str) -> None:
        # Resolve real user id — dev bypass user may not exist in users table
        from sqlalchemy import select as sa_select
        exists = await db.execute(
            sa_select(User.id).where(User.id == current_user.id)
        )
        uid = str(current_user.id) if exists.scalar_one_or_none() else None
        await db.execute(
            text("""
                INSERT INTO system_config (id, config_key, config_value, description, updated_by, updated_at)
                VALUES (gen_random_uuid(), :k, :v, :d, :uid, NOW())
                ON CONFLICT (config_key) DO UPDATE
                  SET config_value = EXCLUDED.config_value,
                      updated_by   = EXCLUDED.updated_by,
                      updated_at   = NOW()
            """),
            {"k": key, "v": value, "d": desc, "uid": uid},
        )

    await _upsert("ai_provider", body.provider, "AI provider: groq | openai | claude")
    await _upsert("ai_api_key", body.api_key, "AI provider API key")
    if body.model:
        await _upsert("ai_model", body.model, "AI model override")
    await db.commit()

    return AIConfigResponse(
        provider=body.provider,
        model=body.model,
        api_key_set=True,
    )


@router.patch("/users/{user_id}/access", response_model=AIAccessStatus)
async def set_user_ai_access(
    user_id: UUID,
    body: AIAccessPatch,
    current_user: SuperAdmin,
    db: DB,
) -> AIAccessStatus:
    """Grant or revoke AI BI access for a specific user (Super Admin only)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("User not found.")
    if user.role == UserRole.SUPER_ADMIN:
        return AIAccessStatus(has_access=True, reason="Super Admins always have access.")

    await db.execute(
        text("UPDATE users SET ai_access_enabled = :val WHERE id = :uid"),
        {"val": body.ai_access_enabled, "uid": str(user_id)},
    )
    await db.commit()

    return AIAccessStatus(
        has_access=body.ai_access_enabled,
        reason=None if body.ai_access_enabled else "Access revoked by Super Admin.",
    )
