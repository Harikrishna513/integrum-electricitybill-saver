"""
Bill document reader — validate + inspect upload bytes (no Gemini).

CONCEPT
  Given raw bytes + claimed content type + filename, produce a BillDocument
  after validation and light inspection (image size / PDF page count).

WHY SEPARATE FROM STORAGE
  Storage = where bytes live.
  Reader/inspector = are these bytes a usable bill file?

WHAT THIS IS NOT
  Not OCR. Not field extraction. That is Milestone 3.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.domain.models.document import BillDocument, DocumentKind


class UnsupportedBillFileError(ValueError):
    """File type or content is not accepted."""


class BillFileTooLargeError(ValueError):
    """Upload exceeds configured size limit."""


class EmptyBillFileError(ValueError):
    """Upload has zero bytes."""


_EXTENSION_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
}

_CONTENT_TYPE_BY_EXTENSION = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}


def sniff_content_type(filename: str, declared_content_type: str | None) -> str | None:
    """
    Prefer a trusted extension mapping; fall back to client-declared type.

    Real production systems often use libmagic. For learning we keep this simple.
    """
    suffix = Path(filename).suffix.lower()
    if suffix in _CONTENT_TYPE_BY_EXTENSION:
        return _CONTENT_TYPE_BY_EXTENSION[suffix]
    if declared_content_type and declared_content_type != "application/octet-stream":
        return declared_content_type
    return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inspect_image(data: bytes) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()  # integrity check
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size
            return width, height
    except UnidentifiedImageError as exc:
        raise UnsupportedBillFileError(
            "File claims to be an image but could not be opened as one."
        ) from exc


def inspect_pdf(data: bytes) -> int:
    try:
        reader = PdfReader(io.BytesIO(data))
        return len(reader.pages)
    except PdfReadError as exc:
        raise UnsupportedBillFileError(
            "File claims to be a PDF but could not be read as one."
        ) from exc


def build_bill_document(
    *,
    data: bytes,
    original_filename: str,
    declared_content_type: str | None,
    stored_filename: str,
    storage_path: str,
    allowed_content_types: frozenset[str],
    max_upload_bytes: int,
) -> BillDocument:
    """
    Validate bytes and build a BillDocument.

    Raises:
      EmptyBillFileError, BillFileTooLargeError, UnsupportedBillFileError
    """
    if not data:
        raise EmptyBillFileError("Uploaded file is empty.")

    if len(data) > max_upload_bytes:
        raise BillFileTooLargeError(
            f"File is {len(data)} bytes; max allowed is {max_upload_bytes} bytes."
        )

    content_type = sniff_content_type(original_filename, declared_content_type)
    if content_type is None or content_type not in allowed_content_types:
        raise UnsupportedBillFileError(
            f"Unsupported file type: {content_type or 'unknown'}. "
            f"Allowed: {', '.join(sorted(allowed_content_types))}"
        )

    width = height = page_count = None
    if content_type.startswith("image/"):
        kind = DocumentKind.IMAGE
        width, height = inspect_image(data)
    elif content_type == "application/pdf":
        kind = DocumentKind.PDF
        page_count = inspect_pdf(data)
    else:
        kind = DocumentKind.UNKNOWN

    return BillDocument(
        original_filename=original_filename,
        stored_filename=stored_filename,
        content_type=content_type,
        size_bytes=len(data),
        sha256=sha256_hex(data),
        kind=kind,
        storage_path=storage_path,
        width=width,
        height=height,
        page_count=page_count,
    )


def extension_for_content_type(content_type: str) -> str:
    return _EXTENSION_BY_CONTENT_TYPE.get(content_type, ".bin")
