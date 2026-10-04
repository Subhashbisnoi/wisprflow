import uuid
from datetime import date
from decimal import Decimal

from fastapi import Depends, Query
from sqlalchemy.orm import Session

from app.core.container import Container, get_container
from app.core.database import get_db
from app.core.exceptions import ValidationFailedError
from app.core.tenant import TenantContext
from app.features.audit.dependencies import get_audit_service
from app.features.audit.service import AuditService
from app.features.auth.dependencies import get_tenant
from app.features.invoices.models import InvoiceStatus
from app.features.invoices.repository import SORTABLE_COLUMNS, InvoiceFilters, InvoiceRepository
from app.features.invoices.service import InvoiceService


def get_invoice_repository(
    db: Session = Depends(get_db), tenant: TenantContext = Depends(get_tenant)
) -> InvoiceRepository:
    return InvoiceRepository(db, tenant)


def get_invoice_service(
    db: Session = Depends(get_db),
    invoices: InvoiceRepository = Depends(get_invoice_repository),
    audit: AuditService = Depends(get_audit_service),
    tenant: TenantContext = Depends(get_tenant),
    container: Container = Depends(get_container),
) -> InvoiceService:
    return InvoiceService(
        session=db,
        invoices=invoices,
        storage=container.storage,
        job_queue=container.job_queue,
        audit=audit,
        tenant=tenant,
        max_upload_bytes=container.settings.max_upload_bytes,
    )


def invoice_filters(
    status: list[InvoiceStatus] = Query(default_factory=list, description="Repeatable"),
    vendor_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None, description="Invoice date from (inclusive)"),
    date_to: date | None = Query(None, description="Invoice date to (inclusive)"),
    min_total: Decimal | None = Query(None, ge=0),
    max_total: Decimal | None = Query(None, ge=0),
    search: str | None = Query(None, max_length=100),
    ids: list[uuid.UUID] = Query(default_factory=list, max_length=100),
    sort: str = Query("-created_at", description="Field, prefix '-' for descending"),
) -> InvoiceFilters:
    if sort.lstrip("-") not in SORTABLE_COLUMNS:
        raise ValidationFailedError(
            details=[{"field": "sort", "message": f"Must be one of {sorted(SORTABLE_COLUMNS)}"}]
        )
    if date_from and date_to and date_from > date_to:
        raise ValidationFailedError(
            details=[{"field": "date_to", "message": "Must be on or after date_from"}]
        )
    if min_total is not None and max_total is not None and min_total > max_total:
        raise ValidationFailedError(
            details=[{"field": "max_total", "message": "Must be at least min_total"}]
        )
    return InvoiceFilters(
        statuses=status,
        vendor_id=vendor_id,
        date_from=date_from,
        date_to=date_to,
        min_total=min_total,
        max_total=max_total,
        search=search or None,
        ids=ids,
        sort=sort,
    )
