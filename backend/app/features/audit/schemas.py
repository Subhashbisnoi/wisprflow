import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.features.audit.models import AuditAction, AuditEvent


class AuditEventOut(BaseModel):
    id: uuid.UUID
    action: AuditAction
    entity_type: str
    entity_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_name: str
    field_name: str | None
    old_value: str | None
    new_value: str | None
    details: dict[str, Any]
    created_at: datetime

    @classmethod
    def from_model(cls, event: AuditEvent) -> "AuditEventOut":
        return cls(
            id=event.id,
            action=event.action,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            actor_user_id=event.actor_user_id,
            actor_name=event.actor.full_name if event.actor else "System",
            field_name=event.field_name,
            old_value=event.old_value,
            new_value=event.new_value,
            details=event.details,
            created_at=event.created_at,
        )
