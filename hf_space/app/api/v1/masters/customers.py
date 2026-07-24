"""Customer master endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
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


@router.get("", response_model=list[CustomerResponse])
async def list_customers(db: DB, _: User) -> list[CustomerResponse]:
    repo = BaseRepository(db, Customer)
    customers = await repo.list_all(is_active=True)
    return [CustomerResponse.model_validate(c) for c in customers]


@router.post("", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(data: CustomerCreate, current_user: FinanceAdmin, db: DB) -> CustomerResponse:
    repo = BaseRepository(db, Customer)
    customer = await repo.create(**data.model_dump())
    await AuditService(db).record_create("customers", customer.id, current_user.id)
    return CustomerResponse.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: UUID, data: CustomerUpdate, current_user: FinanceAdmin, db: DB
) -> CustomerResponse:
    repo = BaseRepository(db, Customer)
    customer = await repo.get_by_id(customer_id)
    if not customer:
        raise NotFoundError(f"Customer {customer_id} not found.")
    customer = await repo.update(customer, **data.model_dump(exclude_unset=True))
    return CustomerResponse.model_validate(customer)
