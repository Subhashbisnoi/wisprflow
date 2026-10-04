from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant import TenantContext
from app.features.audit.dependencies import get_audit_service
from app.features.audit.service import AuditService
from app.features.auth.dependencies import get_tenant
from app.features.vendors.matching import VendorMatchingService
from app.features.vendors.repository import VendorRepository
from app.features.vendors.service import VendorService


def get_vendor_repository(
    db: Session = Depends(get_db), tenant: TenantContext = Depends(get_tenant)
) -> VendorRepository:
    return VendorRepository(db, tenant)


def get_vendor_service(
    db: Session = Depends(get_db),
    vendors: VendorRepository = Depends(get_vendor_repository),
    audit: AuditService = Depends(get_audit_service),
) -> VendorService:
    return VendorService(db, vendors, audit)


def get_vendor_matching_service(
    vendors: VendorRepository = Depends(get_vendor_repository),
    audit: AuditService = Depends(get_audit_service),
) -> VendorMatchingService:
    return VendorMatchingService(vendors, audit)
