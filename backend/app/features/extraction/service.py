import enum
import logging
import time
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session

from app.features.audit.models import AuditAction
from app.features.audit.service import AuditService
from app.features.extraction.document_reader import (
    DocumentContent,
    DocumentError,
    DocumentReader,
)
from app.features.extraction.grounding import ConfidenceGrounder
from app.features.extraction.normalizer import InvoiceNormalizer, NormalizedInvoice
from app.features.extraction.providers.base import (
    LLMProvider,
    ProviderPermanentError,
    ProviderTransientError,
)
from app.features.invoices.models import (
    ExtractionMethod,
    Invoice,
    InvoiceLineItem,
    InvoiceStatus,
)
from app.features.invoices.repository import InvoiceRepository
from app.features.validation.service import ValidationService
from app.features.vendors.matching import VendorMatchingService
from app.infrastructure.storage.base import FileStorage

logger = logging.getLogger("app.extraction")

VISION_CONFIDENCE_CAP = 0.90  # D-053

PROVIDER_DOWN_MESSAGE = (
    "The AI service is busy or unavailable right now. Click 'Retry extraction' to try again."
)


class Outcome(enum.StrEnum):
    COMPLETED = "completed"
    RETRY = "retry"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ExtractionResult:
    outcome: Outcome
    attempts: int = 0


class ExtractionService:
    """Worker-side pipeline: read document -> LLM -> normalise -> ground -> vendor -> validate."""

    def __init__(
        self,
        session: Session,
        invoices: InvoiceRepository,
        storage: FileStorage,
        reader: DocumentReader,
        provider: LLMProvider,
        normalizer: InvoiceNormalizer,
        grounder: ConfidenceGrounder,
        vendor_matching: VendorMatchingService,
        validation: ValidationService,
        audit: AuditService,
        max_attempts: int,
    ) -> None:
        self._session = session
        self._invoices = invoices
        self._storage = storage
        self._reader = reader
        self._provider = provider
        self._normalizer = normalizer
        self._grounder = grounder
        self._vendor_matching = vendor_matching
        self._validation = validation
        self._audit = audit
        self._max_attempts = max_attempts

    def process(self, invoice_id: uuid.UUID) -> ExtractionResult:
        invoice = self._invoices.get_for_update(invoice_id)
        if invoice is None or invoice.status not in (
            InvoiceStatus.QUEUED,
            InvoiceStatus.PROCESSING,
        ):
            self._session.rollback()
            return ExtractionResult(Outcome.SKIPPED)

        invoice.status = InvoiceStatus.PROCESSING
        invoice.extraction_attempts += 1
        attempt = invoice.extraction_attempts
        self._audit.record(
            AuditAction.EXTRACTION_STARTED,
            entity_type="invoice",
            entity_id=invoice.id,
            invoice_id=invoice.id,
            details={"attempt": attempt},
        )
        self._session.commit()

        started = time.perf_counter()
        try:
            content = self._reader.read(
                self._storage.read(invoice.storage_key), invoice.content_type
            )
            normalized, model = self._extract(content)
            invoice = self._reload(invoice_id)
            self._apply(invoice, content, normalized, model)
            self._vendor_matching.match(invoice)
            self._validation.validate(invoice)
            invoice.status = InvoiceStatus.NEEDS_REVIEW
            invoice.error_message = None
            invoice.version += 1
            self._audit.record(
                AuditAction.EXTRACTION_COMPLETED,
                entity_type="invoice",
                entity_id=invoice.id,
                invoice_id=invoice.id,
                details={
                    "method": content.method.value,
                    "pages": content.page_count,
                    "pages_processed": content.pages_processed,
                    "model": model,
                    "line_items": len(normalized.lines),
                    "errors": invoice.error_count,
                    "warnings": invoice.warning_count,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            self._session.commit()
            logger.info(
                "extraction completed",
                extra={
                    "invoice_id": str(invoice_id),
                    "method": content.method.value,
                    "duration_ms": round((time.perf_counter() - started) * 1000),
                },
            )
            return ExtractionResult(Outcome.COMPLETED, attempt)
        except DocumentError as exc:
            return self._fail(invoice_id, str(exc), attempt, reason="unreadable_document")
        except ProviderPermanentError as exc:
            return self._fail(
                invoice_id,
                f"{exc}. Click 'Retry extraction' to try again.",
                attempt,
                reason="provider_error",
            )
        except ProviderTransientError as exc:
            if attempt >= self._max_attempts:
                return self._fail(invoice_id, PROVIDER_DOWN_MESSAGE, attempt, reason=str(exc))
            self._session.rollback()
            invoice = self._reload(invoice_id)
            invoice.status = InvoiceStatus.QUEUED
            invoice.error_message = (
                f"AI service busy, retrying (attempt {attempt} of {self._max_attempts})."
            )
            self._session.commit()
            logger.warning(
                "extraction will retry", extra={"invoice_id": str(invoice_id), "attempt": attempt}
            )
            return ExtractionResult(Outcome.RETRY, attempt)
        except Exception:
            logger.exception("extraction crashed", extra={"invoice_id": str(invoice_id)})
            return self._fail(
                invoice_id,
                "Something went wrong while reading this bill. Click 'Retry extraction'.",
                attempt,
                reason="internal_error",
            )

    def _extract(self, content: DocumentContent) -> tuple[NormalizedInvoice, str]:
        if content.method == ExtractionMethod.TEXT_LAYER:
            extracted = self._provider.extract_from_text(content.text)
            normalized = self._normalizer.normalize(extracted)
            return self._grounder.ground(normalized, content.text), self._provider.text_model
        extracted = self._provider.extract_from_images(content.images)
        normalized = self._normalizer.normalize(extracted)
        # OCR-style reads are never certain, however confident the model claims to be.
        normalized.confidence = {
            k: min(v, VISION_CONFIDENCE_CAP) for k, v in normalized.confidence.items()
        }
        for line in normalized.lines:
            line.confidence = {k: min(v, VISION_CONFIDENCE_CAP) for k, v in line.confidence.items()}
        return normalized, self._provider.vision_model

    def _reload(self, invoice_id: uuid.UUID) -> Invoice:
        invoice = self._invoices.get_for_update(invoice_id)
        if invoice is None:  # deleted mid-flight; nothing sensible to do
            raise RuntimeError("invoice disappeared during extraction")
        return invoice

    def _apply(
        self,
        invoice: Invoice,
        content: DocumentContent,
        normalized: NormalizedInvoice,
        model: str,
    ) -> None:
        values = normalized.values
        invoice.page_count = content.page_count
        invoice.extraction_method = content.method
        invoice.vendor_name = cast(str | None, values["vendor_name"])
        invoice.vendor_gstin = cast(str | None, values["vendor_gstin"])
        invoice.buyer_gstin = cast(str | None, values["buyer_gstin"])
        invoice.invoice_number = cast(str | None, values["invoice_number"])
        invoice.invoice_date = cast(date | None, values["invoice_date"])
        invoice.due_date = cast(date | None, values["due_date"])
        invoice.subtotal = cast(Decimal | None, values["subtotal"])
        invoice.cgst = cast(Decimal | None, values["cgst"])
        invoice.sgst = cast(Decimal | None, values["sgst"])
        invoice.igst = cast(Decimal | None, values["igst"])
        invoice.total = cast(Decimal | None, values["total"])
        invoice.currency = normalized.currency
        invoice.field_confidence = dict(normalized.confidence)
        invoice.raw_extraction = {
            "provider": self._provider.name,
            "model": model,
            "method": content.method.value,
            "pages_processed": content.pages_processed,
            "unparsed_values": normalized.unparsed,
        }
        invoice.line_items = [
            InvoiceLineItem(
                company_id=invoice.company_id,
                position=line.position,
                description=line.description,
                hsn_sac=line.hsn_sac,
                quantity=line.quantity,
                rate=line.rate,
                amount=line.amount,
                confidence=line.confidence,
            )
            for line in normalized.lines
        ]

    def _fail(
        self, invoice_id: uuid.UUID, message: str, attempt: int, reason: str
    ) -> ExtractionResult:
        self._session.rollback()
        invoice = self._reload(invoice_id)
        invoice.status = InvoiceStatus.FAILED
        invoice.error_message = message
        invoice.version += 1
        self._audit.record(
            AuditAction.EXTRACTION_FAILED,
            entity_type="invoice",
            entity_id=invoice.id,
            invoice_id=invoice.id,
            details={"attempt": attempt, "reason": reason, "message": message},
        )
        self._session.commit()
        logger.warning("extraction failed", extra={"invoice_id": str(invoice_id), "reason": reason})
        return ExtractionResult(Outcome.FAILED, attempt)
