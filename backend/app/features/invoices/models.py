import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import (
    Base,
    TenantMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    str_enum,
)
from app.features.auth.models import User
from app.features.vendors.models import Vendor

if TYPE_CHECKING:
    from app.features.validation.models import ValidationFinding

Money = Numeric(14, 2)


class InvoiceStatus(enum.StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FAILED = "failed"


class ExtractionMethod(enum.StrEnum):
    TEXT_LAYER = "text_layer"
    VISION = "vision"


# Header fields a reviewer may correct, mapped to their Python type.
EDITABLE_HEADER_FIELDS: dict[str, type] = {
    "vendor_name": str,
    "vendor_gstin": str,
    "buyer_gstin": str,
    "invoice_number": str,
    "invoice_date": date,
    "due_date": date,
    "subtotal": Decimal,
    "cgst": Decimal,
    "sgst": Decimal,
    "igst": Decimal,
    "total": Decimal,
}

EDITABLE_LINE_FIELDS: dict[str, type] = {
    "description": str,
    "hsn_sac": str,
    "quantity": Decimal,
    "rate": Decimal,
    "amount": Decimal,
}


class Invoice(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        Index("ix_invoices_company_status", "company_id", "status"),
        Index("ix_invoices_company_vendor", "company_id", "vendor_id"),
        Index("ix_invoices_company_invoice_date", "company_id", "invoice_date"),
        Index("ix_invoices_company_created_at", "company_id", "created_at"),
        Index("ix_invoices_company_total", "company_id", "total"),
        Index("ix_invoices_company_due_date", "company_id", "due_date"),
        Index("ix_invoices_company_sha256", "company_id", "file_sha256"),
        Index("ix_invoices_duplicate_key", "company_id", "vendor_gstin", "invoice_number"),
    )

    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vendors.id", ondelete="SET NULL")
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    reviewed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))

    status: Mapped[InvoiceStatus] = mapped_column(
        str_enum(InvoiceStatus, "status"), nullable=False, default=InvoiceStatus.QUEUED
    )

    # File
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    file_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)

    # Extraction bookkeeping
    extraction_method: Mapped[ExtractionMethod | None] = mapped_column(
        str_enum(ExtractionMethod, "extraction_method")
    )
    extraction_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)

    # Extracted header fields (GSTINs are wide enough to hold malformed raw values)
    vendor_name: Mapped[str | None] = mapped_column(String(300))
    vendor_gstin: Mapped[str | None] = mapped_column(String(32))
    buyer_gstin: Mapped[str | None] = mapped_column(String(32))
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    due_date: Mapped[date | None] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, default="INR")
    subtotal: Mapped[Decimal | None] = mapped_column(Money)
    cgst: Mapped[Decimal | None] = mapped_column(Money)
    sgst: Mapped[Decimal | None] = mapped_column(Money)
    igst: Mapped[Decimal | None] = mapped_column(Money)
    total: Mapped[Decimal | None] = mapped_column(Money)
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, default=dict)
    raw_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Validation summary (denormalised for fast queue rendering)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Review
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    review_comment: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    vendor: Mapped[Vendor | None] = relationship(lazy="joined")
    uploaded_by: Mapped[User] = relationship(foreign_keys=[uploaded_by_id])
    reviewed_by: Mapped[User | None] = relationship(foreign_keys=[reviewed_by_id])
    line_items: Mapped[list["InvoiceLineItem"]] = relationship(
        back_populates="invoice",
        order_by="InvoiceLineItem.position",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    findings: Mapped[list["ValidationFinding"]] = relationship(
        cascade="all, delete-orphan", lazy="selectin", viewonly=False
    )

    def is_editable(self) -> bool:
        return self.status == InvoiceStatus.NEEDS_REVIEW


class InvoiceLineItem(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "invoice_line_items"
    __table_args__ = (
        Index("ix_line_items_company_invoice", "company_id", "invoice_id", "position"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    hsn_sac: Mapped[str | None] = mapped_column(String(20))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))
    rate: Mapped[Decimal | None] = mapped_column(Money)
    amount: Mapped[Decimal | None] = mapped_column(Money)
    confidence: Mapped[dict[str, float]] = mapped_column(JSONB, nullable=False, default=dict)

    invoice: Mapped[Invoice] = relationship(back_populates="line_items")
