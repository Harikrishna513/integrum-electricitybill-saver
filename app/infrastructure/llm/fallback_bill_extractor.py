"""Try primary OCR provider, fall back to Gemini vision on failure."""

from __future__ import annotations

import logging

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.document import BillDocument, DocumentKind
from app.infrastructure.llm.bill_extractor import BillExtractionError

logger = logging.getLogger(__name__)


class FallbackBillExtractor:
    def __init__(self, primary, fallback) -> None:
        self._primary = primary
        self._fallback = fallback

    def extract_from_document(self, document: BillDocument) -> ElectricityBillExtraction:
        return self._run(
            lambda: self._primary.extract_from_document(document),
            lambda: self._fallback.extract_from_document(document),
        )

    def extract_from_bytes(
        self,
        *,
        data: bytes,
        content_type: str,
        kind: DocumentKind,
    ) -> ElectricityBillExtraction:
        return self._run(
            lambda: self._primary.extract_from_bytes(
                data=data, content_type=content_type, kind=kind
            ),
            lambda: self._fallback.extract_from_bytes(
                data=data, content_type=content_type, kind=kind
            ),
        )

    def _run(self, primary_fn, fallback_fn) -> ElectricityBillExtraction:
        try:
            return primary_fn()
        except BillExtractionError as exc:
            logger.warning("Primary bill extraction failed, using Gemini fallback: %s", exc)
            return fallback_fn()
