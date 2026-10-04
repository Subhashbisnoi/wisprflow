"""SQLAlchemy engine, session factory and declarative base."""

import enum
import uuid
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache

from fastapi import Request
from sqlalchemy import DateTime, Enum, ForeignKey, MetaData, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantMixin:
    """Every tenant-owned table carries company_id (D-044)."""

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        pool_recycle=1800,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


def get_db(request: Request) -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    The factory comes from the app container so tests can point it at a test database.
    """
    session = request.app.state.container.session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def str_enum(enum_cls: type[enum.StrEnum], name: str, length: int = 20) -> Enum:
    """VARCHAR + CHECK constraint enum column: portable and easy to extend in migrations."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=length,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )
