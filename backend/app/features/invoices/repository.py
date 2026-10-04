import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy import Select, and_, or_, select

from app.core.pagination import Page, PageParams, paginate
from app.core.tenant import TenantRepository
from app.features.invoices.models import Invoice, InvoiceLineItem, InvoiceStatus
from app.features.validation.rules.base import DuplicateMatch
from app.features.vendors.models import Vendor

SORTABLE_COLUMNS = {
    "created_at": Invoice.created_at,
    "invoice_date": Invoice.invoice_date,
    "due_date": Invoice.due_date,
    "total": Invoice.total,
    "vendor_name": Invoice.vendor_name,
    "invoice_number": Invoice.invoice_number,
    "status": Invoice.status,
}


@dataclass(frozen=True)
class InvoiceFilters:
    statuses: Sequence[InvoiceStatus] = ()
    vendor_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    min_total: Decimal | None = None
    max_total: Decimal | None = None
    search: str | None = None
    ids: Sequence[uuid.UUID] = field(default_factory=tuple)
    sort: str = "-created_at"


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class InvoiceRepository(TenantRepository[Invoice]):
    model = Invoice
    not_found_message = "Bill not found."

    def get_for_update(self, invoice_id: uuid.UUID) -> Invoice | None:
        """Row-lock the invoice for the rest of the transaction (review writes, D-047)."""
        stmt = (
            self.scoped()
            .where(Invoice.id == invoice_id)
            .with_for_update(of=Invoice)
            .execution_options(populate_existing=True)
        )
        return self.session.scalars(stmt).first()

    def search(self, filters: InvoiceFilters, params: PageParams) -> Page[Invoice]:
        return paginate(self.session, self._filtered(filters), params)

    def _filtered(self, f: InvoiceFilters) -> Select[Invoice]:
        stmt = self.scoped()
        if f.statuses:
            stmt = stmt.where(Invoice.status.in_(list(f.statuses)))
        if f.ids:
            stmt = stmt.where(Invoice.id.in_(list(f.ids)))
        if f.vendor_id:
            stmt = stmt.where(Invoice.vendor_id == f.vendor_id)
        if f.date_from:
            stmt = stmt.where(Invoice.invoice_date >= f.date_from)
        if f.date_to:
            stmt = stmt.where(Invoice.invoice_date <= f.date_to)
        if f.min_total is not None:
            stmt = stmt.where(Invoice.total >= f.min_total)
        if f.max_total is not None:
            stmt = stmt.where(Invoice.total <= f.max_total)
        if f.search:
            term = f"%{escape_like(f.search.strip())}%"
            vendor_match = (
                select(Vendor.id)
                .where(Vendor.company_id == self.tenant.company_id)
                .where(Vendor.display_name.ilike(term, escape="\\"))
            )
            stmt = stmt.where(
                or_(
                    Invoice.invoice_number.ilike(term, escape="\\"),
                    Invoice.vendor_name.ilike(term, escape="\\"),
                    Invoice.original_filename.ilike(term, escape="\\"),
                    Invoice.vendor_gstin.ilike(term, escape="\\"),
                    Invoice.vendor_id.in_(vendor_match),
                )
            )
        descending = f.sort.startswith("-")
        column = SORTABLE_COLUMNS.get(f.sort.lstrip("-"), Invoice.created_at)
        order = column.desc().nulls_last() if descending else column.asc().nulls_last()
        return stmt.order_by(order, Invoice.id)

    def list_ids_by_status(self, statuses: Sequence[InvoiceStatus]) -> list[uuid.UUID]:
        stmt = select(Invoice.id).where(
            Invoice.company_id == self.tenant.company_id, Invoice.status.in_(list(statuses))
        )
        return list(self.session.scalars(stmt).all())

    # --- DuplicateLookup port (used by DuplicateInvoiceRule) -------------------------------

    def _earlier_than(self, invoice_id: uuid.UUID) -> Select[Invoice]:
        """Only uploads that came before this one count as originals, so the first copy is
        never flagged and the later copy always is."""
        mine = select(Invoice.created_at).where(Invoice.id == invoice_id).scalar_subquery()
        return self.scoped().where(
            Invoice.id != invoice_id,
            Invoice.status.not_in([InvoiceStatus.REJECTED, InvoiceStatus.FAILED]),
            or_(
                Invoice.created_at < mine, and_(Invoice.created_at == mine, Invoice.id < invoice_id)
            ),
        )

    @staticmethod
    def _to_match(invoice: Invoice) -> DuplicateMatch:
        return DuplicateMatch(
            id=invoice.id,
            invoice_number=invoice.invoice_number,
            vendor_name=invoice.vendor.display_name if invoice.vendor else invoice.vendor_name,
            original_filename=invoice.original_filename,
            status=invoice.status.value,
            created_at=invoice.created_at,
        )

    def find_duplicates(
        self, vendor_gstin: str, invoice_number: str, total: Decimal, exclude_id: uuid.UUID
    ) -> list[DuplicateMatch]:
        stmt = (
            self._earlier_than(exclude_id)
            .where(
                Invoice.vendor_gstin == vendor_gstin,
                Invoice.invoice_number.ilike(escape_like(invoice_number.strip()), escape="\\"),
                Invoice.total == total,
            )
            .order_by(Invoice.created_at)
        )
        return [self._to_match(i) for i in self.session.scalars(stmt).unique().all()]

    def find_by_sha256(self, sha256: str, exclude_id: uuid.UUID) -> list[DuplicateMatch]:
        stmt = (
            self._earlier_than(exclude_id)
            .where(Invoice.file_sha256 == sha256)
            .order_by(Invoice.created_at)
        )
        return [self._to_match(i) for i in self.session.scalars(stmt).unique().all()]


class LineItemRepository(TenantRepository[InvoiceLineItem]):
    model = InvoiceLineItem
    not_found_message = "Line item not found."

    def get_for_invoice(self, invoice_id: uuid.UUID, item_id: uuid.UUID) -> InvoiceLineItem | None:
        stmt = self.scoped().where(
            InvoiceLineItem.invoice_id == invoice_id, InvoiceLineItem.id == item_id
        )
        return self.session.scalars(stmt).first()
