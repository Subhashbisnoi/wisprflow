from collections.abc import Callable

from app.features.extraction.providers.base import LLMProvider
from app.features.extraction.schemas import ExtractedField, ExtractedInvoice, ExtractedLineItem


def field(value: str | None, confidence: float = 0.9) -> ExtractedField:
    return ExtractedField(value=value, confidence=confidence)


def empty_invoice() -> ExtractedInvoice:
    blank = field(None, 0.0)
    return ExtractedInvoice(
        vendor_name=blank,
        vendor_gstin=blank,
        buyer_gstin=blank,
        invoice_number=blank,
        invoice_date=blank,
        due_date=blank,
        line_items=[],
        subtotal=blank,
        cgst=blank,
        sgst=blank,
        igst=blank,
        total=blank,
        currency=field("INR"),
    )


def line(description: str, qty: str, rate: str, amount: str, hsn: str = "") -> ExtractedLineItem:
    return ExtractedLineItem(
        description=field(description),
        hsn_sac=field(hsn or None),
        quantity=field(qty),
        rate=field(rate),
        amount=field(amount),
    )


class FakeProvider(LLMProvider):
    """Deterministic provider for tests and offline demos (D-051).

    `resolver` maps the document text (or None for images) to a result. When it returns None
    or no resolver is given, `default` is returned. Calls are recorded for assertions.
    """

    name = "fake"
    text_model = "fake-text"
    vision_model = "fake-vision"

    def __init__(
        self,
        default: ExtractedInvoice | None = None,
        resolver: Callable[[str | None], ExtractedInvoice | None] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.default = default or empty_invoice()
        self.resolver = resolver
        self.error = error
        self.calls: list[str] = []

    def _resolve(self, text: str | None) -> ExtractedInvoice:
        if self.error is not None:
            raise self.error
        if self.resolver is not None:
            result = self.resolver(text)
            if result is not None:
                return result
        return self.default

    def extract_from_text(self, text: str) -> ExtractedInvoice:
        self.calls.append("text")
        return self._resolve(text)

    def extract_from_images(self, images: list[bytes]) -> ExtractedInvoice:
        self.calls.append("vision")
        return self._resolve(None)
