from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import NotFoundError
from app.infrastructure.storage.base import FileStorage
from app.infrastructure.storage.models import StoredFile


class DatabaseFileStorage(FileStorage):
    """Keeps documents in Postgres. No extra service needed, and every serverless instance
    sees the same files. Suited to MVP volumes; move to S3 as volume grows."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, key: str, data: bytes) -> None:
        stmt = insert(StoredFile).values(key=key, data=data, size_bytes=len(data))
        stmt = stmt.on_conflict_do_update(
            index_elements=[StoredFile.key], set_={"data": data, "size_bytes": len(data)}
        )
        with self._session_factory() as session, session.begin():
            session.execute(stmt)

    def read(self, key: str) -> bytes:
        with self._session_factory() as session:
            data = session.scalar(select(StoredFile.data).where(StoredFile.key == key))
        if data is None:
            raise NotFoundError("The document file is missing from storage.")
        return bytes(data)

    def exists(self, key: str) -> bool:
        with self._session_factory() as session:
            return session.scalar(select(StoredFile.key).where(StoredFile.key == key)) is not None

    def delete(self, key: str) -> None:
        with self._session_factory() as session, session.begin():
            session.execute(delete(StoredFile).where(StoredFile.key == key))
