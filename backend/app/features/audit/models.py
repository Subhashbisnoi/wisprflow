import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TenantMixin, UUIDPrimaryKeyMixin, str_enum
from app.features.auth.models import User

if TYPE_CHECKING:
    from app.features.invoices.models import Invoice


class AuditAction(enum.StrEnum):
    INVOICE_UPLOADED = "invoice_uploaded"
    EXTRACTION_STARTED = "extraction_started"
    EXTRACTION_COMPLETED = "extraction_completed"
    EXTRACTION_FAILED = "extraction_failed"
    EXTRACTION_RETRIED = "extraction_retried"
    VENDOR_LINKED = "vendor_linked"
    VENDOR_CREATED = "vendor_created"
    VENDOR_UPDATED = "vendor_updated"
    FIELD_CORRECTED = "field_corrected"
    LINE_ITEM_ADDED = "line_item_added"
    LINE_ITEM_CORRECTED = "line_item_corrected"
    LINE_ITEM_REMOVED = "line_item_removed"
    INVOICE_APPROVED = "invoice_approved"
    INVOICE_REJECTED = "invoice_rejected"


class AuditEvent(UUIDPrimaryKeyMixin, TenantMixin, Base):
    """Append-only. Never updated or deleted by application code (D-056)."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_company_invoice_created", "company_id", "invoice_id", "created_at"),
        Index("ix_audit_company_entity", "company_id", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_company_created", "company_id", "created_at"),
    )

    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE")
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    action: Mapped[AuditAction] = mapped_column(
        str_enum(AuditAction, "action", length=40),
        nullable=False,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    field_name: Mapped[str | None] = mapped_column(String(100))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    actor: Mapped[User | None] = relationship(lazy="joined")
    # Never loaded; declared so the unit of work inserts the invoice before its events.
    invoice: Mapped["Invoice | None"] = relationship(lazy="raise")
