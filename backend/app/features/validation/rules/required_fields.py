from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    FIELD_LABELS,
    FindingDraft,
    ValidationContext,
    ValidationRule,
)

REQUIRED = ("vendor_name", "vendor_gstin", "invoice_number", "invoice_date", "total")
RECOMMENDED = ("buyer_gstin", "due_date")


class RequiredFieldsRule(ValidationRule):
    code = "required_fields"

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        inv = ctx.invoice
        findings: list[FindingDraft] = []
        for name in REQUIRED:
            if getattr(inv, name) in (None, ""):
                findings.append(
                    self.finding(
                        Severity.ERROR,
                        f"{FIELD_LABELS[name]} is missing. Enter it from the document before "
                        "approving.",
                        name,
                    )
                )
        for name in RECOMMENDED:
            if getattr(inv, name) in (None, ""):
                findings.append(
                    self.finding(
                        Severity.WARNING,
                        f"{FIELD_LABELS[name]} was not found on the invoice. Add it if the "
                        "document shows one.",
                        name,
                    )
                )
        if not inv.lines:
            findings.append(
                self.finding(
                    Severity.WARNING,
                    "No line items were found. Line-level checks were skipped.",
                    "line_items",
                )
            )
        return findings
