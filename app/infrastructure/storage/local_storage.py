"""
Local filesystem storage for uploaded bills.

CONCEPT
  Save bytes to disk under a UUID filename; return the absolute path.

WHY IT EXISTS
  Keeps FastAPI routes thin. Later we can swap this for S3 without changing
  the upload use case interface much.

SPRING ANALOGY
  Like a FileStorageService / ResourceLoader adapter.

SECURITY
  - Never trust the client filename for the on-disk name (path traversal risk).
  - Store under UPLOAD_DIR only.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4


class LocalFileStorage:
    def __init__(self, upload_dir: str | Path) -> None:
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)

    def save(self, data: bytes, extension: str) -> tuple[str, Path]:
        """
        Persist bytes and return (stored_filename, absolute_path).

        extension should include the dot, e.g. ".jpg"
        """
        safe_ext = extension.lower() if extension.startswith(".") else f".{extension.lower()}"
        stored_filename = f"{uuid4().hex}{safe_ext}"
        path = self.upload_dir / stored_filename
        path.write_bytes(data)
        return stored_filename, path.resolve()

    def read_bytes(self, storage_path: str | Path) -> bytes:
        return Path(storage_path).read_bytes()
