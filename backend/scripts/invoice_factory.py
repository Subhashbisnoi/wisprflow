"""Generates realistic sample GST invoices (PDF with text layer, scanned PDF, PNG).

Used by the test-suite and the demo seed. `expected_extraction()` returns exactly what is
printed on the document, which lets the FakeProvider stand in for OpenAI deterministically.
"""

import io
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import pypdfium2 as pdfium
from fpdf import FPDF
from PIL import Image

from app.core.formatting import format_inr
from app.features.extraction.providers.fake_provider import field as xf
from app.features.extraction.schemas import ExtractedInvoice, ExtractedLineItem
from app.features.validation.gstin import compute_check_digit

TWO_PLACES = Decimal("0.01")


def make_gstin(state: str, pan: str, entity: str = "1") -> str:
    first14 = f"{state}{pan}{entity}Z"
    return first14 + compute_check_digit(first14)


def money(value: Decimal) -> str:
    """Indian lakh grouping as printed on real invoices, e.g. 1,23,456.00."""
    return format_inr(value).replace("₹", "")


@dataclass
class Line:
    description: str
    hsn: str
    quantity: Decimal
    rate: Decimal
    amount_override: Decimal | None = None

    @property
    def amount(self) -> Decimal:
        if self.amount_override is not None:
            return self.amount_override
        return (self.quantity * self.rate).quantize(TWO_PLACES)


@dataclass
class InvoiceSpec:
    vendor_name: str
    vendor_gstin: str
    vendor_address: str
    buyer_name: str
    buyer_gstin: str
    buyer_address: str
    invoice_number: str
    invoice_date: date
    due_date: date | None
    lines: list[Line]
    gst_rate: Decimal = Decimal("18")
    inter_state: bool = False
    # Overrides let a spec carry deliberate mistakes for the validation demo.
    subtotal_override: Decimal | None = None
    cgst_override: Decimal | None = None
    sgst_override: Decimal | None = None
    igst_override: Decimal | None = None
    total_override: Decimal | None = None
    round_off: bool = True
    notes: list[str] = field(default_factory=list)

    @property
    def subtotal(self) -> Decimal:
        if self.subtotal_override is not None:
            return self.subtotal_override
        return sum((line.amount for line in self.lines), Decimal("0"))

    def _tax(self, share: Decimal) -> Decimal:
        return (self.subtotal * self.gst_rate * share / 100).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )

    @property
    def cgst(self) -> Decimal | None:
        if self.cgst_override is not None:
            return self.cgst_override
        return None if self.inter_state else self._tax(Decimal("0.5"))

    @property
    def sgst(self) -> Decimal | None:
        if self.sgst_override is not None:
            return self.sgst_override
        return None if self.inter_state else self._tax(Decimal("0.5"))

    @property
    def igst(self) -> Decimal | None:
        if self.igst_override is not None:
            return self.igst_override
        return self._tax(Decimal("1")) if self.inter_state else None

    @property
    def total_before_round(self) -> Decimal:
        return self.subtotal + sum(
            (t for t in (self.cgst, self.sgst, self.igst) if t is not None), Decimal("0")
        )

    @property
    def total(self) -> Decimal:
        if self.total_override is not None:
            return self.total_override
        if self.round_off:
            return self.total_before_round.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return self.total_before_round


# --- Rendering --------------------------------------------------------------------------------

NAVY = (30, 58, 95)
GREY = (90, 100, 115)


def render_pdf(spec: InvoiceSpec) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_margins(16, 16, 16)

    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*NAVY)
    pdf.cell(0, 9, spec.vendor_name, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*GREY)
    pdf.multi_cell(0, 4.5, spec.vendor_address, new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5, f"GSTIN: {spec.vendor_gstin}", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 8, "TAX INVOICE", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)

    pdf.set_font("Helvetica", "", 9.5)
    top = pdf.get_y()
    pdf.multi_cell(
        95,
        5,
        f"Bill To:\n{spec.buyer_name}\n{spec.buyer_address}\nGSTIN: {spec.buyer_gstin}",
        new_x="RIGHT",
        new_y="TOP",
    )
    pdf.set_xy(120, top)
    meta = [
        f"Invoice No: {spec.invoice_number}",
        f"Invoice Date: {spec.invoice_date.strftime('%d/%m/%Y')}",
    ]
    if spec.due_date:
        meta.append(f"Due Date: {spec.due_date.strftime('%d/%m/%Y')}")
    meta.append("Place of Supply: " + spec.buyer_gstin[:2])
    pdf.multi_cell(74, 5, "\n".join(meta), new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(max(pdf.get_y(), top + 26))
    pdf.ln(3)

    widths = (10, 74, 22, 18, 26, 28)
    headers = ("#", "Description", "HSN/SAC", "Qty", "Rate", "Amount")
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(235, 239, 245)
    for w, h in zip(widths, headers, strict=True):
        pdf.cell(w, 7, h, border=1, fill=True, align="R" if h in ("Qty", "Rate", "Amount") else "L")
    pdf.ln()
    pdf.set_font("Helvetica", "", 9)
    for index, line in enumerate(spec.lines, start=1):
        cells = (
            str(index),
            line.description[:44],
            line.hsn,
            f"{line.quantity.normalize():f}",
            money(line.rate),
            money(line.amount),
        )
        for i, (w, value) in enumerate(zip(widths, cells, strict=True)):
            pdf.cell(w, 6.5, value, border=1, align="R" if i >= 3 else "L")
        pdf.ln()

    pdf.ln(2)
    rate = spec.gst_rate.normalize()
    half = (spec.gst_rate / 2).normalize()
    summary: list[tuple[str, str]] = [("Taxable Value (Subtotal)", money(spec.subtotal))]
    if spec.cgst is not None:
        summary.append((f"CGST @ {half:f}%", money(spec.cgst)))
    if spec.sgst is not None:
        summary.append((f"SGST @ {half:f}%", money(spec.sgst)))
    if spec.igst is not None:
        summary.append((f"IGST @ {rate:f}%", money(spec.igst)))
    if spec.total_override is None and spec.round_off and spec.total != spec.total_before_round:
        summary.append(("Round Off", money(spec.total - spec.total_before_round)))
    for label, value in summary:
        pdf.set_x(110)
        pdf.cell(56, 6, label, border=0)
        pdf.cell(28, 6, value, border=0, align="R", new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(110)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.cell(56, 8, "Total Amount (Rs.)", border="T")
    pdf.cell(28, 8, money(spec.total), border="T", align="R", new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GREY)
    for note in [*spec.notes, "This is a computer generated invoice."]:
        pdf.multi_cell(0, 4.5, note, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def render_png(spec: InvoiceSpec, dpi: int = 110) -> bytes:
    """A 'phone photo' style image of the invoice (no text layer)."""
    pdf = pdfium.PdfDocument(render_pdf(spec))
    try:
        image = pdf[0].render(scale=dpi / 72).to_pil().convert("L")
    finally:
        pdf.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def render_scanned_pdf(spec: InvoiceSpec) -> bytes:
    """A PDF that contains only a page image, like a scanner produces."""
    png = render_png(spec)
    image = Image.open(io.BytesIO(png))
    out = io.BytesIO()
    image.convert("RGB").save(out, format="PDF", resolution=110)
    return out.getvalue()


def blank_pdf(pages: int = 1) -> bytes:
    pdf = FPDF(format="A4")
    for _ in range(pages):
        pdf.add_page()
    return bytes(pdf.output())


# --- Expected extraction ----------------------------------------------------------------------


def expected_extraction(spec: InvoiceSpec, confidence: float = 0.92) -> ExtractedInvoice:
    """What a perfect extractor would return for this document."""

    def num(value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"

    return ExtractedInvoice(
        vendor_name=xf(spec.vendor_name, confidence),
        vendor_gstin=xf(spec.vendor_gstin, confidence),
        buyer_gstin=xf(spec.buyer_gstin, confidence),
        invoice_number=xf(spec.invoice_number, confidence),
        invoice_date=xf(spec.invoice_date.isoformat(), confidence),
        due_date=xf(spec.due_date.isoformat() if spec.due_date else None, confidence),
        line_items=[
            ExtractedLineItem(
                description=xf(line.description, confidence),
                hsn_sac=xf(line.hsn, confidence),
                quantity=xf(f"{line.quantity.normalize():f}", confidence),
                rate=xf(num(line.rate), confidence),
                amount=xf(num(line.amount), confidence),
            )
            for line in spec.lines
        ],
        subtotal=xf(num(spec.subtotal), confidence),
        cgst=xf(num(spec.cgst), confidence),
        sgst=xf(num(spec.sgst), confidence),
        igst=xf(num(spec.igst), confidence),
        total=xf(num(spec.total), confidence),
        currency=xf("INR", 0.99),
    )
