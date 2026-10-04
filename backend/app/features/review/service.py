import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import (
    ApprovalBlockedError,
    InvalidStateError,
    NotFoundError,
    VersionConflictError,
)
from app.core.tenant import TenantContext
from app.features.audit.models import AuditAction
from app.features.audit.service import AuditService
from app.features.invoices.models import Invoice, InvoiceLineItem, InvoiceStatus
from app.features.invoices.repository import InvoiceRepository
from app.features.review.field_parser import parse_field_value
from app.features.review.schemas import FieldChange, LineFieldChange, LineItemCreateRequest
from app.features.validation.service import ValidationService
from app.features.vendors.matching import VendorMatchingService

logger = logging.getLogger("app.review")

HUMAN_VERIFIED = 1.0


class ReviewService:
    def __init__(
        self,
        session: Session,
        invoices: InvoiceRepository,
        validation: ValidationService,
        vendor_matching: VendorMatchingService,
        audit: AuditService,
        tenant: TenantContext,
    ) -> None:
        self._session = session
        self._invoices = invoices
        self._validation = validation
        self._vendor_matching = vendor_matching
        self._audit = audit
        self._tenant = tenant

    # --- Header fields -----------------------------------------------------------------------

    def correct_fields(
        self, invoice_id: uuid.UUID, version: int, changes: list[FieldChange]
    ) -> Invoice:
        invoice = self._lock_editable(invoice_id, version)
        parsed = [(c.field, parse_field_value(c.field, c.value)) for c in changes]

        changed_fields: list[str] = []
        confidence = dict(invoice.field_confidence or {})
        for field, new_value in parsed:
            old_value = getattr(invoice, field)
            if old_value == new_value:
                continue
            setattr(invoice, field, new_value)
            confidence[field] = HUMAN_VERIFIED
            changed_fields.append(field)
            self._audit.record(
                AuditAction.FIELD_CORRECTED,
                entity_type="invoice",
                entity_id=invoice.id,
                invoice_id=invoice.id,
                field_name=field,
                old_value=old_value,
                new_value=new_value,
            )
        if not changed_fields:
            self._session.rollback()
            return self._invoices.get_or_raise(invoice_id)

        invoice.field_confidence = confidence
        if "vendor_gstin" in changed_fields or (
            "vendor_name" in changed_fields and invoice.vendor_id is None
        ):
            self._vendor_matching.match(invoice)
        return self._revalidate_and_commit(invoice)

    # --- Line items --------------------------------------------------------------------------

    def add_line_item(
        self, invoice_id: uuid.UUID, version: int, data: LineItemCreateRequest
    ) -> Invoice:
        invoice = self._lock_editable(invoice_id, version)
        values = {
            name: parse_field_value(name, getattr(data, name), line=True)
            for name in ("description", "hsn_sac", "quantity", "rate", "amount")
        }
        position = max((li.position for li in invoice.line_items), default=0) + 1
        item = InvoiceLineItem(
            company_id=invoice.company_id,
            position=position,
            confidence={k: HUMAN_VERIFIED for k, v in values.items() if v is not None},
            **values,
        )
        invoice.line_items.append(item)
        self._session.flush()
        self._audit.record(
            AuditAction.LINE_ITEM_ADDED,
            entity_type="line_item",
            entity_id=item.id,
            invoice_id=invoice.id,
            field_name=f"line {position}",
            new_value=item.description,
            details={k: str(v) for k, v in values.items() if v is not None},
        )
        return self._revalidate_and_commit(invoice)

    def correct_line_item(
        self,
        invoice_id: uuid.UUID,
        item_id: uuid.UUID,
        version: int,
        changes: list[LineFieldChange],
    ) -> Invoice:
        invoice = self._lock_editable(invoice_id, version)
        item = self._find_line(invoice, item_id)
        confidence = dict(item.confidence or {})
        changed = False
        for change in changes:
            new_value = parse_field_value(change.field, change.value, line=True)
            old_value = getattr(item, change.field)
            if old_value == new_value:
                continue
            setattr(item, change.field, new_value)
            confidence[change.field] = HUMAN_VERIFIED
            changed = True
            self._audit.record(
                AuditAction.LINE_ITEM_CORRECTED,
                entity_type="line_item",
                entity_id=item.id,
                invoice_id=invoice.id,
                field_name=f"line {item.position} {change.field}",
                old_value=old_value,
                new_value=new_value,
            )
        if not changed:
            self._session.rollback()
            return self._invoices.get_or_raise(invoice_id)
        item.confidence = confidence
        return self._revalidate_and_commit(invoice)

    def remove_line_item(self, invoice_id: uuid.UUID, item_id: uuid.UUID, version: int) -> Invoice:
        invoice = self._lock_editable(invoice_id, version)
        item = self._find_line(invoice, item_id)
        self._audit.record(
            AuditAction.LINE_ITEM_REMOVED,
            entity_type="line_item",
            entity_id=item.id,
            invoice_id=invoice.id,
            field_name=f"line {item.position}",
            old_value=item.description,
            details={"amount": str(item.amount) if item.amount is not None else None},
        )
        invoice.line_items.remove(item)
        for position, line in enumerate(sorted(invoice.line_items, key=lambda li: li.position), 1):
            line.position = position
        return self._revalidate_and_commit(invoice)

    # --- Decisions ---------------------------------------------------------------------------

    def approve(self, invoice_id: uuid.UUID, version: int, comment: str | None) -> Invoice:
        invoice = self._lock_editable(invoice_id, version)
        # Re-check at decision time: another bill may have become a duplicate since.
        self._validation.validate(invoice)
        if invoice.error_count > 0:
            self._session.commit()  # persist the refreshed findings; version unchanged
            noun = "error" if invoice.error_count == 1 else "errors"
            raise ApprovalBlockedError(
                f"This bill has {invoice.error_count} {noun}. Correct the data or reject the bill."
            )
        invoice.status = InvoiceStatus.APPROVED
        invoice.review_comment = (comment or "").strip() or None
        self._decide(invoice, AuditAction.INVOICE_APPROVED, invoice.review_comment)
        return self._invoices.get_or_raise(invoice_id)

    def reject(self, invoice_id: uuid.UUID, version: int, reason: str) -> Invoice:
        invoice = self._lock_editable(invoice_id, version)
        invoice.status = InvoiceStatus.REJECTED
        invoice.rejection_reason = reason
        self._decide(invoice, AuditAction.INVOICE_REJECTED, reason)
        return self._invoices.get_or_raise(invoice_id)

    # --- Helpers -----------------------------------------------------------------------------

    def _decide(self, invoice: Invoice, action: AuditAction, note: str | None) -> None:
        invoice.reviewed_by_id = self._tenant.user_id
        invoice.reviewed_at = datetime.now(UTC)
        invoice.version += 1
        self._audit.record(
            action,
            entity_type="invoice",
            entity_id=invoice.id,
            invoice_id=invoice.id,
            field_name="status",
            old_value=InvoiceStatus.NEEDS_REVIEW.value,
            new_value=invoice.status.value,
            details={"note": note} if note else {},
        )
        self._session.commit()
        logger.info(
            "invoice decided", extra={"invoice_id": str(invoice.id), "status": invoice.status}
        )

    def _lock_editable(self, invoice_id: uuid.UUID, version: int) -> Invoice:
        invoice = self._invoices.get_for_update(invoice_id)
        if invoice is None:
            raise NotFoundError("Bill not found.")
        if not invoice.is_editable():
            self._session.rollback()
            label = invoice.status.value.replace("_", " ")
            raise InvalidStateError(
                f"This bill is {label} and can no longer be changed.",
                details={"status": invoice.status.value, "current_version": invoice.version},
            )
        if invoice.version != version:
            current = invoice.version
            self._session.rollback()
            raise VersionConflictError(details={"current_version": current})
        return invoice

    @staticmethod
    def _find_line(invoice: Invoice, item_id: uuid.UUID) -> InvoiceLineItem:
        for item in invoice.line_items:
            if item.id == item_id:
                return item
        raise NotFoundError("Line item not found.")

    def _revalidate_and_commit(self, invoice: Invoice) -> Invoice:
        self._validation.validate(invoice)
        invoice.version += 1
        self._session.commit()
        return self._invoices.get_or_raise(invoice.id)
