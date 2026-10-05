import time

from app.infrastructure.jobs.base import JobHandler, JobPayload, JobQueue


class SynchronousJobQueue(JobQueue):
    """Runs jobs inline when enqueued.

    Used by tests and the demo seed (delays skipped, so they stay fast and deterministic)
    and on serverless hosts (JOB_QUEUE_BACKEND=sync, delays honoured for retry backoff).
    """

    def __init__(self, honor_delays: bool = False) -> None:
        self._honor_delays = honor_delays
        self._handlers: dict[str, JobHandler] = {}
        self.enqueued: list[tuple[str, JobPayload]] = []

    def register(self, name: str, handler: JobHandler) -> None:
        self._handlers[name] = handler

    def enqueue(self, name: str, payload: JobPayload, delay_seconds: float = 0) -> None:
        self.enqueued.append((name, payload))
        if self._honor_delays and delay_seconds > 0:
            time.sleep(delay_seconds)
        self._handlers[name]({**payload, "job_id": f"sync-{len(self.enqueued)}"})

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None
