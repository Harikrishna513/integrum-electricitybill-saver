"""
Tests for Milestone 2 — upload / read bill files (no Gemini).
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

from app.application.use_cases.upload_bill import (
    UploadBillCommand,
    UploadBillDocumentUseCase,
)
from app.config.settings import Settings, get_settings
from app.domain.models.document import DocumentKind
from app.infrastructure.storage.bill_file_reader import (
    BillFileTooLargeError,
    EmptyBillFileError,
    UnsupportedBillFileError,
)
from app.infrastructure.storage.local_storage import LocalFileStorage


def _png_bytes(width: int = 40, height: int = 30) -> bytes:
    img = Image.new("RGB", (width, height), color=(20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pdf_bytes() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1048576")
    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()


@pytest.fixture
def use_case(settings: Settings) -> UploadBillDocumentUseCase:
    storage = LocalFileStorage(settings.upload_dir)
    return UploadBillDocumentUseCase(settings, storage)


def test_upload_png_returns_image_metadata(use_case: UploadBillDocumentUseCase):
    data = _png_bytes(64, 48)
    doc = use_case.execute(
        UploadBillCommand(
            filename="bescom_bill.png",
            content_type="image/png",
            data=data,
        )
    )

    assert doc.kind == DocumentKind.IMAGE
    assert doc.content_type == "image/png"
    assert doc.width == 64
    assert doc.height == 48
    assert doc.size_bytes == len(data)
    assert len(doc.sha256) == 64
    assert Path(doc.storage_path).exists()
    assert doc.stored_filename.endswith(".png")
    # On-disk name must not be the original filename (PII / traversal safety)
    assert doc.stored_filename != "bescom_bill.png"


def test_upload_pdf_returns_page_count(use_case: UploadBillDocumentUseCase):
    data = _pdf_bytes()
    doc = use_case.execute(
        UploadBillCommand(
            filename="bill.pdf",
            content_type="application/pdf",
            data=data,
        )
    )

    assert doc.kind == DocumentKind.PDF
    assert doc.page_count == 1
    assert Path(doc.storage_path).exists()


def test_reject_empty_file(use_case: UploadBillDocumentUseCase):
    with pytest.raises(EmptyBillFileError):
        use_case.execute(
            UploadBillCommand(
                filename="empty.png",
                content_type="image/png",
                data=b"",
            )
        )


def test_reject_too_large(use_case: UploadBillDocumentUseCase, settings: Settings):
    data = b"x" * (settings.max_upload_bytes + 1)
    with pytest.raises(BillFileTooLargeError):
        use_case.execute(
            UploadBillCommand(
                filename="huge.png",
                content_type="image/png",
                data=data,
            )
        )


def test_reject_unsupported_type(use_case: UploadBillDocumentUseCase):
    with pytest.raises(UnsupportedBillFileError):
        use_case.execute(
            UploadBillCommand(
                filename="notes.txt",
                content_type="text/plain",
                data=b"hello",
            )
        )


def test_reject_fake_png_bytes(use_case: UploadBillDocumentUseCase, settings: Settings):
    with pytest.raises(UnsupportedBillFileError):
        use_case.execute(
            UploadBillCommand(
                filename="fake.png",
                content_type="image/png",
                data=b"not-an-image",
            )
        )
    # Orphan file should be cleaned up
    uploads = list(Path(settings.upload_dir).glob("*"))
    assert uploads == []
