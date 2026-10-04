from abc import ABC, abstractmethod


class FileStorage(ABC):
    """Abstraction over document storage (local disk now, S3/GCS later; D-050)."""

    @abstractmethod
    def save(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def read(self, key: str) -> bytes: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
