"""Detect uploaded file types from magic bytes, never from the filename (D-062)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class FileType:
    content_type: str
    extension: str


PDF = FileType("application/pdf", "pdf")
PNG = FileType("image/png", "png")
JPEG = FileType("image/jpeg", "jpg")
WEBP = FileType("image/webp", "webp")

ALLOWED_TYPES = (PDF, PNG, JPEG, WEBP)


def sniff_file_type(head: bytes) -> FileType | None:
    if head.startswith(b"%PDF-") or head[:1024].lstrip().startswith(b"%PDF-"):
        return PDF
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if head.startswith(b"\xff\xd8\xff"):
        return JPEG
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return WEBP
    return None
