import uuid

from app.core.pagination import Page, PageParams, paginate
from app.core.tenant import TenantRepository
from app.features.audit.models import AuditEvent


class AuditRepository(TenantRepository[AuditEvent]):
    model = AuditEvent

    def list_for_invoice(self, invoice_id: uuid.UUID, params: PageParams) -> Page[AuditEvent]:
        stmt = (
            self.scoped()
            .where(AuditEvent.invoice_id == invoice_id)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
        )
        return paginate(self.session, stmt, params)
