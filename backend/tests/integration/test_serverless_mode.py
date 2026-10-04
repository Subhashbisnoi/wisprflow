"""Settings used on serverless hosts: database file storage, inline jobs, stuck-job retry."""

import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from app.core.config import Settings
from app.core.container import Container
from app.core.exceptions import NotFoundError
from app.db.models import Invoice
from app.features.extraction.providers.fake_provider import FakeProvider
from app.features.invoices.models import InvoiceStatus
from app.infrastructure.jobs.sync import SynchronousJobQueue
from app.infrastructure.storage.database import DatabaseFileStorage
from app.main import build_job_queue, build_storage, create_app
from scripts.invoice_factory import render_pdf
from tests.conftest import sample_spec, signup, upload, use_spec


def test_database_storage_round_trip(container: Container) -> None:
    storage = DatabaseFileStorage(container.session_factory)
    storage.save("c1/i1/abc.pdf", b"%PDF-1 first")
    storage.save("c1/i1/abc.pdf", b"%PDF-1 second")  # overwrite is an upsert
    assert storage.exists("c1/i1/abc.pdf")
    assert storage.read("c1/i1/abc.pdf") == b"%PDF-1 second"
    storage.delete("c1/i1/abc.pdf")
    assert not storage.exists("c1/i1/abc.pdf")
    with pytest.raises(NotFoundError):
        storage.read("c1/i1/abc.pdf")


def test_settings_select_serverless_backends(settings: Settings, container: Container) -> None:
    serverless = settings.model_copy(
        update={"storage_backend": "database", "job_queue_backend": "sync"}
    )
    assert isinstance(build_storage(serverless, container.session_factory), DatabaseFileStorage)
    assert isinstance(build_job_queue(serverless), SynchronousJobQueue)


def test_sync_queue_honours_retry_delay_when_asked() -> None:
    calls: list[float] = []
    queue = SynchronousJobQueue(honor_delays=True)
    queue.register("job", lambda _: calls.append(time.monotonic()))
    started = time.monotonic()
    queue.enqueue("job", {}, delay_seconds=0.2)
    assert calls and calls[0] - started >= 0.2


def test_full_flow_with_database_storage(container: Container, provider: FakeProvider) -> None:
    container.storage = DatabaseFileStorage(container.session_factory)
    with TestClient(create_app(container)) as client:
        auth = signup(client)
        spec = sample_spec()
        use_spec(provider, spec)
        pdf = render_pdf(spec)
        invoice_id = upload(client, auth["headers"], ("a.pdf", pdf, "application/pdf")).json()[
            "results"
        ][0]["invoice"]["id"]
        detail = client.get(f"/api/v1/invoices/{invoice_id}", headers=auth["headers"]).json()
        assert detail["status"] == "needs_review"
        file = client.get(f"/api/v1/invoices/{invoice_id}/file", headers=auth["headers"])
        assert file.content == pdf


def test_bill_stuck_in_extraction_can_be_retried(
    client: TestClient, auth: dict[str, Any], provider: FakeProvider, container: Container
) -> None:
    use_spec(provider, sample_spec())
    invoice_id = upload(
        client, auth["headers"], ("a.pdf", render_pdf(sample_spec()), "application/pdf")
    ).json()["results"][0]["invoice"]["id"]
    retry_url = f"/api/v1/invoices/{invoice_id}/retry"

    with container.session_factory() as session, session.begin():
        session.execute(
            update(Invoice)
            .where(Invoice.id == invoice_id)
            .values(status=InvoiceStatus.PROCESSING, updated_at=datetime.now(UTC))
        )
    fresh = client.post(retry_url, headers=auth["headers"])
    assert fresh.status_code == 409  # still within the normal processing window

    with container.session_factory() as session, session.begin():
        session.execute(
            update(Invoice)
            .where(Invoice.id == invoice_id)
            .values(updated_at=datetime.now(UTC) - timedelta(minutes=10))
        )
    stale = client.post(retry_url, headers=auth["headers"])
    assert stale.status_code == 200
    assert stale.json()["status"] == "needs_review"
