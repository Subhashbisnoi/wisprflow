from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def format_inr(amount: Decimal | None) -> str:
    """Format as Indian rupees with lakh grouping, e.g. 1234567.5 -> '₹12,34,567.50'."""
    if amount is None:
        return "-"
    quantized = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    sign = "-" if quantized < 0 else ""
    whole, frac = f"{abs(quantized):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups: list[str] = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join([*groups, tail])
    return f"{sign}₹{whole}.{frac}"


def format_date(value: date | None) -> str:
    return value.strftime("%d %b %Y") if value else "-"
