import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.features.audit.models import AuditAction
from app.features.audit.service import AuditService
from app.features.invoices.models import Invoice
from app.features.validation.gstin import is_valid_gstin, normalize_gstin
from app.features.vendors.models import Vendor
from app.features.vendors.repository import VendorRepository

logger = logging.getLogger("app.vendors")


@dataclass(frozen=True)
class MatchResult:
    vendor: Vendor | None
    created: bool = False


class VendorMatchingService:
    """Links an invoice to a vendor by GSTIN, creating the vendor on first sight (D-023)."""

    def __init__(self, vendors: VendorRepository, audit: AuditService) -> None:
        self._vendors = vendors
        self._audit = audit

    def match(self, invoice: Invoice) -> MatchResult:
        gstin = normalize_gstin(invoice.vendor_gstin)
        if not gstin or not is_valid_gstin(gstin):
            self._link(invoice, None)
            return MatchResult(None)

        vendor = self._vendors.get_by_gstin(gstin)
        created = False
        if vendor is None:
            vendor, created = self._create(invoice, gstin)
        self._link(invoice, vendor)
        return MatchResult(vendor, created)

    def _create(self, invoice: Invoice, gstin: str) -> tuple[Vendor, bool]:
        name = (invoice.vendor_name or "").strip() or f"Vendor {gstin}"
        session = self._vendors.session
        try:
            # Savepoint: a concurrent extraction may create the same vendor first.
            with session.begin_nested():
                vendor = self._vendors.add(
                    Vendor(gstin=gstin, legal_name=name, display_name=name, state_code=gstin[:2])
                )
                session.flush()
        except IntegrityError:
            existing = self._vendors.get_by_gstin(gstin)
            if existing is None:
                raise
            return existing, False

        self._audit.record(
            AuditAction.VENDOR_CREATED,
            entity_type="vendor",
            entity_id=vendor.id,
            invoice_id=invoice.id,
            new_value=vendor.display_name,
            details={"gstin": gstin, "source": "invoice"},
        )
        logger.info("vendor auto-created", extra={"vendor_id": str(vendor.id)})
        return vendor, True

    def _link(self, invoice: Invoice, vendor: Vendor | None) -> None:
        new_id = vendor.id if vendor else None
        if invoice.vendor_id == new_id:
            return
        old_name = invoice.vendor.display_name if invoice.vendor else None
        invoice.vendor_id = new_id
        invoice.vendor = vendor
        self._audit.record(
            AuditAction.VENDOR_LINKED,
            entity_type="invoice",
            entity_id=invoice.id,
            invoice_id=invoice.id,
            field_name="vendor",
            old_value=old_name,
            new_value=vendor.display_name if vendor else None,
        )
