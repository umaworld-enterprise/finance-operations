"""Customer master endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.dependencies import CurrentUser, RequireFinanceAdmin, get_current_user
from app.core.exceptions import NotFoundError
from app.models.masters import Customer
from app.repositories.base import BaseRepository
from app.schemas.masters import CustomerCreate, CustomerResponse, CustomerUpdate
from app.services.audit_service import AuditService

router = APIRouter(prefix="/masters/customers", tags=["masters-customers"])

DB = Annotated[AsyncSession, Depends(get_db_session)]
User = Annotated[CurrentUser, Depends(get_current_user)]
FinanceAdmin = Annotated[CurrentUser, RequireFinanceAdmin]


def _ip(req: Request) -> str | None:
    forwarded = req.headers.get("x-forwarded-for")
    return forwarded.split(",")[0].strip() if forwarded else (req.client.host if req.client else None)


@router.get("", response_model=list[CustomerResponse])
async def list_customers(db: DB, _: User) -> list[CustomerResponse]:
    repo = BaseRepository(db, Customer)
    customers = await repo.list_all(is_active=True)
    return [CustomerResponse.model_validate(c) for c in customers]


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(data: CustomerCreate, current_user: FinanceAdmin, db: DB, request: Request) -> CustomerResponse:
    repo = BaseRepository(db, Customer)
    customer = await repo.create(**data.model_dump())
    await AuditService(db).record_create(
        "customers", customer.id, current_user.id,
        ip_address=_ip(request),
        user_agent=request.headers.get("user-agent"),
        new_value=data.name,
    )
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID, data: CustomerUpdate, current_user: FinanceAdmin, db: DB, request: Request
) -> CustomerResponse:
    repo = BaseRepository(db, Customer)
    customer = await repo.get_by_id(customer_id)
    if not customer:
        raise NotFoundError(f"Customer {customer_id} not found.")

    audit = AuditService(db)
    ip = _ip(request)
    ua = request.headers.get("user-agent")
    update_data = data.model_dump(exclude_unset=True)

    for field, new_val in update_data.items():
        await audit.record_update(
            "customers", customer.id, current_user.id,
            field_name=field,
            old_value=str(getattr(customer, field, "")),
            new_value=str(new_val),
            ip_address=ip,
            user_agent=ua,
        )

    customer = await repo.update(customer, **update_data)
    return CustomerResponse.model_validate(customer)
