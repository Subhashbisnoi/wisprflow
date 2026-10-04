import uuid
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal as D

import pytest

from app.features.validation.engine import ValidationEngine
from app.features.validation.models import Severity
from app.features.validation.rules.base import (
    DuplicateMatch,
    FindingDraft,
    InvoiceSnapshot,
    LineSnapshot,
    ValidationContext,
    ValidationRule,
)
from app.features.validation.rules.duplicate_invoice import DuplicateInvoiceRule
from app.features.validation.rules.gstin_format import GstinFormatRule
from app.features.validation.rules.line_item_arithmetic import LineItemArithmeticRule
from app.features.validation.rules.low_confidence import LowConfidenceRule
from app.features.validation.rules.required_fields import RequiredFieldsRule
from app.features.validation.rules.tax_rate import TaxRateRule
from app.features.validation.rules.tax_type import TaxTypeRule
from app.features.validation.rules.totals import TotalsRule
from scripts.invoice_factory import make_gstin

MH_VENDOR = make_gstin("27", "AAPCA1234B")
MH_BUYER = make_gstin("27", "AABCD1234E")
KA_VENDOR = make_gstin("29", "AAKCS5678F")


class FakeDuplicates:
    def __init__(
        self,
        by_fields: list[DuplicateMatch] | None = None,
        by_sha: list[DuplicateMatch] | None = None,
    ) -> None:
        self.by_fields = by_fields or []
        self.by_sha = by_sha or []

    def find_duplicates(self, *_: object) -> list[DuplicateMatch]:
        return self.by_fields

    def find_by_sha256(self, *_: object) -> list[DuplicateMatch]:
        return self.by_sha


def clean_invoice(**overrides: object) -> InvoiceSnapshot:
    base = InvoiceSnapshot(
        id=uuid.uuid4(),
        vendor_name="Acme Traders Pvt Ltd",
        vendor_gstin=MH_VENDOR,
        buyer_gstin=MH_BUYER,
        invoice_number="AT/2026/0042",
        invoice_date=date(2026, 9, 12),
        due_date=date(2026, 10, 12),
        subtotal=D("10000.00"),
        cgst=D("900.00"),
        sgst=D("900.00"),
        igst=None,
        total=D("11800.00"),
        lines=(
            LineSnapshot(1, "Paper", D("10"), D("500.00"), D("5000.00")),
            LineSnapshot(2, "Toner", D("2"), D("2500.00"), D("5000.00")),
        ),
        field_confidence={"total": 0.98, "vendor_gstin": 0.97},
        file_sha256="a" * 64,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def ctx(
    invoice: InvoiceSnapshot,
    duplicates: FakeDuplicates | None = None,
    company_gstin: str | None = MH_BUYER,
) -> ValidationContext:
    return ValidationContext(
        invoice=invoice,
        company_gstin=company_gstin,
        company_state_code=company_gstin[:2] if company_gstin else None,
        duplicates=duplicates or FakeDuplicates(),
    )


def severities(findings: list[FindingDraft]) -> list[Severity]:
    return [f.severity for f in findings]


def test_clean_invoice_has_no_findings() -> None:
    assert ValidationEngine().evaluate(ctx(clean_invoice())) == []


# --- required fields -------------------------------------------------------------------------


def test_missing_required_fields_are_errors_and_recommended_are_warnings() -> None:
    findings = RequiredFieldsRule().evaluate(
        ctx(clean_invoice(invoice_number=None, total=None, due_date=None, lines=()))
    )
    by_field = {f.field: f.severity for f in findings}
    assert by_field["invoice_number"] == Severity.ERROR
    assert by_field["total"] == Severity.ERROR
    assert by_field["due_date"] == Severity.WARNING
    assert by_field["line_items"] == Severity.WARNING
    assert "missing" in findings[0].message


# --- GSTIN -----------------------------------------------------------------------------------


def test_invalid_vendor_gstin_is_error_with_reason() -> None:
    findings = GstinFormatRule().evaluate(ctx(clean_invoice(vendor_gstin="27AAPCA1234B1Z9")))
    assert severities(findings) == [Severity.ERROR]
    assert "check digit" in findings[0].message


def test_buyer_gstin_of_another_entity_is_warning() -> None:
    other = make_gstin("27", "AAACZ9999Q")
    findings = GstinFormatRule().evaluate(ctx(clean_invoice(buyer_gstin=other)))
    assert severities(findings) == [Severity.WARNING]
    assert "does not match your company GSTIN" in findings[0].message


# --- duplicates ------------------------------------------------------------------------------


def _match(**kw: object) -> DuplicateMatch:
    base = {
        "id": uuid.uuid4(),
        "invoice_number": "AT/2026/0042",
        "vendor_name": "Acme Traders",
        "original_filename": "acme-sept.pdf",
        "status": "approved",
        "created_at": datetime(2026, 10, 2, tzinfo=UTC),
    }
    base.update(kw)
    return DuplicateMatch(**base)  # type: ignore[arg-type]


def test_duplicate_by_vendor_number_and_amount() -> None:
    findings = DuplicateInvoiceRule().evaluate(
        ctx(clean_invoice(), FakeDuplicates(by_fields=[_match()]))
    )
    assert severities(findings) == [Severity.ERROR]
    assert "duplicate of invoice AT/2026/0042" in findings[0].message
    assert "02 Oct 2026" in findings[0].message


def test_same_file_reported_once_even_if_fields_also_match() -> None:
    same = _match()
    findings = DuplicateInvoiceRule().evaluate(
        ctx(clean_invoice(), FakeDuplicates(by_fields=[same], by_sha=[same]))
    )
    assert len(findings) == 1
    assert "exact file" in findings[0].message


# --- arithmetic ------------------------------------------------------------------------------


def test_line_items_not_adding_up_to_subtotal() -> None:
    findings = LineItemArithmeticRule().evaluate(ctx(clean_invoice(subtotal=D("9500.00"))))
    assert severities(findings) == [Severity.ERROR]
    assert findings[0].field == "subtotal"
    assert "₹10,000.00" in findings[0].message and "₹500.00" in findings[0].message


def test_line_quantity_times_rate_mismatch() -> None:
    lines = (LineSnapshot(1, "Paper", D("10"), D("500.00"), D("5500.00")),)
    findings = LineItemArithmeticRule().evaluate(
        ctx(clean_invoice(lines=lines, subtotal=D("5500")))
    )
    assert severities(findings) == [Severity.ERROR]
    assert findings[0].field == "line_items.1.amount"


def test_totals_round_off_is_info_and_big_gap_is_error() -> None:
    assert severities(TotalsRule().evaluate(ctx(clean_invoice(total=D("11800.40"))))) == [
        Severity.INFO
    ]
    findings = TotalsRule().evaluate(ctx(clean_invoice(total=D("12800.00"))))
    assert severities(findings) == [Severity.ERROR]
    assert "₹11,800.00" in findings[0].message


# --- tax -------------------------------------------------------------------------------------


def test_unequal_cgst_sgst_is_error() -> None:
    findings = TaxRateRule().evaluate(ctx(clean_invoice(sgst=D("800.00"), total=D("11700.00"))))
    assert Severity.ERROR in severities(findings)


@pytest.mark.parametrize("rate_tax", [D("765.00")])  # 15.3% of 10,000 split in two
def test_non_standard_rate_is_warning(rate_tax: D) -> None:
    findings = TaxRateRule().evaluate(
        ctx(clean_invoice(cgst=rate_tax, sgst=rate_tax, total=D("11530")))
    )
    assert severities(findings) == [Severity.WARNING]
    assert "15.30%" in findings[0].message


def test_standard_rate_with_paise_rounding_passes() -> None:
    inv = clean_invoice(
        subtotal=D("101.00"), cgst=D("9.09"), sgst=D("9.09"), total=D("119.18"), lines=()
    )
    assert TaxRateRule().evaluate(ctx(inv)) == []


def test_igst_on_intra_state_supply_is_error() -> None:
    inv = clean_invoice(cgst=None, sgst=None, igst=D("1800.00"))
    findings = TaxTypeRule().evaluate(ctx(inv))
    assert severities(findings) == [Severity.ERROR]
    assert "Maharashtra" in findings[0].message


def test_cgst_on_inter_state_supply_is_error() -> None:
    findings = TaxTypeRule().evaluate(ctx(clean_invoice(vendor_gstin=KA_VENDOR)))
    assert severities(findings) == [Severity.ERROR]
    assert "Karnataka" in findings[0].message and "IGST should apply" in findings[0].message


def test_inter_state_with_igst_passes() -> None:
    inv = clean_invoice(vendor_gstin=KA_VENDOR, cgst=None, sgst=None, igst=D("1800.00"))
    assert TaxTypeRule().evaluate(ctx(inv)) == []


def test_tax_type_falls_back_to_company_state_when_buyer_gstin_missing() -> None:
    inv = clean_invoice(buyer_gstin=None, cgst=None, sgst=None, igst=D("1800.00"))
    assert severities(TaxTypeRule().evaluate(ctx(inv))) == [Severity.ERROR]


# --- confidence ------------------------------------------------------------------------------


def test_low_confidence_field_is_warning() -> None:
    inv = clean_invoice(field_confidence={"total": 0.42})
    findings = LowConfidenceRule().evaluate(ctx(inv))
    assert severities(findings) == [Severity.WARNING]
    assert "42%" in findings[0].message


# --- engine ----------------------------------------------------------------------------------


class ExplodingRule(ValidationRule):
    code = "exploding"

    def evaluate(self, ctx: ValidationContext) -> list[FindingDraft]:
        raise RuntimeError("boom")


def test_engine_survives_crashing_rule_and_sorts_by_severity() -> None:
    engine = ValidationEngine([TotalsRule(), ExplodingRule(), RequiredFieldsRule()])
    findings = engine.evaluate(ctx(clean_invoice(total=D("11800.50"), due_date=None)))
    assert severities(findings) == [Severity.WARNING, Severity.WARNING, Severity.INFO]
    assert any(f.rule_code == "exploding" for f in findings)
