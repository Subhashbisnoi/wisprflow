"""Common contract for validation rules (D-055)."""

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Protocol

from app.features.validation.models import Severity


@dataclass(frozen=True)
class LineSnapshot:
    position: int
    description: str | None
    quantity: Decimal | None
    rate: Decimal | None
    amount: Decimal | None


@dataclass(frozen=True)
class InvoiceSnapshot:
    """Immutable view of an invoice so rules cannot mutate ORM state."""

    id: uuid.UUID
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    buyer_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    subtotal: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    total: Decimal | None = None
    lines: tuple[LineSnapshot, ...] = ()
    field_confidence: dict[str, float] = field(default_factory=dict)
    file_sha256: str | None = None


@dataclass(frozen=True)
class DuplicateMatch:
    id: uuid.UUID
    invoice_number: str | None
    vendor_name: str | None
    original_filename: str
    status: str
    created_at: datetime


class DuplicateLookup(Protocol):
    def find_duplicates(
        self,
        vendor_gstin: str,
        invoice_number: str,
        total: Decimal,
        exclude_id: uuid.UUID,
    ) -> list[DuplicateMatch]: ...

    def find_by_sha256(self, sha256: str, exclude_id: uuid.UUID) -> list[DuplicateMatch]: ...


@dataclass(frozen=True)
class ValidationContext:
    invoice: InvoiceSnapshot
    company_gstin: str | None
    company_state_code: str | None
    duplicates: DuplicateLookup


@dataclass(frozen=True)
class FindingDraft:
    rule_code: str
    severity: Severity
    message: str
    field: str | None = None


class ValidationRule(ABC):
    code: str

    @abstractmethod
    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]: ...

    def finding(self, severity: Severity, message: str, field: str | None = None) -> FindingDraft:
        return FindingDraft(rule_code=self.code, severity=severity, message=message, field=field)


AMOUNT_TOLERANCE = Decimal("1.00")  # D-029

FIELD_LABELS: dict[str, str] = {
    "vendor_name": "Vendor name",
    "vendor_gstin": "Vendor GSTIN",
    "buyer_gstin": "Buyer GSTIN",
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "subtotal": "Subtotal",
    "cgst": "CGST",
    "sgst": "SGST",
    "igst": "IGST",
    "total": "Total",
}


def zero_if_none(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")
