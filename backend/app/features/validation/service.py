import logging

from app.core.tenant import TenantContext
from app.features.auth.repository import CompanyRepository
from app.features.invoices.models import Invoice
from app.features.validation.engine import ValidationEngine
from app.features.validation.models import Severity, ValidationFinding
from app.features.validation.rules.base import (
    DuplicateLookup,
    InvoiceSnapshot,
    LineSnapshot,
    ValidationContext,
)

logger = logging.getLogger("app.validation")


def snapshot_of(invoice: Invoice) -> InvoiceSnapshot:
    return InvoiceSnapshot(
        id=invoice.id,
        vendor_name=invoice.vendor_name,
        vendor_gstin=invoice.vendor_gstin,
        buyer_gstin=invoice.buyer_gstin,
        invoice_number=invoice.invoice_number,
        invoice_date=invoice.invoice_date,
        due_date=invoice.due_date,
        subtotal=invoice.subtotal,
        cgst=invoice.cgst,
        sgst=invoice.sgst,
        igst=invoice.igst,
        total=invoice.total,
        lines=tuple(
            LineSnapshot(
                position=line.position,
                description=line.description,
                quantity=line.quantity,
                rate=line.rate,
                amount=line.amount,
            )
            for line in sorted(invoice.line_items, key=lambda li: li.position)
        ),
        field_confidence=dict(invoice.field_confidence or {}),
        file_sha256=invoice.file_sha256,
    )


class ValidationService:
    """Runs the engine and replaces the invoice's findings. The caller commits."""

    def __init__(
        self,
        engine: ValidationEngine,
        duplicates: DuplicateLookup,
        companies: CompanyRepository,
        tenant: TenantContext,
    ) -> None:
        self._engine = engine
        self._duplicates = duplicates
        self._companies = companies
        self._tenant = tenant

    def validate(self, invoice: Invoice) -> list[ValidationFinding]:
        self._companies.session.flush()  # rules (duplicates) must see pending changes
        company = self._companies.get(self._tenant.company_id)
        ctx = ValidationContext(
            invoice=snapshot_of(invoice),
            company_gstin=company.gstin if company else None,
            company_state_code=company.state_code if company else None,
            duplicates=self._duplicates,
        )
        drafts = self._engine.evaluate(ctx)
        findings = [
            ValidationFinding(
                company_id=self._tenant.company_id,
                rule_code=d.rule_code,
                severity=d.severity,
                field=d.field,
                message=d.message,
            )
            for d in drafts
        ]
        invoice.findings = findings  # delete-orphan cascade removes the previous run
        invoice.error_count = sum(1 for f in findings if f.severity == Severity.ERROR)
        invoice.warning_count = sum(1 for f in findings if f.severity == Severity.WARNING)
        logger.info(
            "invoice validated",
            extra={
                "invoice_id": str(invoice.id),
                "errors": invoice.error_count,
                "warnings": invoice.warning_count,
            },
        )
        return findings
