from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

JobPayload = dict[str, Any]
JobHandler = Callable[[JobPayload], None]


class RetryableJobError(Exception):
    """Raised by a handler to ask the queue to retry the job later."""


class JobQueue(ABC):
    """Background job abstraction. Payloads must be JSON-serialisable so a Redis-backed
    implementation (RQ, Arq, Celery) can replace the in-process one (D-048)."""

    @abstractmethod
    def register(self, name: str, handler: JobHandler) -> None: ...

    @abstractmethod
    def enqueue(self, name: str, payload: JobPayload, delay_seconds: float = 0) -> None: ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...
