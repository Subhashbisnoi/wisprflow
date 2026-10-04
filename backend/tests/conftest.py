"""Shared fixtures. Tests run against a real, separate Postgres database (D-064)."""

import os
from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.core.config import Settings, normalize_database_url
from app.core.container import Container
from app.core.security import PasswordHasher, TokenService
from app.db.models import Base
from app.features.extraction.providers.fake_provider import FakeProvider
from app.infrastructure.jobs.sync import SynchronousJobQueue
from app.infrastructure.storage.local import LocalFileStorage
from app.main import create_app
from scripts.invoice_factory import InvoiceSpec, Line, expected_extraction, make_gstin

BACKEND_DIR = Path(__file__).resolve().parents[1]
TEST_DATABASE_URL = normalize_database_url(
    os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://localhost/ledgerline_test")
)

BUYER_GSTIN = make_gstin("27", "AABCD1234E")
VENDOR_GSTIN = make_gstin("27", "AAPCA1234B")
INTERSTATE_VENDOR_GSTIN = make_gstin("29", "AAKCS5678F")


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = create_engine(TEST_DATABASE_URL)
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.cmd_opts = type("Opts", (), {"x": [f"url={TEST_DATABASE_URL}"]})()  # type: ignore[assignment]
    command.upgrade(cfg, "head")  # the migration itself is under test
    yield eng
    eng.dispose()


@pytest.fixture(autouse=True)
def _clean_tables(request: pytest.FixtureRequest) -> Iterator[None]:
    yield
    if "engine" not in request.fixturenames:
        return
    eng: Engine = request.getfixturevalue("engine")
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with eng.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(  # type: ignore[call-arg]
        DATABASE_URL=TEST_DATABASE_URL,
        app_env="test",
        jwt_secret="test-secret-for-unit-tests-only-0123456789",
        llm_provider="fake",
        storage_dir=tmp_path / "storage",
        start_job_queue=False,
        max_upload_mb=2,
        extraction_max_attempts=3,
        extraction_backoff_base_seconds=0,
        log_level="WARNING",
    )


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def container(engine: Engine, settings: Settings, provider: FakeProvider) -> Container:
    return Container(
        settings=settings,
        session_factory=sessionmaker(bind=engine, autoflush=False, expire_on_commit=False),
        storage=LocalFileStorage(settings.storage_dir),
        job_queue=SynchronousJobQueue(),
        llm_provider=provider,
        token_service=TokenService(settings),
        password_hasher=PasswordHasher(rounds=4),
    )


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container)) as test_client:
        yield test_client


@pytest.fixture
def db(container: Container) -> Iterator[Session]:
    with container.session_factory() as session:
        yield session


def signup(
    client: TestClient, email: str = "priya@acmedemo.in", **overrides: Any
) -> dict[str, Any]:
    body = {
        "company_name": "Demo Manufacturing Pvt Ltd",
        "company_gstin": BUYER_GSTIN,
        "full_name": "Priya Sharma",
        "email": email,
        "password": "correct-horse-1",
        **overrides,
    }
    response = client.post("/api/v1/auth/signup", json=body)
    assert response.status_code == 201, response.text
    data: dict[str, Any] = response.json()
    data["headers"] = {"Authorization": f"Bearer {data['access_token']}"}
    return data


@pytest.fixture
def auth(client: TestClient) -> dict[str, Any]:
    return signup(client)


def sample_spec(**overrides: Any) -> InvoiceSpec:
    base: dict[str, Any] = {
        "vendor_name": "Acme Traders Pvt Ltd",
        "vendor_gstin": VENDOR_GSTIN,
        "vendor_address": "12 MG Road, Pune 411001",
        "buyer_name": "Demo Manufacturing Pvt Ltd",
        "buyer_gstin": BUYER_GSTIN,
        "buyer_address": "Andheri East, Mumbai 400069",
        "invoice_number": "AT/2026/0042",
        "invoice_date": date(2026, 9, 12),
        "due_date": date(2026, 10, 12),
        "lines": [
            Line("Copier paper A4 75gsm", "4802", Decimal("50"), Decimal("245.50")),
            Line("Toner cartridge", "8443", Decimal("3"), Decimal("3150")),
        ],
    }
    base.update(overrides)
    return InvoiceSpec(**base)


def use_spec(provider: FakeProvider, spec: InvoiceSpec) -> None:
    """Make the fake LLM return exactly what is printed on `spec`."""
    provider.default = expected_extraction(spec)


def upload(client: TestClient, headers: dict[str, str], *files: tuple[str, bytes, str]) -> Any:
    return client.post(
        "/api/v1/invoices",
        headers=headers,
        files=[("files", (name, data, ctype)) for name, data, ctype in files],
    )
