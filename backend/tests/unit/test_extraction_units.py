import io
from datetime import date
from decimal import Decimal as D

import pytest
from pypdf import PdfReader, PdfWriter

from app.core.formatting import format_inr
from app.features.extraction.document_reader import (
    DocumentReader,
    PasswordProtectedDocumentError,
    UnreadableDocumentError,
)
from app.features.extraction.grounding import ConfidenceGrounder
from app.features.extraction.normalizer import InvoiceNormalizer, parse_amount, parse_date
from app.features.extraction.providers.fake_provider import field as xf
from app.features.invoices.file_types import PDF, PNG, sniff_file_type
from app.features.invoices.models import ExtractionMethod
from scripts.invoice_factory import (
    blank_pdf,
    expected_extraction,
    render_pdf,
    render_png,
    render_scanned_pdf,
)
from tests.conftest import sample_spec


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,23,456.50", D("123456.50")),
        ("₹ 11,800", D("11800.00")),
        ("Rs. 999.999", D("1000.00")),
        ("INR 42", D("42.00")),
        ("(250.00)", D("-250.00")),
        ("abc", None),
        (None, None),
    ],
)
def test_parse_amount(raw: str | None, expected: D | None) -> None:
    assert parse_amount(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-10-05", date(2026, 10, 5)),
        ("05/10/2026", date(2026, 10, 5)),  # day-first, Indian convention
        ("5-Oct-2026", date(2026, 10, 5)),
        ("5th October 2026", date(2026, 10, 5)),
        ("05.10.26", None),
        ("not a date", None),
    ],
)
def test_parse_date(raw: str, expected: date | None) -> None:
    assert parse_date(raw) == expected


def test_format_inr_uses_lakh_grouping() -> None:
    assert format_inr(D("1234567.5")) == "₹12,34,567.50"
    assert format_inr(D("999")) == "₹999.00"
    assert format_inr(D("-100000")) == "-₹1,00,000.00"


def test_normalizer_keeps_unparseable_raw_values_and_zeroes_confidence() -> None:
    extracted = expected_extraction(sample_spec())
    extracted.invoice_date = xf("sometime in Sept", 0.8)
    normalized = InvoiceNormalizer().normalize(extracted)
    assert normalized.values["invoice_date"] is None
    assert normalized.confidence["invoice_date"] == 0.0
    assert normalized.unparsed["invoice_date"] == "sometime in Sept"


def test_grounding_raises_found_values_and_caps_invented_ones() -> None:
    spec = sample_spec()
    content = DocumentReader().read(render_pdf(spec), "application/pdf")
    extracted = expected_extraction(spec, confidence=0.8)
    extracted.invoice_number = xf("INV-INVENTED-1", 0.99)
    normalized = ConfidenceGrounder().ground(InvoiceNormalizer().normalize(extracted), content.text)
    assert normalized.confidence["total"] >= 0.95
    assert normalized.confidence["invoice_date"] >= 0.95  # printed as 12/09/2026
    assert normalized.confidence["invoice_number"] == 0.70


def test_reader_uses_text_layer_for_digital_pdf() -> None:
    content = DocumentReader().read(render_pdf(sample_spec()), "application/pdf")
    assert content.method == ExtractionMethod.TEXT_LAYER
    assert "AT/2026/0042" in content.text


def test_reader_falls_back_to_vision_for_scans_and_images() -> None:
    scanned = DocumentReader().read(render_scanned_pdf(sample_spec()), "application/pdf")
    assert scanned.method == ExtractionMethod.VISION and len(scanned.images) == 1
    image = DocumentReader().read(render_png(sample_spec()), "image/png")
    assert image.method == ExtractionMethod.VISION


def test_reader_caps_vision_pages() -> None:
    content = DocumentReader(max_vision_pages=2).read(blank_pdf(pages=4), "application/pdf")
    assert content.page_count == 4 and len(content.images) == 2
    assert content.pages_processed == 2


def test_reader_rejects_corrupt_pdf() -> None:
    with pytest.raises(UnreadableDocumentError):
        DocumentReader().read(b"%PDF-1.7\n garbage garbage", "application/pdf")


def test_reader_rejects_password_protected_pdf() -> None:
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(render_pdf(sample_spec()))))
    writer.encrypt(user_password="secret", owner_password="owner", algorithm="AES-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    with pytest.raises(PasswordProtectedDocumentError):
        DocumentReader().read(buffer.getvalue(), "application/pdf")


def test_sniff_file_type_ignores_extension() -> None:
    assert sniff_file_type(render_pdf(sample_spec())[:16]) == PDF
    assert sniff_file_type(render_png(sample_spec())[:16]) == PNG
    assert sniff_file_type(b"PK\x03\x04 docx in disguise") is None
