# Import all models here so Alembic autogenerate picks them up
from app.models.base import Base  # noqa: F401
from app.models.enums import *  # noqa: F401, F403
from app.models.masters import Customer, Supplier, SystemConfig, User, Vertical  # noqa: F401
from app.models.deposit_request import DepositRequest  # noqa: F401
from app.models.payment import PaymentDetails  # noqa: F401
from app.models.workflow import AccountsAction, MerchandiserAction, StatusHistory  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.integrations import DefaultedSupplier, GoogleFormSubmission, SyncLog  # noqa: F401
from app.models.analytics import AnalyticsSnapshot  # noqa: F401
