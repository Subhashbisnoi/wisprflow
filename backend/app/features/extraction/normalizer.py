"""Turns raw string values from the provider into typed, clean values."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.features.extraction.schemas import HEADER_FIELDS, ExtractedField, ExtractedInvoice
from app.features.validation.gstin import normalize_gstin

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d-%b-%Y",
    "%d-%b-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%d-%B-%Y",
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b, %Y",
)
_CURRENCY_TOKENS = re.compile(r"(₹|rs\.?|inr|\s)", re.IGNORECASE)
_ORDINAL = re.compile(r"(\d+)(st|nd|rd|th)\b", re.IGNORECASE)

MONEY_FIELDS = ("subtotal", "cgst", "sgst", "igst", "total")
DATE_FIELDS = ("invoice_date", "due_date")
MAX_LENGTHS = {"vendor_name": 300, "invoice_number": 100, "vendor_gstin": 32, "buyer_gstin": 32}


def parse_amount(raw: str | None, places: str = "0.01") -> Decimal | None:
    if raw is None:
        return None
    text = _CURRENCY_TOKENS.sub("", raw).replace(",", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()")
    if text.endswith("-"):  # "1,000.00-" style negatives
        negative, text = True, text[:-1]
    try:
        value = Decimal(text)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    value = value.quantize(Decimal(places), rounding=ROUND_HALF_UP)
    return -value if negative else value


def parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    text = _ORDINAL.sub(r"\1", raw.strip()).replace("  ", " ")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def clamp_confidence(value: float) -> float:
    return round(max(0.0, min(1.0, float(value))), 3)


@dataclass
class NormalizedLine:
    position: int
    description: str | None
    hsn_sac: str | None
    quantity: Decimal | None
    rate: Decimal | None
    amount: Decimal | None
    confidence: dict[str, float] = field(default_factory=dict)


@dataclass
class NormalizedInvoice:
    values: dict[str, str | date | Decimal | None]
    confidence: dict[str, float]
    lines: list[NormalizedLine]
    currency: str = "INR"
    unparsed: dict[str, str] = field(default_factory=dict)


class InvoiceNormalizer:
    def normalize(self, extracted: ExtractedInvoice) -> NormalizedInvoice:
        values: dict[str, str | date | Decimal | None] = {}
        confidence: dict[str, float] = {}
        unparsed: dict[str, str] = {}

        for name in HEADER_FIELDS:
            raw_field: ExtractedField = getattr(extracted, name)
            raw = raw_field.value.strip() if raw_field.value else None
            parsed = self._parse_header(name, raw)
            if raw and parsed is None:
                unparsed[name] = raw
            values[name] = parsed
            confidence[name] = clamp_confidence(raw_field.confidence) if parsed is not None else 0.0

        lines = []
        for position, item in enumerate(extracted.line_items, start=1):
            description = _clean_text(item.description.value)
            hsn = _clean_text(item.hsn_sac.value, 20)
            line = NormalizedLine(
                position=position,
                description=description,
                hsn_sac=hsn,
                quantity=parse_amount(item.quantity.value, "0.001"),
                rate=parse_amount(item.rate.value),
                amount=parse_amount(item.amount.value),
                confidence={
                    k: clamp_confidence(getattr(item, k).confidence)
                    for k in ("description", "hsn_sac", "quantity", "rate", "amount")
                },
            )
            if any(v is not None for v in (description, line.quantity, line.rate, line.amount)):
                lines.append(line)
        for index, line in enumerate(lines, start=1):
            line.position = index

        currency = (extracted.currency.value or "INR").strip().upper()[:3] or "INR"
        return NormalizedInvoice(values, confidence, lines, currency, unparsed)

    def _parse_header(self, name: str, raw: str | None) -> str | date | Decimal | None:
        if raw is None:
            return None
        if name in MONEY_FIELDS:
            return parse_amount(raw)
        if name in DATE_FIELDS:
            return parse_date(raw)
        if name in ("vendor_gstin", "buyer_gstin"):
            gstin = normalize_gstin(raw)
            return gstin[: MAX_LENGTHS[name]] if gstin else None
        return _clean_text(raw, MAX_LENGTHS.get(name, 300))


def _clean_text(raw: str | None, max_length: int | None = None) -> str | None:
    if raw is None:
        return None
    text = " ".join(raw.split())
    if not text:
        return None
    return text[:max_length] if max_length else text
