"""Opens invoice documents and decides between the text-layer and vision paths (D-052)."""

import io
import logging
from dataclasses import dataclass, field

import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PyPdfError

from app.features.invoices.models import ExtractionMethod

logger = logging.getLogger("app.extraction.reader")

MIN_TEXT_CHARS_PER_PAGE = 40
MAX_TEXT_CHARS = 60_000
MAX_VISION_PAGES = 5
RENDER_DPI = 150
MAX_IMAGE_EDGE = 2000


class DocumentError(Exception):
    """Base class for documents we cannot process. Message is shown to the user."""


class UnreadableDocumentError(DocumentError):
    pass


class PasswordProtectedDocumentError(DocumentError):
    pass


@dataclass
class DocumentContent:
    method: ExtractionMethod
    page_count: int
    text: str = ""
    images: list[bytes] = field(default_factory=list)

    @property
    def pages_processed(self) -> int:
        return self.page_count if self.method == ExtractionMethod.TEXT_LAYER else len(self.images)


UNREADABLE_MESSAGE = (
    "The file appears to be damaged or is not a valid {kind}. Please re-export or re-scan it "
    "and upload again."
)
PASSWORD_MESSAGE = (
    "This PDF is password-protected. Remove the password (for example, print it to a new PDF) "
    "and upload again."
)


class DocumentReader:
    def __init__(
        self,
        min_chars_per_page: int = MIN_TEXT_CHARS_PER_PAGE,
        max_vision_pages: int = MAX_VISION_PAGES,
    ) -> None:
        self._min_chars = min_chars_per_page
        self._max_pages = max_vision_pages

    def read(self, data: bytes, content_type: str) -> DocumentContent:
        if not data:
            raise UnreadableDocumentError("The file is empty.")
        if content_type == "application/pdf":
            return self._read_pdf(data)
        return self._read_image(data)

    # --- PDF ---------------------------------------------------------------------------------

    def _read_pdf(self, data: bytes) -> DocumentContent:
        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted and not reader.decrypt(""):
                raise PasswordProtectedDocumentError(PASSWORD_MESSAGE)
            page_count = len(reader.pages)
            if page_count == 0:
                raise UnreadableDocumentError("The PDF has no pages.")
            pages_text = [(page.extract_text() or "") for page in reader.pages]
        except DocumentError:
            raise
        except (PdfReadError, PyPdfError, ValueError, KeyError, TypeError, OSError) as exc:
            logger.info("pdf unreadable", extra={"error": type(exc).__name__})
            raise UnreadableDocumentError(UNREADABLE_MESSAGE.format(kind="PDF")) from exc

        meaningful_chars = sum(len("".join(t.split())) for t in pages_text)
        if meaningful_chars / page_count >= self._min_chars:
            text = "\n".join(
                f"--- Page {i} ---\n{t.strip()}" for i, t in enumerate(pages_text, start=1)
            )
            return DocumentContent(
                method=ExtractionMethod.TEXT_LAYER,
                page_count=page_count,
                text=text[:MAX_TEXT_CHARS],
            )

        return DocumentContent(
            method=ExtractionMethod.VISION,
            page_count=page_count,
            images=self._render_pdf(data, page_count),
        )

    def _render_pdf(self, data: bytes, page_count: int) -> list[bytes]:
        try:
            pdf = pdfium.PdfDocument(data)
            try:
                images = []
                for index in range(min(page_count, self._max_pages)):
                    bitmap = pdf[index].render(scale=RENDER_DPI / 72)
                    images.append(_to_jpeg(bitmap.to_pil()))
                return images
            finally:
                pdf.close()
        except pdfium.PdfiumError as exc:
            raise UnreadableDocumentError(UNREADABLE_MESSAGE.format(kind="PDF")) from exc

    # --- Images ------------------------------------------------------------------------------

    def _read_image(self, data: bytes) -> DocumentContent:
        try:
            with Image.open(io.BytesIO(data)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(data)) as img:
                img.load()
                jpeg = _to_jpeg(img)
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
            raise UnreadableDocumentError(UNREADABLE_MESSAGE.format(kind="image")) from exc
        return DocumentContent(method=ExtractionMethod.VISION, page_count=1, images=[jpeg])


def _to_jpeg(img: Image.Image) -> bytes:
    image = img.convert("RGB")
    image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return buffer.getvalue()
