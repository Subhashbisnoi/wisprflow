import uuid

from fastapi import APIRouter, Depends, Query

from app.features.invoices.schemas import InvoiceDetailOut
from app.features.review.dependencies import get_review_service
from app.features.review.schemas import (
    ApproveRequest,
    FieldCorrectionRequest,
    LineItemCorrectionRequest,
    LineItemCreateRequest,
    RejectRequest,
)
from app.features.review.service import ReviewService

router = APIRouter(prefix="/invoices", tags=["review"])


@router.patch("/{invoice_id}/fields", response_model=InvoiceDetailOut)
def correct_fields(
    invoice_id: uuid.UUID,
    body: FieldCorrectionRequest,
    service: ReviewService = Depends(get_review_service),
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(
        service.correct_fields(invoice_id, body.version, body.changes)
    )


@router.post("/{invoice_id}/line-items", response_model=InvoiceDetailOut, status_code=201)
def add_line_item(
    invoice_id: uuid.UUID,
    body: LineItemCreateRequest,
    service: ReviewService = Depends(get_review_service),
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(service.add_line_item(invoice_id, body.version, body))


@router.patch("/{invoice_id}/line-items/{item_id}", response_model=InvoiceDetailOut)
def correct_line_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    body: LineItemCorrectionRequest,
    service: ReviewService = Depends(get_review_service),
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(
        service.correct_line_item(invoice_id, item_id, body.version, body.changes)
    )


@router.delete("/{invoice_id}/line-items/{item_id}", response_model=InvoiceDetailOut)
def remove_line_item(
    invoice_id: uuid.UUID,
    item_id: uuid.UUID,
    version: int = Query(ge=1),
    service: ReviewService = Depends(get_review_service),
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(service.remove_line_item(invoice_id, item_id, version))


@router.post("/{invoice_id}/approve", response_model=InvoiceDetailOut)
def approve(
    invoice_id: uuid.UUID,
    body: ApproveRequest,
    service: ReviewService = Depends(get_review_service),
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(service.approve(invoice_id, body.version, body.comment))


@router.post("/{invoice_id}/reject", response_model=InvoiceDetailOut)
def reject(
    invoice_id: uuid.UUID,
    body: RejectRequest,
    service: ReviewService = Depends(get_review_service),
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(service.reject(invoice_id, body.version, body.reason))
