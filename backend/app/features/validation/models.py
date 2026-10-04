import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantMixin, UUIDPrimaryKeyMixin, str_enum


class Severity(enum.StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


class ValidationFinding(UUIDPrimaryKeyMixin, TenantMixin, Base):
    __tablename__ = "validation_findings"
    __table_args__ = (
        Index("ix_findings_company_invoice", "company_id", "invoice_id"),
        Index("ix_findings_company_severity", "company_id", "severity"),
    )

    invoice_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False
    )
    rule_code: Mapped[str] = mapped_column(String(50), nullable=False)
    severity: Mapped[Severity] = mapped_column(
        str_enum(Severity, "severity", length=10),
        nullable=False,
    )
    field: Mapped[str | None] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
