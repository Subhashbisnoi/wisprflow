import logging
import queue
import threading
import uuid
from dataclasses import dataclass, field

from app.infrastructure.jobs.base import JobHandler, JobPayload, JobQueue

logger = logging.getLogger("app.jobs")


@dataclass
class _Job:
    name: str
    payload: JobPayload
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex)


_STOP = _Job(name="__stop__", payload={})


class InProcessJobQueue(JobQueue):
    """A thread pool fed by a queue.Queue. Good for a single-process MVP.

    Durability comes from the database: the invoice status is the source of truth and
    pending jobs are re-enqueued at startup, so losing this in-memory queue loses no work.
    """

    def __init__(self, workers: int = 3) -> None:
        self._workers = workers
        self._queue: queue.Queue[_Job] = queue.Queue()
        self._handlers: dict[str, JobHandler] = {}
        self._threads: list[threading.Thread] = []
        self._timers: set[threading.Timer] = set()
        self._lock = threading.Lock()
        self._running = False

    def register(self, name: str, handler: JobHandler) -> None:
        self._handlers[name] = handler

    def enqueue(self, name: str, payload: JobPayload, delay_seconds: float = 0) -> None:
        if name not in self._handlers:
            raise KeyError(f"No handler registered for job '{name}'")
        job = _Job(name=name, payload=dict(payload))
        if delay_seconds > 0:
            timer = threading.Timer(delay_seconds, self._delayed_put, args=(job,))
            timer.daemon = True
            with self._lock:
                self._timers.add(timer)
            timer.start()
        else:
            self._queue.put(job)
        logger.info(
            "job enqueued",
            extra={"job": name, "job_id": job.job_id, "delay_seconds": delay_seconds},
        )

    def _delayed_put(self, job: _Job) -> None:
        with self._lock:
            self._timers = {t for t in self._timers if t.is_alive()}
        if self._running:
            self._queue.put(job)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        for i in range(self._workers):
            thread = threading.Thread(target=self._run, name=f"job-worker-{i}", daemon=True)
            thread.start()
            self._threads.append(thread)
        logger.info("job queue started", extra={"workers": self._workers})

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        with self._lock:
            for timer in self._timers:
                timer.cancel()
            self._timers.clear()
        for _ in self._threads:
            self._queue.put(_STOP)
        for thread in self._threads:
            thread.join(timeout=10)
        self._threads.clear()
        logger.info("job queue stopped")

    def join(self) -> None:
        """Block until all queued jobs are processed (used by tests and scripts)."""
        self._queue.join()

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            try:
                if job is _STOP:
                    return
                handler = self._handlers[job.name]
                handler({**job.payload, "job_id": job.job_id})
            except Exception:
                # Handlers own their retry policy; anything reaching here is a bug.
                logger.exception("job crashed", extra={"job": job.name, "job_id": job.job_id})
            finally:
                self._queue.task_done()
