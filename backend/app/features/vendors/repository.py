import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, or_, select

from app.core.pagination import Page, PageParams
from app.core.tenant import TenantRepository
from app.features.invoices.models import Invoice, InvoiceStatus
from app.features.invoices.repository import escape_like
from app.features.vendors.models import Vendor


@dataclass(frozen=True)
class VendorRow:
    vendor: Vendor
    bill_count: int
    approved_spend: Decimal
    pending_amount: Decimal


class VendorRepository(TenantRepository[Vendor]):
    model = Vendor
    not_found_message = "Vendor not found."

    def get_by_gstin(self, gstin: str) -> Vendor | None:
        return self.session.scalars(self.scoped().where(Vendor.gstin == gstin)).first()

    def list_with_stats(self, search: str | None, params: PageParams) -> Page[VendorRow]:
        stats = (
            select(
                Invoice.vendor_id.label("vendor_id"),
                func.count(Invoice.id).label("bill_count"),
                func.coalesce(
                    func.sum(case((Invoice.status == InvoiceStatus.APPROVED, Invoice.total))), 0
                ).label("approved_spend"),
                func.coalesce(
                    func.sum(case((Invoice.status == InvoiceStatus.NEEDS_REVIEW, Invoice.total))),
                    0,
                ).label("pending_amount"),
            )
            .where(Invoice.company_id == self.tenant.company_id, Invoice.vendor_id.is_not(None))
            .group_by(Invoice.vendor_id)
            .subquery()
        )
        base = (
            select(
                Vendor,
                func.coalesce(stats.c.bill_count, 0),
                func.coalesce(stats.c.approved_spend, 0),
                func.coalesce(stats.c.pending_amount, 0),
            )
            .outerjoin(stats, stats.c.vendor_id == Vendor.id)
            .where(Vendor.company_id == self.tenant.company_id)
        )
        if search:
            term = f"%{escape_like(search.strip())}%"
            base = base.where(
                or_(
                    Vendor.display_name.ilike(term, escape="\\"),
                    Vendor.legal_name.ilike(term, escape="\\"),
                    Vendor.gstin.ilike(term, escape="\\"),
                )
            )
        total = self.session.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = self.session.execute(
            base.order_by(Vendor.display_name, Vendor.id)
            .limit(params.page_size)
            .offset(params.offset)
        ).all()
        items = [
            VendorRow(vendor=r[0], bill_count=int(r[1]), approved_spend=r[2], pending_amount=r[3])
            for r in rows
        ]
        return Page(items=items, page=params.page, page_size=params.page_size, total=total)

    def stats_for(self, vendor_id: uuid.UUID) -> VendorRow:
        vendor = self.get_or_raise(vendor_id)
        row = self.session.execute(
            select(
                func.count(Invoice.id),
                func.coalesce(
                    func.sum(case((Invoice.status == InvoiceStatus.APPROVED, Invoice.total))), 0
                ),
                func.coalesce(
                    func.sum(case((Invoice.status == InvoiceStatus.NEEDS_REVIEW, Invoice.total))),
                    0,
                ),
            ).where(Invoice.company_id == self.tenant.company_id, Invoice.vendor_id == vendor_id)
        ).one()
        return VendorRow(
            vendor=vendor, bill_count=int(row[0]), approved_spend=row[1], pending_amount=row[2]
        )
