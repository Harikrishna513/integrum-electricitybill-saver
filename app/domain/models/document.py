from datetime import datetime, timezone
from enum import Enum
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class DocumentKind(str, Enum):
    IMAGE = "image"
    PDF = "pdf"
    UNKNOWN = "unknown"


class BillDocument(BaseModel):
    """
    Canonical representation of an uploaded bill file.

    PII note:
      original_filename may contain personal info — do not log it in production.
      stored_filename is a UUID-based safe name on disk.
    """

    id: UUID = Field(default_factory=uuid4)
    original_filename: str
    stored_filename: str
    content_type: str
    size_bytes: int
    sha256: str
    kind: DocumentKind
    storage_path: str
    width: int | None = None
    height: int | None = None
    page_count: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_image(self) -> bool:
        return self.kind == DocumentKind.IMAGE

    @property
    def is_pdf(self) -> bool:
        return self.kind == DocumentKind.PDF
