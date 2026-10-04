from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant import TenantContext
from app.features.audit.dependencies import get_audit_service
from app.features.audit.service import AuditService
from app.features.auth.dependencies import get_tenant
from app.features.extraction.job import build_validation_service
from app.features.invoices.dependencies import get_invoice_repository
from app.features.invoices.repository import InvoiceRepository
from app.features.review.service import ReviewService
from app.features.validation.service import ValidationService
from app.features.vendors.dependencies import get_vendor_matching_service
from app.features.vendors.matching import VendorMatchingService


def get_validation_service(
    db: Session = Depends(get_db), tenant: TenantContext = Depends(get_tenant)
) -> ValidationService:
    return build_validation_service(db, tenant)


def get_review_service(
    db: Session = Depends(get_db),
    invoices: InvoiceRepository = Depends(get_invoice_repository),
    validation: ValidationService = Depends(get_validation_service),
    vendor_matching: VendorMatchingService = Depends(get_vendor_matching_service),
    audit: AuditService = Depends(get_audit_service),
    tenant: TenantContext = Depends(get_tenant),
) -> ReviewService:
    return ReviewService(db, invoices, validation, vendor_matching, audit, tenant)
