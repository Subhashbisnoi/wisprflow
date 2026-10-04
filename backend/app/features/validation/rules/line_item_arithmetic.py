from decimal import Decimal

from app.core.formatting import format_inr
from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    AMOUNT_TOLERANCE,
    FindingDraft,
    ValidationContext,
    ValidationRule,
)


def _fmt_qty(qty: Decimal) -> str:
    return f"{qty.normalize():f}"


class LineItemArithmeticRule(ValidationRule):
    """Each line: quantity x rate = amount. All lines: sum of amounts = subtotal."""

    code = "line_item_arithmetic"

    def __init__(self, tolerance: Decimal = AMOUNT_TOLERANCE) -> None:
        self.tolerance = tolerance

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        inv = ctx.invoice
        findings: list[FindingDraft] = []

        for line in inv.lines:
            if line.quantity is None or line.rate is None or line.amount is None:
                continue
            expected = line.quantity * line.rate
            if abs(expected - line.amount) > self.tolerance:
                findings.append(
                    self.finding(
                        Severity.ERROR,
                        f"Line {line.position}: quantity {_fmt_qty(line.quantity)} x rate "
                        f"{format_inr(line.rate)} = {format_inr(expected)}, but the amount says "
                        f"{format_inr(line.amount)}.",
                        f"line_items.{line.position}.amount",
                    )
                )

        amounts = [line.amount for line in inv.lines]
        if inv.lines and inv.subtotal is not None and all(a is not None for a in amounts):
            line_sum = sum((a for a in amounts if a is not None), Decimal("0"))
            difference = line_sum - inv.subtotal
            if abs(difference) > self.tolerance:
                findings.append(
                    self.finding(
                        Severity.ERROR,
                        f"Line items add up to {format_inr(line_sum)} but the subtotal says "
                        f"{format_inr(inv.subtotal)} (difference {format_inr(abs(difference))}). "
                        "A line may be missing or misread.",
                        "subtotal",
                    )
                )
        return findings
