import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.features.invoices.models import ExtractionMethod, Invoice, InvoiceStatus
from app.features.validation.models import SEVERITY_ORDER, Severity
from app.features.vendors.schemas import VendorRef


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    position: int
    description: str | None
    hsn_sac: str | None
    quantity: Decimal | None
    rate: Decimal | None
    amount: Decimal | None
    confidence: dict[str, float]


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rule_code: str
    severity: Severity
    field: str | None
    message: str


class InvoiceSummaryOut(BaseModel):
    id: uuid.UUID
    status: InvoiceStatus
    original_filename: str
    vendor: VendorRef | None
    vendor_name: str | None
    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None
    total: Decimal | None
    error_count: int
    warning_count: int
    error_message: str | None
    version: int
    created_at: datetime

    @classmethod
    def from_model(cls, inv: Invoice) -> "InvoiceSummaryOut":
        return cls(
            id=inv.id,
            status=inv.status,
            original_filename=inv.original_filename,
            vendor=VendorRef.model_validate(inv.vendor) if inv.vendor else None,
            vendor_name=inv.vendor_name,
            invoice_number=inv.invoice_number,
            invoice_date=inv.invoice_date,
            due_date=inv.due_date,
            total=inv.total,
            error_count=inv.error_count,
            warning_count=inv.warning_count,
            error_message=inv.error_message,
            version=inv.version,
            created_at=inv.created_at,
        )


class InvoiceDetailOut(InvoiceSummaryOut):
    vendor_gstin: str | None
    buyer_gstin: str | None
    currency: str
    subtotal: Decimal | None
    cgst: Decimal | None
    sgst: Decimal | None
    igst: Decimal | None
    field_confidence: dict[str, float]
    line_items: list[LineItemOut]
    findings: list[FindingOut]
    content_type: str
    file_size_bytes: int
    page_count: int | None
    pages_processed: int | None
    extraction_method: ExtractionMethod | None
    extraction_model: str | None
    extraction_attempts: int
    uploaded_by_name: str
    reviewed_by_name: str | None
    reviewed_at: datetime | None
    rejection_reason: str | None
    review_comment: str | None
    updated_at: datetime

    @classmethod
    def from_model(cls, inv: Invoice) -> "InvoiceDetailOut":
        raw = inv.raw_extraction or {}
        summary = InvoiceSummaryOut.from_model(inv).model_dump()
        findings = sorted(inv.findings, key=lambda f: SEVERITY_ORDER[f.severity])
        return cls(
            **summary,
            vendor_gstin=inv.vendor_gstin,
            buyer_gstin=inv.buyer_gstin,
            currency=inv.currency,
            subtotal=inv.subtotal,
            cgst=inv.cgst,
            sgst=inv.sgst,
            igst=inv.igst,
            field_confidence=inv.field_confidence or {},
            line_items=[LineItemOut.model_validate(li) for li in inv.line_items],
            findings=[FindingOut.model_validate(f) for f in findings],
            content_type=inv.content_type,
            file_size_bytes=inv.file_size_bytes,
            page_count=inv.page_count,
            pages_processed=raw.get("pages_processed"),
            extraction_method=inv.extraction_method,
            extraction_model=raw.get("model"),
            extraction_attempts=inv.extraction_attempts,
            uploaded_by_name=inv.uploaded_by.full_name,
            reviewed_by_name=inv.reviewed_by.full_name if inv.reviewed_by else None,
            reviewed_at=inv.reviewed_at,
            rejection_reason=inv.rejection_reason,
            review_comment=inv.review_comment,
            updated_at=inv.updated_at,
        )


class UploadError(BaseModel):
    code: str
    message: str


class UploadResultOut(BaseModel):
    filename: str
    status: Literal["accepted", "rejected"]
    invoice: InvoiceSummaryOut | None = None
    error: UploadError | None = None


class UploadResponse(BaseModel):
    results: list[UploadResultOut]
    accepted: int
    rejected: int
