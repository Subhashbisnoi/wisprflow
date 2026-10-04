import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from app.core.pagination import Page, PageParams
from app.core.tenant import TenantContext
from app.features.audit.models import AuditAction, AuditEvent
from app.features.audit.repository import AuditRepository


def stringify(value: Any) -> str | None:
    """Audit values are stored as text so every type renders the same way in the timeline."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return f"{value:.2f}" if value == value.quantize(Decimal("0.01")) else str(value)
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


class AuditService:
    """Writes audit events into the caller's session; the caller's commit makes the change
    and its audit record atomic (D-056)."""

    def __init__(self, repository: AuditRepository, tenant: TenantContext) -> None:
        self._repo = repository
        self._tenant = tenant

    def record(
        self,
        action: AuditAction,
        *,
        entity_type: str,
        entity_id: uuid.UUID,
        invoice_id: uuid.UUID | None = None,
        field_name: str | None = None,
        old_value: Any = None,
        new_value: Any = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        event = AuditEvent(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            invoice_id=invoice_id,
            actor_user_id=self._tenant.user_id,
            field_name=field_name,
            old_value=stringify(old_value),
            new_value=stringify(new_value),
            details=details or {},
        )
        return self._repo.add(event)

    def timeline(self, invoice_id: uuid.UUID, params: PageParams) -> Page[AuditEvent]:
        return self._repo.list_for_invoice(invoice_id, params)
