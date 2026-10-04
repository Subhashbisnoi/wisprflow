"""Parses reviewer-entered values into typed field values."""

from datetime import date
from decimal import Decimal

from app.core.exceptions import ValidationFailedError
from app.features.extraction.normalizer import parse_amount, parse_date
from app.features.invoices.models import EDITABLE_HEADER_FIELDS, EDITABLE_LINE_FIELDS
from app.features.validation.gstin import normalize_gstin

FieldValue = str | date | Decimal | None

TEXT_LIMITS = {
    "vendor_name": 300,
    "invoice_number": 100,
    "vendor_gstin": 32,
    "buyer_gstin": 32,
    "hsn_sac": 20,
    "description": 1000,
}


def _invalid(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(message, details=[{"field": field, "message": message}])


def parse_field_value(field: str, raw: str | None, *, line: bool = False) -> FieldValue:
    kind = (EDITABLE_LINE_FIELDS if line else EDITABLE_HEADER_FIELDS).get(field)
    if kind is None:
        raise _invalid(field, f"'{field}' cannot be edited.")
    text = raw.strip() if raw is not None else ""
    if not text:
        return None

    if kind is Decimal:
        value = parse_amount(text, "0.001" if field == "quantity" else "0.01")
        if value is None:
            raise _invalid(field, "Enter a number, for example 12500.50.")
        if value < 0:
            raise _invalid(field, "Amounts cannot be negative.")
        if value >= Decimal("1000000000000"):
            raise _invalid(field, "Amount is too large.")
        return value
    if kind is date:
        parsed = parse_date(text)
        if parsed is None:
            raise _invalid(field, "Enter a valid date, for example 2026-10-04.")
        return parsed
    if field in ("vendor_gstin", "buyer_gstin"):
        gstin = normalize_gstin(text)
        if gstin and len(gstin) > TEXT_LIMITS[field]:
            raise _invalid(field, "GSTIN is too long.")
        return gstin
    limit = TEXT_LIMITS.get(field, 300)
    if len(text) > limit:
        raise _invalid(field, f"Must be at most {limit} characters.")
    return " ".join(text.split())
