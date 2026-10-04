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


class TotalsRule(ValidationRule):
    """subtotal + CGST + SGST + IGST = total, allowing a rupee of round-off (D-029)."""

    code = "totals"

    def __init__(self, tolerance: Decimal = AMOUNT_TOLERANCE) -> None:
        self.tolerance = tolerance

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        inv = ctx.invoice
        if inv.subtotal is None or inv.total is None:
            return []
        computed = inv.subtotal + zero_if_none(inv.cgst) + zero_if_none(inv.sgst)
        computed += zero_if_none(inv.igst)
        difference = inv.total - computed
        if difference == 0:
            return []
        if abs(difference) <= self.tolerance:
            return [
                self.finding(
                    Severity.INFO,
                    f"Total differs from subtotal plus tax by {format_inr(abs(difference))}, "
                    "which looks like normal round-off.",
                    "total",
                )
            ]
        return [
            self.finding(
                Severity.ERROR,
                f"Subtotal plus tax comes to {format_inr(computed)}, but the invoice total is "
                f"{format_inr(inv.total)} (difference {format_inr(abs(difference))}).",
                "total",
            )
        ]
