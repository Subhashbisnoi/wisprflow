"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees them all."""

from app.core.database import Base
from app.features.audit.models import AuditEvent
from app.features.auth.models import Company, User
from app.features.invoices.models import Invoice, InvoiceLineItem
from app.features.validation.models import ValidationFinding
from app.features.vendors.models import Vendor

__all__ = [
    "AuditEvent",
    "Base",
    "Company",
    "Invoice",
    "InvoiceLineItem",
    "User",
    "ValidationFinding",
    "Vendor",
]
