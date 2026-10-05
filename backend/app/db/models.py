"""Import every model so SQLAlchemy metadata (and Alembic autogenerate) sees them all."""

from app.core.database import Base
from app.features.audit.models import AuditEvent
from app.features.auth.models import Company, User
from app.features.invoices.models import Invoice, InvoiceLineItem
from app.features.validation.models import ValidationFinding
from app.features.vendors.models import Vendor
from app.infrastructure.storage.models import StoredFile

__all__ = [
    "AuditEvent",
    "Base",
    "Company",
    "Invoice",
    "InvoiceLineItem",
    "StoredFile",
    "User",
    "ValidationFinding",
    "Vendor",
]
