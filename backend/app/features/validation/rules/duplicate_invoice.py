import uuid
from decimal import Decimal

from app.core.formatting import format_date, format_inr
from app.features.validation.gstin import normalize_gstin
from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    DuplicateMatch,
    FindingDraft,
    ValidationContext,
    ValidationRule,
)


def _status_label(status: str) -> str:
    return status.replace("_", " ").capitalize()


class DuplicateInvoiceRule(ValidationRule):
    """Same file (SHA-256), or same vendor GSTIN + invoice number + total (D-027)."""

    code = "duplicate_invoice"

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        inv = ctx.invoice
        findings: list[FindingDraft] = []
        reported: set[uuid.UUID] = set()

        if inv.file_sha256:
            for match in ctx.duplicates.find_by_sha256(inv.file_sha256, inv.id)[:3]:
                reported.add(match.id)
                findings.append(
                    self.finding(
                        Severity.ERROR,
                        f"This exact file was already uploaded on {format_date(match.created_at)} "
                        f"as '{match.original_filename}' (status: {_status_label(match.status)}). "
                        "Reject this copy unless it is a genuinely separate bill.",
                        None,
                    )
                )

        vendor_gstin = normalize_gstin(inv.vendor_gstin)
        if vendor_gstin and inv.invoice_number and inv.total is not None:
            matches = ctx.duplicates.find_duplicates(
                vendor_gstin, inv.invoice_number, inv.total, inv.id
            )
            for match in [m for m in matches if m.id not in reported][:3]:
                findings.append(self._field_duplicate(match, inv.total))
        return findings

    def _field_duplicate(self, match: DuplicateMatch, total: Decimal) -> FindingDraft:
        vendor = f" from {match.vendor_name}" if match.vendor_name else ""
        amount = format_inr(total)
        return self.finding(
            Severity.ERROR,
            f"This looks like a duplicate of invoice {match.invoice_number}{vendor} for {amount}, "
            f"uploaded on {format_date(match.created_at)} (status: "
            f"{_status_label(match.status)}). Reject it unless this is a genuinely separate bill.",
            "invoice_number",
        )
