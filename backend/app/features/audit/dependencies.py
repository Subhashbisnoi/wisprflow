from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.tenant import TenantContext
from app.features.audit.repository import AuditRepository
from app.features.audit.service import AuditService
from app.features.auth.dependencies import get_tenant


def get_audit_service(
    db: Session = Depends(get_db), tenant: TenantContext = Depends(get_tenant)
) -> AuditService:
    return AuditService(AuditRepository(db, tenant), tenant)
