from abc import ABC, abstractmethod

from app.features.extraction.schemas import ExtractedInvoice


class ProviderError(Exception):
    """Base class for LLM provider failures."""


class ProviderTransientError(ProviderError):
    """Timeouts, rate limits, 5xx: safe to retry later (D-049)."""


class ProviderPermanentError(ProviderError):
    """Auth errors, bad requests, unusable output: retrying will not help."""


class LLMProvider(ABC):
    """Hides the model vendor so it can be swapped (D-051)."""

    name: str
    text_model: str = ""
    vision_model: str = ""

    @abstractmethod
    def extract_from_text(self, text: str) -> ExtractedInvoice:
        """Structure an invoice from its PDF text layer."""

    @abstractmethod
    def extract_from_images(self, images: list[bytes]) -> ExtractedInvoice:
        """Structure an invoice from page images (JPEG bytes)."""
