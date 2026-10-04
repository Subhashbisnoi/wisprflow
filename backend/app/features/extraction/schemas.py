"""Structured output contract between the LLM provider and the extraction service.

All values are strings exactly as the model read them; the normaliser converts types. This
keeps the provider contract simple and lets us keep the raw value when parsing fails.
"""

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    value: str | None = Field(description="Value as printed on the invoice, or null if absent")
    confidence: float = Field(description="0.0 to 1.0: how sure you are the value is correct")


class ExtractedLineItem(BaseModel):
    description: ExtractedField
    hsn_sac: ExtractedField
    quantity: ExtractedField
    rate: ExtractedField
    amount: ExtractedField


class ExtractedInvoice(BaseModel):
    vendor_name: ExtractedField
    vendor_gstin: ExtractedField
    buyer_gstin: ExtractedField
    invoice_number: ExtractedField
    invoice_date: ExtractedField
    due_date: ExtractedField
    line_items: list[ExtractedLineItem]
    subtotal: ExtractedField
    cgst: ExtractedField
    sgst: ExtractedField
    igst: ExtractedField
    total: ExtractedField
    currency: ExtractedField


HEADER_FIELDS = (
    "vendor_name",
    "vendor_gstin",
    "buyer_gstin",
    "invoice_number",
    "invoice_date",
    "due_date",
    "subtotal",
    "cgst",
    "sgst",
    "igst",
    "total",
)
