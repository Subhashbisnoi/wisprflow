from decimal import Decimal

from app.core.formatting import format_inr
from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    AMOUNT_TOLERANCE,
    FindingDraft,
    ValidationContext,
    ValidationRule,
    zero_if_none,
)

# Pre- and post-GST 2.0 slabs (D-028).
GST_SLABS: tuple[Decimal, ...] = tuple(
    Decimal(s) for s in ("0", "0.25", "3", "5", "12", "18", "28", "40")
)
RATE_TOLERANCE_PP = Decimal("0.1")


class TaxRateRule(ValidationRule):
    """CGST must equal SGST, and the effective tax rate must match a GST slab."""

    code = "tax_rate"

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        inv = ctx.invoice
        findings: list[FindingDraft] = []
        cgst, sgst, igst = zero_if_none(inv.cgst), zero_if_none(inv.sgst), zero_if_none(inv.igst)

        if (cgst > 0 or sgst > 0) and abs(cgst - sgst) > AMOUNT_TOLERANCE:
            findings.append(
                self.finding(
                    Severity.ERROR,
                    f"CGST ({format_inr(cgst)}) and SGST ({format_inr(sgst)}) should be equal; "
                    "each is half of the GST rate on an intra-state supply.",
                    "sgst",
                )
            )

        tax = cgst + sgst + igst
        if inv.subtotal is None or inv.subtotal <= 0 or tax <= 0:
            return findings

        rate = tax / inv.subtotal * 100
        nearest = min(GST_SLABS, key=lambda slab: abs(slab - rate))
        expected_tax = inv.subtotal * nearest / 100
        within_rate = abs(rate - nearest) <= RATE_TOLERANCE_PP
        within_amount = abs(expected_tax - tax) <= AMOUNT_TOLERANCE
        if not (within_rate or within_amount):
            slabs = ", ".join(f"{s.normalize():f}" for s in GST_SLABS)
            findings.append(
                self.finding(
                    Severity.WARNING,
                    f"Total tax ({format_inr(tax)}) is {rate:.2f}% of the subtotal, which is not "
                    f"a standard GST rate ({slabs}%). The closest is {nearest.normalize():f}% "
                    f"({format_inr(expected_tax)}). Check the tax amounts, unless items carry "
                    "different rates.",
                    "cgst" if igst == 0 else "igst",
                )
            )
        return findings
