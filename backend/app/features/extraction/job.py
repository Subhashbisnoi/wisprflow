"""Background job wiring for extraction (D-048, D-049)."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.container import Container
from app.core.logging import company_id_var
from app.core.tenant import TenantContext
from app.features.audit.repository import AuditRepository
from app.features.audit.service import AuditService
from app.features.auth.repository import CompanyRepository
from app.features.extraction.document_reader import DocumentReader
from app.features.extraction.grounding import ConfidenceGrounder
from app.features.extraction.normalizer import InvoiceNormalizer
from app.features.extraction.service import ExtractionService, Outcome
from app.features.invoices.models import Invoice, InvoiceStatus
from app.features.invoices.repository import InvoiceRepository
from app.features.validation.engine import ValidationEngine
from app.features.validation.service import ValidationService
from app.features.vendors.matching import VendorMatchingService
from app.features.vendors.repository import VendorRepository
from app.infrastructure.jobs.base import JobPayload

logger = logging.getLogger("app.extraction.job")

EXTRACT_INVOICE_JOB = "extract_invoice"


def build_validation_service(session: Session, tenant: TenantContext) -> ValidationService:
    return ValidationService(
        engine=ValidationEngine(),
        duplicates=InvoiceRepository(session, tenant),
        companies=CompanyRepository(session),
        tenant=tenant,
    )


def build_extraction_service(
    session: Session, tenant: TenantContext, container: Container
) -> ExtractionService:
    audit = AuditService(AuditRepository(session, tenant), tenant)
    return ExtractionService(
        session=session,
        invoices=InvoiceRepository(session, tenant),
        storage=container.storage,
        reader=DocumentReader(),
        provider=container.llm_provider,
        normalizer=InvoiceNormalizer(),
        grounder=ConfidenceGrounder(),
        vendor_matching=VendorMatchingService(VendorRepository(session, tenant), audit),
        validation=build_validation_service(session, tenant),
        audit=audit,
        max_attempts=container.settings.extraction_max_attempts,
    )


def extraction_payload(invoice_id: uuid.UUID, company_id: uuid.UUID) -> JobPayload:
    return {"invoice_id": str(invoice_id), "company_id": str(company_id)}


class ExtractionJobHandler:
    def __init__(self, container: Container) -> None:
        self._container = container

    def __call__(self, payload: JobPayload) -> None:
        invoice_id = uuid.UUID(payload["invoice_id"])
        company_id = uuid.UUID(payload["company_id"])
        token = company_id_var.set(str(company_id))
        session = self._container.session_factory()
        try:
            # Jobs act as the system: no user id, tenant from the payload (never a request).
            tenant = TenantContext(company_id=company_id, user_id=None)
            result = build_extraction_service(session, tenant, self._container).process(invoice_id)
            if result.outcome == Outcome.RETRY:
                delay = self._container.settings.extraction_backoff_base_seconds * (
                    4 ** (result.attempts - 1)
                )
                self._container.job_queue.enqueue(
                    EXTRACT_INVOICE_JOB, extraction_payload(invoice_id, company_id), delay
                )
        finally:
            session.close()
            company_id_var.reset(token)


def recover_pending_jobs(container: Container) -> int:
    """Re-enqueue bills left queued/processing by a previous process (D-048).

    Deliberately cross-tenant: this is a system maintenance task, not a request.
    """
    with container.session_factory() as session:
        rows = session.execute(
            select(Invoice.id, Invoice.company_id).where(
                Invoice.status.in_([InvoiceStatus.QUEUED, InvoiceStatus.PROCESSING])
            )
        ).all()
    for invoice_id, company_id in rows:
        container.job_queue.enqueue(EXTRACT_INVOICE_JOB, extraction_payload(invoice_id, company_id))
    if rows:
        logger.info("recovered pending extraction jobs", extra={"count": len(rows)})
    return len(rows)
