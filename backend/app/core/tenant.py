"""Tenant context and the base repositories that enforce it (D-044)."""

import uuid
from dataclasses import dataclass
from typing import Any, ClassVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError


@dataclass(frozen=True)
class TenantContext:
    company_id: uuid.UUID
    user_id: uuid.UUID | None  # None for system actors (background jobs)


class BaseRepository[T]:
    model: ClassVar[type[Any]]

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, entity: T) -> T:
        self.session.add(entity)
        return entity

    def flush(self) -> None:
        self.session.flush()


class TenantRepository[T](BaseRepository[T]):
    """All reads go through `scoped()`, which always filters by the tenant's company_id."""

    not_found_message: ClassVar[str] = "The requested resource was not found."

    def __init__(self, session: Session, tenant: TenantContext) -> None:
        super().__init__(session)
        self.tenant = tenant

    def scoped(self) -> Select[T]:
        return select(self.model).where(self.model.company_id == self.tenant.company_id)

    def get(self, entity_id: uuid.UUID) -> T | None:
        stmt = self.scoped().where(self.model.id == entity_id)
        return self.session.scalars(stmt).first()

    def get_or_raise(self, entity_id: uuid.UUID) -> T:
        entity = self.get(entity_id)
        if entity is None:
            raise NotFoundError(self.not_found_message)
        return entity

    def add(self, entity: T) -> T:
        # Defence in depth: the tenant always comes from context, never the caller.
        entity.company_id = self.tenant.company_id  # type: ignore[attr-defined]
        return super().add(entity)
