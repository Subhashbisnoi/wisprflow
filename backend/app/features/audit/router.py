import uuid

from fastapi import APIRouter, Depends

from app.core.pagination import PageOut, PageParams, page_params
from app.features.audit.dependencies import get_audit_service
from app.features.audit.schemas import AuditEventOut
from app.features.audit.service import AuditService
from app.features.invoices.dependencies import get_invoice_service
from app.features.invoices.service import InvoiceService

router = APIRouter(prefix="/invoices", tags=["audit"])


@router.get("/{invoice_id}/audit-events", response_model=PageOut[AuditEventOut])
def list_audit_events(
    invoice_id: uuid.UUID,
    page: PageParams = Depends(page_params),
    audit: AuditService = Depends(get_audit_service),
    invoices: InvoiceService = Depends(get_invoice_service),
) -> PageOut[AuditEventOut]:
    invoices.get(invoice_id)  # 404 for unknown / other-tenant bills
    return PageOut[AuditEventOut].from_page(
        audit.timeline(invoice_id, page).map(AuditEventOut.from_model)
    )
