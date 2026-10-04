from app.infrastructure.jobs.base import JobHandler, JobPayload, JobQueue


class SynchronousJobQueue(JobQueue):
    """Runs jobs inline when enqueued. Used by tests and the demo seed script.

    Delayed retries are executed immediately so tests stay fast and deterministic.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self.enqueued: list[tuple[str, JobPayload]] = []

    def register(self, name: str, handler: JobHandler) -> None:
        self._handlers[name] = handler

    def enqueue(self, name: str, payload: JobPayload, delay_seconds: float = 0) -> None:
        self.enqueued.append((name, payload))
        self._handlers[name]({**payload, "job_id": f"sync-{len(self.enqueued)}"})

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None
