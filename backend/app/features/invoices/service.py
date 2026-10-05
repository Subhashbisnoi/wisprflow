import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.core.exceptions import InvalidStateError
from app.core.pagination import Page, PageParams
from app.core.tenant import TenantContext
from app.features.audit.models import AuditAction
from app.features.audit.service import AuditService
from app.features.extraction.job import EXTRACT_INVOICE_JOB, extraction_payload
from app.features.invoices.file_types import sniff_file_type
from app.features.invoices.models import Invoice, InvoiceStatus
from app.features.invoices.repository import InvoiceFilters, InvoiceRepository
from app.infrastructure.jobs.base import JobQueue
from app.infrastructure.storage.base import FileStorage

logger = logging.getLogger("app.invoices")

STALE_EXTRACTION_MINUTES = 5


@dataclass(frozen=True)
class IncomingFile:
    filename: str
    stream: BinaryIO


@dataclass(frozen=True)
class UploadOutcome:
    filename: str
    invoice: Invoice | None = None
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class StoredFile:
    content: bytes
    content_type: str
    filename: str


def _human_size(size: int) -> str:
    return f"{size / (1024 * 1024):.1f} MB"


class InvoiceService:
    def __init__(
        self,
        session: Session,
        invoices: InvoiceRepository,
        storage: FileStorage,
        job_queue: JobQueue,
        audit: AuditService,
        tenant: TenantContext,
        max_upload_bytes: int,
    ) -> None:
        self._session = session
        self._invoices = invoices
        self._storage = storage
        self._jobs = job_queue
        self._audit = audit
        self._tenant = tenant
        self._max_bytes = max_upload_bytes

    # --- Upload ------------------------------------------------------------------------------

    def upload_many(self, files: list[IncomingFile]) -> list[UploadOutcome]:
        outcomes = [self._accept(f) for f in files]
        self._session.commit()
        # Enqueue only after commit so workers always find the row (HLD section 3).
        for outcome in outcomes:
            if outcome.invoice is not None:
                self._jobs.enqueue(
                    EXTRACT_INVOICE_JOB,
                    extraction_payload(outcome.invoice.id, self._tenant.company_id),
                )
        # An inline (sync) queue may already have extracted them in its own session.
        self._session.expire_all()
        for outcome in outcomes:
            if outcome.invoice is not None:
                self._session.refresh(outcome.invoice)
        accepted = sum(1 for o in outcomes if o.invoice)
        logger.info(
            "invoices uploaded",
            extra={"accepted": accepted, "rejected": len(outcomes) - accepted},
        )
        return outcomes

    def _accept(self, incoming: IncomingFile) -> UploadOutcome:
        filename = (incoming.filename or "upload").rsplit("/", 1)[-1][:255]
        data = incoming.stream.read(self._max_bytes + 1)  # never buffer past the cap
        if len(data) > self._max_bytes:
            incoming.stream.seek(0, 2)
            size = incoming.stream.tell()
            return UploadOutcome(
                filename,
                error_code="file_too_large",
                error_message=f"File is {_human_size(size)}; the limit is "
                f"{_human_size(self._max_bytes)}. Compress or split the PDF.",
            )
        if not data:
            return UploadOutcome(
                filename, error_code="unsupported_file_type", error_message="File is empty."
            )
        file_type = sniff_file_type(data[:2048])
        if file_type is None:
            return UploadOutcome(
                filename,
                error_code="unsupported_file_type",
                error_message="Only PDF, PNG, JPG and WEBP files are supported.",
            )

        sha256 = hashlib.sha256(data).hexdigest()
        invoice_id = uuid.uuid4()
        key = f"{self._tenant.company_id}/{invoice_id}/{sha256}.{file_type.extension}"
        try:
            self._storage.save(key, data)
        except OSError:
            logger.exception("storage save failed")
            return UploadOutcome(
                filename,
                error_code="storage_error",
                error_message="The file could not be stored. Please try again.",
            )

        assert self._tenant.user_id is not None
        invoice = self._invoices.add(
            Invoice(
                id=invoice_id,
                uploaded_by_id=self._tenant.user_id,
                status=InvoiceStatus.QUEUED,
                original_filename=filename,
                storage_key=key,
                content_type=file_type.content_type,
                file_size_bytes=len(data),
                file_sha256=sha256,
                field_confidence={},
                extraction_attempts=0,
                error_count=0,
                warning_count=0,
                currency="INR",
                version=1,
            )
        )
        self._audit.record(
            AuditAction.INVOICE_UPLOADED,
            entity_type="invoice",
            entity_id=invoice_id,
            invoice_id=invoice_id,
            details={"filename": filename, "size_bytes": len(data), "type": file_type.content_type},
        )
        self._session.flush()
        return UploadOutcome(filename, invoice=invoice)

    # --- Queries -----------------------------------------------------------------------------

    def list_invoices(self, filters: InvoiceFilters, params: PageParams) -> Page[Invoice]:
        return self._invoices.search(filters, params)

    def get(self, invoice_id: uuid.UUID) -> Invoice:
        return self._invoices.get_or_raise(invoice_id)

    def open_file(self, invoice_id: uuid.UUID) -> StoredFile:
        invoice = self._invoices.get_or_raise(invoice_id)
        return StoredFile(
            content=self._storage.read(invoice.storage_key),
            content_type=invoice.content_type,
            filename=invoice.original_filename,
        )

    @staticmethod
    def _can_retry(invoice: Invoice) -> bool:
        if invoice.status == InvoiceStatus.FAILED:
            return True
        # A worker that died mid-job (or a serverless timeout) leaves the bill in progress.
        stale_before = datetime.now(UTC) - timedelta(minutes=STALE_EXTRACTION_MINUTES)
        return (
            invoice.status in (InvoiceStatus.QUEUED, InvoiceStatus.PROCESSING)
            and invoice.updated_at < stale_before
        )

    # --- Commands ----------------------------------------------------------------------------

    def retry_extraction(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = self._invoices.get_for_update(invoice_id)
        if invoice is None:
            return self._invoices.get_or_raise(invoice_id)
        if not self._can_retry(invoice):
            raise InvalidStateError(
                "Only failed bills, or bills stuck in extraction for more than "
                f"{STALE_EXTRACTION_MINUTES} minutes, can be retried."
            )
        invoice.status = InvoiceStatus.QUEUED
        invoice.extraction_attempts = 0
        invoice.error_message = None
        invoice.version += 1
        self._audit.record(
            AuditAction.EXTRACTION_RETRIED,
            entity_type="invoice",
            entity_id=invoice.id,
            invoice_id=invoice.id,
        )
        self._session.commit()
        self._jobs.enqueue(EXTRACT_INVOICE_JOB, extraction_payload(invoice.id, invoice.company_id))
        # An inline (sync) queue may already have finished the job in its own session.
        self._session.expire_all()
        return self._invoices.get_or_raise(invoice_id)
