import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status

from app.core.container import Container, get_container
from app.core.exceptions import PayloadTooLargeError, ValidationFailedError
from app.core.pagination import PageOut, PageParams, page_params
from app.features.invoices.dependencies import get_invoice_service, invoice_filters
from app.features.invoices.repository import InvoiceFilters
from app.features.invoices.schemas import (
    InvoiceDetailOut,
    InvoiceSummaryOut,
    UploadError,
    UploadResponse,
    UploadResultOut,
)
from app.features.invoices.service import IncomingFile, InvoiceService

router = APIRouter(prefix="/invoices", tags=["invoices"])


@router.post("", response_model=UploadResponse, status_code=status.HTTP_202_ACCEPTED)
def upload_invoices(
    request: Request,
    files: list[UploadFile] = File(..., description="One or more PDF/PNG/JPG/WEBP files"),
    service: InvoiceService = Depends(get_invoice_service),
    container: Container = Depends(get_container),
) -> UploadResponse:
    settings = container.settings
    if len(files) > settings.max_files_per_upload:
        raise ValidationFailedError(
            f"Upload at most {settings.max_files_per_upload} files at a time.",
            details=[{"field": "files", "message": "Too many files"}],
        )
    declared = int(request.headers.get("content-length") or 0)
    if declared > settings.max_upload_bytes * settings.max_files_per_upload + 1024 * 1024:
        raise PayloadTooLargeError("The upload is too large.")

    outcomes = service.upload_many(
        [IncomingFile(filename=f.filename or "upload", stream=f.file) for f in files]
    )
    results = [
        UploadResultOut(
            filename=o.filename,
            status="accepted" if o.invoice else "rejected",
            invoice=InvoiceSummaryOut.from_model(o.invoice) if o.invoice else None,
            error=UploadError(code=o.error_code or "error", message=o.error_message or "")
            if o.invoice is None
            else None,
        )
        for o in outcomes
    ]
    accepted = sum(1 for r in results if r.status == "accepted")
    return UploadResponse(results=results, accepted=accepted, rejected=len(results) - accepted)


@router.get("", response_model=PageOut[InvoiceSummaryOut])
def list_invoices(
    filters: InvoiceFilters = Depends(invoice_filters),
    page: PageParams = Depends(page_params),
    service: InvoiceService = Depends(get_invoice_service),
) -> PageOut[InvoiceSummaryOut]:
    return PageOut[InvoiceSummaryOut].from_page(
        service.list_invoices(filters, page).map(InvoiceSummaryOut.from_model)
    )


@router.get("/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(
    invoice_id: uuid.UUID, service: InvoiceService = Depends(get_invoice_service)
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(service.get(invoice_id))


@router.get("/{invoice_id}/file", response_class=Response)
def get_invoice_file(
    invoice_id: uuid.UUID, service: InvoiceService = Depends(get_invoice_service)
) -> Response:
    stored = service.open_file(invoice_id)
    return Response(
        content=stored.content,
        media_type=stored.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{quote(stored.filename)}",
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{invoice_id}/retry", response_model=InvoiceDetailOut)
def retry_extraction(
    invoice_id: uuid.UUID, service: InvoiceService = Depends(get_invoice_service)
) -> InvoiceDetailOut:
    return InvoiceDetailOut.from_model(service.retry_extraction(invoice_id))
