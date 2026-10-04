from app.features.validation.gstin import state_code_of, state_label
from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    FindingDraft,
    ValidationContext,
    ValidationRule,
    zero_if_none,
)


class TaxTypeRule(ValidationRule):
    """Intra-state supplies carry CGST + SGST; inter-state supplies carry IGST."""

    code = "tax_type"

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        inv = ctx.invoice
        vendor_state = state_code_of(inv.vendor_gstin)
        buyer_state = state_code_of(inv.buyer_gstin) or ctx.company_state_code
        if not vendor_state or not buyer_state:
            return []

        cgst, sgst, igst = zero_if_none(inv.cgst), zero_if_none(inv.sgst), zero_if_none(inv.igst)
        vendor, buyer = state_label(vendor_state), state_label(buyer_state)

        if vendor_state == buyer_state and igst > 0:
            return [
                self.finding(
                    Severity.ERROR,
                    f"Vendor and buyer are both in {vendor}, so this is an intra-state supply "
                    "and CGST + SGST should apply, but IGST was charged.",
                    "igst",
                )
            ]
        if vendor_state != buyer_state and (cgst > 0 or sgst > 0):
            return [
                self.finding(
                    Severity.ERROR,
                    f"Vendor ({vendor}) and buyer ({buyer}) are in different states, so IGST "
                    "should apply, but CGST/SGST was charged.",
                    "cgst",
                )
            ]
        return []
