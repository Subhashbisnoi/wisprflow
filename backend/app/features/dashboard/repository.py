from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.features.invoices.models import Invoice, InvoiceStatus
from app.features.vendors.models import Vendor

ACTIVE_STATUSES = (InvoiceStatus.NEEDS_REVIEW, InvoiceStatus.APPROVED)


@dataclass(frozen=True)
class MonthSpend:
    month: date
    approved: Decimal
    pending: Decimal


@dataclass(frozen=True)
class VendorSpend:
    vendor_id: str
    display_name: str
    amount: Decimal
    bill_count: int


class DashboardRepository:
    """Read-only aggregate queries, always scoped to the tenant."""

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        self.session = session
        self.tenant = tenant

    @property
    def _bill_date(self):  # type: ignore[no-untyped-def]
        # Bills without an extracted invoice date fall back to their upload date.
        return func.coalesce(Invoice.invoice_date, cast(Invoice.created_at, Date))

    def total_between(self, start: date, end: date) -> tuple[Decimal, int]:
        row = self.session.execute(
            select(func.coalesce(func.sum(Invoice.total), 0), func.count(Invoice.id)).where(
                Invoice.company_id == self.tenant.company_id,
                Invoice.status.in_(ACTIVE_STATUSES),
                self._bill_date >= start,
                self._bill_date < end,
            )
        ).one()
        return Decimal(row[0] or 0), int(row[1])

    def status_summary(self) -> dict[InvoiceStatus, tuple[int, Decimal]]:
        rows = self.session.execute(
            select(
                Invoice.status, func.count(Invoice.id), func.coalesce(func.sum(Invoice.total), 0)
            )
            .where(Invoice.company_id == self.tenant.company_id)
            .group_by(Invoice.status)
        ).all()
        return {r[0]: (int(r[1]), Decimal(r[2] or 0)) for r in rows}

    def decisions_between(self, start: datetime, end: datetime) -> tuple[int, int]:
        rows = self.session.execute(
            select(Invoice.status, func.count(Invoice.id))
            .where(
                Invoice.company_id == self.tenant.company_id,
                Invoice.status.in_([InvoiceStatus.APPROVED, InvoiceStatus.REJECTED]),
                Invoice.reviewed_at >= start,
                Invoice.reviewed_at < end,
            )
            .group_by(Invoice.status)
        ).all()
        counts = {r[0]: int(r[1]) for r in rows}
        return counts.get(InvoiceStatus.APPROVED, 0), counts.get(InvoiceStatus.REJECTED, 0)

    def monthly_spend(self, since: date) -> list[MonthSpend]:
        month = func.date_trunc("month", self._bill_date)
        rows = self.session.execute(
            select(
                month.label("month"),
                func.coalesce(
                    func.sum(Invoice.total).filter(Invoice.status == InvoiceStatus.APPROVED), 0
                ),
                func.coalesce(
                    func.sum(Invoice.total).filter(Invoice.status == InvoiceStatus.NEEDS_REVIEW),
                    0,
                ),
            )
            .where(
                Invoice.company_id == self.tenant.company_id,
                Invoice.status.in_(ACTIVE_STATUSES),
                self._bill_date >= since,
            )
            .group_by(month)
            .order_by(month)
        ).all()
        return [MonthSpend(r[0].date(), Decimal(r[1]), Decimal(r[2])) for r in rows]

    def top_vendors(self, since: date, limit: int = 5) -> list[VendorSpend]:
        amount = func.coalesce(func.sum(Invoice.total), 0)
        rows = self.session.execute(
            select(Vendor.id, Vendor.display_name, amount, func.count(Invoice.id))
            .join(Invoice, Invoice.vendor_id == Vendor.id)
            .where(
                Vendor.company_id == self.tenant.company_id,
                Invoice.company_id == self.tenant.company_id,
                Invoice.status.in_(ACTIVE_STATUSES),
                self._bill_date >= since,
            )
            .group_by(Vendor.id, Vendor.display_name)
            .order_by(amount.desc())
            .limit(limit)
        ).all()
        return [VendorSpend(str(r[0]), r[1], Decimal(r[2] or 0), int(r[3])) for r in rows]
