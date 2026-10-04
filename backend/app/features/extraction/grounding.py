"""Confidence grounding against the PDF text layer (D-053).

A value that literally appears in the text layer is almost certainly right (the text layer is
exact); a value that does not appear was inferred or misread by the model.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.features.extraction.normalizer import NormalizedInvoice

GROUNDED_FLOOR = 0.95
UNGROUNDED_CAP = 0.70
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers_in(text: str) -> set[Decimal]:
    numbers: set[Decimal] = set()
    for match in _NUMBER.findall(text):
        try:
            numbers.add(Decimal(match.replace(",", "")).normalize())
        except InvalidOperation:
            continue
    return numbers


def _date_renderings(value: date) -> set[str]:
    d, m, y = value.day, value.month, value.year
    out = set()
    for day in {f"{d:02d}", str(d)}:
        for month in {f"{m:02d}", str(m)}:
            for year in (str(y), f"{y % 100:02d}"):
                for sep in ("/", "-", "."):
                    out.add(f"{day}{sep}{month}{sep}{year}")
        for mon in (value.strftime("%b"), value.strftime("%B")):
            for sep in ("-", " ", "/"):
                out.add(f"{day}{sep}{mon}{sep}{y}".lower())
                out.add(f"{day}{sep}{mon}{sep}{y % 100:02d}".lower())
            out.add(f"{mon} {day}, {y}".lower())
    out.add(value.isoformat())
    return out


class ConfidenceGrounder:
    def ground(self, invoice: NormalizedInvoice, text: str) -> NormalizedInvoice:
        lowered = " ".join(text.lower().split())
        compact = re.sub(r"\s", "", text.upper())
        numbers = _numbers_in(text)

        def present(value: object) -> bool:
            if isinstance(value, Decimal):
                return value.normalize() in numbers
            if isinstance(value, date):
                return any(r in lowered for r in _date_renderings(value))
            if isinstance(value, str):
                return (
                    " ".join(value.lower().split()) in lowered
                    or re.sub(r"\s", "", value.upper()) in compact
                )
            return False

        def adjust(confidence: float, value: object) -> float:
            if value is None:
                return confidence
            return (
                max(confidence, GROUNDED_FLOOR)
                if present(value)
                else min(confidence, UNGROUNDED_CAP)
            )

        for name, value in invoice.values.items():
            invoice.confidence[name] = adjust(invoice.confidence.get(name, 0.0), value)
        for line in invoice.lines:
            for name in ("description", "quantity", "rate", "amount"):
                line.confidence[name] = adjust(line.confidence.get(name, 0.0), getattr(line, name))
        return invoice
