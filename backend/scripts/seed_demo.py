"""Seed a demo company, user and realistic bills so Ledgerline can be demoed immediately.

    python -m scripts.seed_demo            # deterministic offline extraction (no OpenAI cost)
    python -m scripts.seed_demo --live     # run every sample through the real OpenAI provider

Re-running resets ONLY the demo company (matched by the demo email). The bills go through the
real pipeline (PDF text layer / vision path, grounding, vendor matching, validation engine,
review service, audit trail); only the LLM call is simulated unless --live is passed.

It also writes sample documents to ../samples/ for manual drag-and-drop uploads.
"""

import argparse
import io
import logging
import sys
from collections import deque
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path

from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from app.core.config import REPO_ROOT, get_settings
from app.core.container import Container
from app.core.database import get_session_factory
from app.core.security import PasswordHasher, TokenService
from app.core.tenant import TenantContext
from app.db.models import AuditEvent, Company, Invoice, User
from app.features.audit.models import AuditAction
from app.features.audit.repository import AuditRepository
from app.features.audit.service import AuditService
from app.features.auth.repository import CompanyRepository, UserRepository
from app.features.auth.schemas import SignupRequest
from app.features.auth.service import AuthService
from app.features.extraction.job import (
    EXTRACT_INVOICE_JOB,
    ExtractionJobHandler,
    build_validation_service,
)
from app.features.extraction.providers.base import LLMProvider
from app.features.extraction.providers.fake_provider import FakeProvider
from app.features.extraction.schemas import ExtractedInvoice
from app.features.invoices.models import InvoiceStatus
from app.features.invoices.repository import InvoiceRepository
from app.features.invoices.service import IncomingFile, InvoiceService
from app.features.review.service import ReviewService
from app.features.vendors.matching import VendorMatchingService
from app.features.vendors.repository import VendorRepository
from app.infrastructure.jobs.sync import SynchronousJobQueue
from app.infrastructure.storage.local import LocalFileStorage
from app.main import build_llm_provider
from scripts.invoice_factory import (
    InvoiceSpec,
    Line,
    expected_extraction,
    make_gstin,
    render_pdf,
    render_png,
    render_scanned_pdf,
)

DEMO_EMAIL = "demo@ledgerline.in"
DEMO_PASSWORD = "Demo@12345"
DEMO_COMPANY = "Shakti Components Pvt Ltd"
COMPANY_GSTIN = make_gstin("27", "AAKCS4821M")
COMPANY_ADDRESS = "Plot 14, MIDC Bhosari, Pune 411026"

logger = logging.getLogger("seed")

ACME = ("Acme Traders Pvt Ltd", make_gstin("27", "AAPCA1234B"), "12 MG Road, Pune 411001")
SHARMA = (
    "Sharma Logistics LLP",
    make_gstin("29", "AAKFS5678F"),
    "44 Peenya Industrial Area, Bengaluru 560058",
)
BHARAT = (
    "Bharat Steel Industries Ltd",
    make_gstin("24", "AABCB9087K"),
    "GIDC Estate, Vatva, Ahmedabad 382445",
)
MEHTA = (
    "Mehta Office Supplies",
    make_gstin("27", "AGXPM3344Q"),
    "Shop 7, Lamington Road, Mumbai 400007",
)
CLOUDNINE = (
    "CloudNine Software Services Pvt Ltd",
    make_gstin("36", "AAFCC7712H"),
    "HITEC City, Hyderabad 500081",
)
PATEL = ("Patel Packaging Co", make_gstin("27", "AAJFP6655R"), "Chakan MIDC, Pune 410501")
GANESH = ("Shree Ganesh Electricals", "27ABCPG1234K1Z9", "Kasba Peth, Pune 411011")  # bad check


@dataclass
class Sample:
    key: str
    spec: InvoiceSpec
    uploaded: datetime
    kind: str = "pdf"  # pdf | scan | png | corrupt
    decision: str | None = None  # approve | reject
    note: str | None = None
    confidence: float = 0.92
    low_confidence_fields: tuple[str, ...] = ()


def spec(
    vendor: tuple[str, str, str],
    number: str,
    invoice_date: date,
    lines: list[Line],
    due_days: int | None = 30,
    **kw: object,
) -> InvoiceSpec:
    return InvoiceSpec(
        vendor_name=vendor[0],
        vendor_gstin=vendor[1],
        vendor_address=vendor[2],
        buyer_name=DEMO_COMPANY,
        buyer_gstin=COMPANY_GSTIN,
        buyer_address=COMPANY_ADDRESS,
        invoice_number=number,
        invoice_date=invoice_date,
        due_date=invoice_date + timedelta(days=due_days) if due_days else None,
        lines=lines,
        **kw,  # type: ignore[arg-type]
    )


def build_samples(today: date) -> list[Sample]:
    def at(days_ago: int, hour: int = 11) -> datetime:
        day = today - timedelta(days=days_ago)
        return datetime(day.year, day.month, day.day, hour, 15, tzinfo=UTC)

    def d(days_ago: int) -> date:
        return today - timedelta(days=days_ago)

    paper = Line("Copier paper A4 75gsm (box of 5 reams)", "4802", D("40"), D("1245.00"))
    toner = Line("Toner cartridge HP 88A", "8443", D("6"), D("3150.00"))
    freight = Line("Road freight Pune-Bengaluru, 2 MT", "996511", D("1"), D("18500.00"))
    steel = Line("MS plate 10mm IS2062", "7208", D("2.5"), D("58400.00"))
    saas = Line("ERP subscription, 25 users (monthly)", "998314", D("25"), D("1450.00"))
    boxes = Line("5-ply corrugated boxes 18x12x10", "4819", D("1200"), D("38.50"))
    cable = Line("FR copper cable 2.5 sq mm (90m coil)", "8544", D("12"), D("2875.00"))
    many_lines = [
        Line(f"Fastener kit SKU-{1000 + i}", "7318", D(str(5 + i % 7)), D(str(120 + i * 15)))
        for i in range(34)
    ]

    acme_clean = spec(ACME, "AT/2026/0412", d(52), [paper, toner])
    return [
        # History: approved bills over previous months feed the spend chart.
        Sample(
            "history-1",
            spec(BHARAT, "BSI/26-27/0098", d(128), [steel], inter_state=True),
            at(126),
            decision="approve",
        ),
        Sample(
            "history-2",
            spec(SHARMA, "SL-5521", d(97), [freight], inter_state=True),
            at(95),
            decision="approve",
        ),
        Sample(
            "history-3",
            spec(CLOUDNINE, "CN/INV/7781", d(66), [saas], inter_state=True),
            at(65),
            decision="approve",
        ),
        Sample(
            "history-4", spec(PATEL, "PPC-2026-311", d(60), [boxes]), at(58), decision="approve"
        ),
        Sample("clean-acme", acme_clean, at(50), decision="approve", note="Matched with PO 4471"),
        Sample(
            "history-5",
            spec(CLOUDNINE, "CN/INV/8120", d(35), [saas], inter_state=True),
            at(34),
            decision="approve",
        ),
        Sample(
            "approved-recent",
            spec(PATEL, "PPC-2026-401", d(4), [boxes]),
            at(3, 9),
            decision="approve",
        ),
        Sample(
            "rejected",
            spec(MEHTA, "MOS/1187", d(4), [paper]),
            at(3, 10),
            decision="reject",
            note="Goods not received at Bhosari plant",
        ),
        Sample(
            "approved-recent-2",
            spec(MEHTA, "MOS/1251", d(3), [toner]),
            at(2, 9),
            decision="approve",
        ),
        # Current queue: one bill per validation scenario.
        Sample("duplicate", acme_clean, at(6, 10)),
        Sample("invalid-gstin", spec(GANESH, "SGE/26/0045", d(9), [cable]), at(5, 12)),
        Sample(
            "lines-dont-add-up",
            spec(MEHTA, "MOS/1244", d(8), [paper, toner], subtotal_override=D("63000.00")),
            at(4, 9),
        ),
        Sample(
            "odd-tax-rate",
            spec(
                PATEL,
                "PPC-2026-388",
                d(7),
                [boxes],
                cgst_override=D("3326.40"),
                sgst_override=D("3326.40"),
                total_override=D("52852.80"),
                round_off=False,
            ),
            at(4, 15),
        ),
        Sample(
            "wrong-tax-type",
            spec(ACME, "AT/2026/0467", d(5), [toner, paper], inter_state=True),
            at(3, 11),
        ),
        Sample(
            "multi-page",
            spec(BHARAT, "BSI/26-27/0131", d(4), many_lines, inter_state=True),
            at(2, 10),
        ),
        Sample(
            "scanned",
            spec(SHARMA, "SL-5790", d(3), [freight], inter_state=True, due_days=None),
            at(1, 16),
            kind="scan",
            confidence=0.88,
            low_confidence_fields=("invoice_number", "total"),
        ),
        Sample(
            "clean-ready", spec(CLOUDNINE, "CN/INV/8452", d(2), [saas], inter_state=True), at(1, 9)
        ),
        Sample("corrupt", spec(MEHTA, "MOS/0000", d(1), [paper]), at(0, 9), kind="corrupt"),
    ]


def document_bytes(sample: Sample) -> tuple[str, bytes, str]:
    slug = sample.spec.invoice_number.replace("/", "-")
    if sample.kind == "scan":
        return f"scan-{slug}.pdf", render_scanned_pdf(sample.spec), "application/pdf"
    if sample.kind == "png":
        return f"photo-{slug}.png", render_png(sample.spec), "image/png"
    if sample.kind == "corrupt":
        return (
            "damaged-export.pdf",
            b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj << /Type /Cat",
            "application/pdf",
        )
    return f"{slug}.pdf", render_pdf(sample.spec), "application/pdf"


def extraction_for(sample: Sample) -> ExtractedInvoice:
    result = expected_extraction(sample.spec, sample.confidence)
    for name in sample.low_confidence_fields:
        getattr(result, name).confidence = 0.52
    return result


def build_fake_provider(samples: list[Sample]) -> FakeProvider:
    by_number = {s.spec.invoice_number: extraction_for(s) for s in samples}
    vision = deque(extraction_for(s) for s in samples if s.kind in ("scan", "png"))

    def resolve(text_layer: str | None) -> ExtractedInvoice | None:
        if text_layer is None:
            return vision.popleft() if vision else None
        for number, extracted in by_number.items():
            if number in text_layer:
                return extracted
        return None

    provider = FakeProvider(resolver=resolve)
    provider.text_model = provider.vision_model = "offline demo"
    return provider


def reset_demo_company(session: Session, storage_root: Path) -> None:
    existing = session.scalars(select(User).where(User.email == DEMO_EMAIL)).first()
    if existing is None:
        return
    company_id = existing.company_id
    session.execute(delete(Company).where(Company.id == company_id))  # cascades to all tables
    session.commit()
    company_dir = storage_root / str(company_id)
    if company_dir.is_dir():
        for path in sorted(company_dir.rglob("*"), reverse=True):
            path.unlink() if path.is_file() else path.rmdir()
        company_dir.rmdir()
    print(f"  removed previous demo company {company_id}")


def backdate(session: Session, invoice_id: object, when: datetime, decided: bool) -> None:
    """Shift a bill and its audit trail back in time, preserving event order. Decisions are
    placed a day after upload, as a reviewer would typically get to them."""
    invoice = session.get(Invoice, invoice_id)
    assert invoice is not None
    delta = invoice.created_at - when
    session.execute(
        update(Invoice)
        .where(Invoice.id == invoice_id)
        .values(
            created_at=Invoice.created_at - delta,
            updated_at=Invoice.updated_at - delta,
            reviewed_at=Invoice.reviewed_at - delta,
        )
    )
    session.execute(
        update(AuditEvent)
        .where(AuditEvent.invoice_id == invoice_id)
        .values(created_at=AuditEvent.created_at - delta)
    )
    if decided:
        decided_at = min(when + timedelta(hours=26), datetime.now(UTC))
        session.execute(
            update(Invoice).where(Invoice.id == invoice_id).values(reviewed_at=decided_at)
        )
        session.execute(
            update(AuditEvent)
            .where(
                AuditEvent.invoice_id == invoice_id,
                AuditEvent.action.in_([AuditAction.INVOICE_APPROVED, AuditAction.INVOICE_REJECTED]),
            )
            .values(created_at=decided_at)
        )
    session.commit()


def write_manual_samples(samples: list[Sample]) -> Path:
    out = REPO_ROOT / "samples"
    out.mkdir(exist_ok=True)
    picks = {s.key: s for s in samples}
    files = {
        "01-clean-intra-state.pdf": render_pdf(picks["clean-ready"].spec),
        "02-clean-acme.pdf": render_pdf(picks["clean-acme"].spec),
        "03-duplicate-of-02.pdf": render_pdf(picks["clean-acme"].spec),
        "04-invalid-gstin.pdf": render_pdf(picks["invalid-gstin"].spec),
        "05-line-items-dont-add-up.pdf": render_pdf(picks["lines-dont-add-up"].spec),
        "06-wrong-tax-type.pdf": render_pdf(picks["wrong-tax-type"].spec),
        "07-multi-page.pdf": render_pdf(picks["multi-page"].spec),
        "08-scanned-no-text-layer.pdf": render_scanned_pdf(picks["scanned"].spec),
        "09-phone-photo.png": render_png(picks["odd-tax-rate"].spec),
        "10-corrupt.pdf": b"%PDF-1.7\n%broken",
    }
    for name, data in files.items():
        (out / name).write_bytes(data)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--live", action="store_true", help="use the real OpenAI provider")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)

    settings = get_settings()
    session_factory = get_session_factory()
    today = date.today()
    samples = build_samples(today)
    provider: LLMProvider = (
        build_llm_provider(settings) if args.live else build_fake_provider(samples)
    )

    container = Container(
        settings=settings,
        session_factory=session_factory,
        storage=LocalFileStorage(settings.storage_dir),
        job_queue=SynchronousJobQueue(),
        llm_provider=provider,
        token_service=TokenService(settings),
        password_hasher=PasswordHasher(),
    )
    container.job_queue.register(EXTRACT_INVOICE_JOB, ExtractionJobHandler(container))

    print(f"Seeding demo data ({'live OpenAI' if args.live else 'offline extraction'})")
    with session_factory() as session:
        session.execute(text("SELECT 1"))
        reset_demo_company(session, settings.storage_dir)
        result = AuthService(
            session,
            UserRepository(session),
            CompanyRepository(session),
            container.password_hasher,
            container.token_service,
        ).signup(
            SignupRequest(
                company_name=DEMO_COMPANY,
                company_gstin=COMPANY_GSTIN,
                full_name="Asha Verma",
                email=DEMO_EMAIL,
                password=DEMO_PASSWORD,
            )
        )
        tenant = TenantContext(company_id=result.company.id, user_id=result.user.id)
        print(f"  company {DEMO_COMPANY} ({COMPANY_GSTIN}) and user {DEMO_EMAIL}")

    for sample in samples:
        with session_factory() as session:
            audit = AuditService(AuditRepository(session, tenant), tenant)
            invoices = InvoiceService(
                session,
                InvoiceRepository(session, tenant),
                container.storage,
                container.job_queue,
                audit,
                tenant,
                settings.max_upload_bytes,
            )
            filename, data, _ = document_bytes(sample)
            outcome = invoices.upload_many([IncomingFile(filename, io.BytesIO(data))])[0]
            assert outcome.invoice is not None, outcome.error_message
            invoice_id = outcome.invoice.id

        with session_factory() as session:
            review = ReviewService(
                session,
                InvoiceRepository(session, tenant),
                build_validation_service(session, tenant),
                VendorMatchingService(
                    VendorRepository(session, tenant),
                    AuditService(AuditRepository(session, tenant), tenant),
                ),
                AuditService(AuditRepository(session, tenant), tenant),
                tenant,
            )
            invoice = session.get(Invoice, invoice_id)
            assert invoice is not None
            if sample.decision and invoice.status == InvoiceStatus.NEEDS_REVIEW:
                if sample.decision == "approve" and invoice.error_count == 0:
                    review.approve(invoice_id, invoice.version, sample.note)
                elif sample.decision == "reject":
                    review.reject(invoice_id, invoice.version, sample.note or "Rejected")
            backdate(session, invoice_id, sample.uploaded, decided=bool(sample.decision))
            session.refresh(invoice)
            print(
                f"  {sample.key:<18} {invoice.status.value:<13} "
                f"errors={invoice.error_count} warnings={invoice.warning_count}"
            )

    out = write_manual_samples(samples)
    print(f"\nSample files for manual upload written to {out}")
    print("\nDemo login")
    print(f"  email:    {DEMO_EMAIL}")
    print(f"  password: {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
