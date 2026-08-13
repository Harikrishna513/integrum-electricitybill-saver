"""
UploadBillDocumentUseCase — Milestone 2 orchestration.

CONCEPT
  One application use case:
    receive bytes → validate/inspect → store → return BillDocument

WHY A USE CASE CLASS
  Keeps the FastAPI route thin (Controller).
  Domain stays free of HTTP / FastAPI types.

SPRING ANALOGY
  @Service UploadBillService { Document upload(MultipartFile file); }

DATA FLOW
  UploadBillCommand
        │
        ▼
  LocalFileStorage.save
        │
        ▼
  build_bill_document (validate + inspect)
        │
        ▼
  BillDocument

NOTE
  We save first with a guessed extension from sniffed content type.
  If inspection fails after save, we delete the orphan file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.config.settings import Settings
from app.domain.models.document import BillDocument
from app.infrastructure.storage.bill_file_reader import (
    BillFileTooLargeError,
    EmptyBillFileError,
    UnsupportedBillFileError,
    build_bill_document,
    extension_for_content_type,
    sniff_content_type,
)
from app.infrastructure.storage.local_storage import LocalFileStorage


@dataclass(frozen=True)
class UploadBillCommand:
    """Input DTO for the use case (≈ method args / command object)."""

    filename: str
    content_type: str | None
    data: bytes


class UploadBillDocumentUseCase:
    def __init__(self, settings: Settings, storage: LocalFileStorage | None = None) -> None:
        self._settings = settings
        self._storage = storage or LocalFileStorage(settings.upload_dir)

    def execute(self, command: UploadBillCommand) -> BillDocument:
        content_type = sniff_content_type(command.filename, command.content_type)
        if content_type is None:
            raise UnsupportedBillFileError(
                "Could not determine file type. Upload JPG, PNG, WEBP, or PDF."
            )

        # Fail fast on size/empty before writing to disk
        if not command.data:
            raise EmptyBillFileError("Uploaded file is empty.")
        if len(command.data) > self._settings.max_upload_bytes:
            raise BillFileTooLargeError(
                f"File is {len(command.data)} bytes; "
                f"max allowed is {self._settings.max_upload_bytes} bytes."
            )
        if content_type not in self._settings.allowed_bill_content_types:
            raise UnsupportedBillFileError(
                f"Unsupported file type: {content_type}. "
                f"Allowed: {', '.join(sorted(self._settings.allowed_bill_content_types))}"
            )

        extension = extension_for_content_type(content_type)
        stored_filename, absolute_path = self._storage.save(command.data, extension)

        try:
            document = build_bill_document(
                data=command.data,
                original_filename=command.filename,
                declared_content_type=content_type,
                stored_filename=stored_filename,
                storage_path=str(absolute_path),
                allowed_content_types=self._settings.allowed_bill_content_types,
                max_upload_bytes=self._settings.max_upload_bytes,
            )
        except Exception:
            # Clean up orphan file if inspection fails
            path = Path(absolute_path)
            if path.exists():
                path.unlink()
            raise

        return document
