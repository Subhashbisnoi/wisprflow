from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Vendor(UUIDPrimaryKeyMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("company_id", "gstin", name="uq_vendors_company_gstin"),
        Index("ix_vendors_company_display_name", "company_id", "display_name"),
    )

    gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str] = mapped_column(String(300), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
