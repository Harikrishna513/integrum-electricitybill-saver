"""Select bill OCR provider from settings."""

from __future__ import annotations

from typing import Protocol

from app.config.settings import Settings, get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.document import BillDocument, DocumentKind
from app.infrastructure.llm.bill_extractor import GeminiBillExtractor
from app.infrastructure.llm.fallback_bill_extractor import FallbackBillExtractor
from app.infrastructure.llm.mistral_bill_extractor import MistralBillExtractor
from app.infrastructure.llm.mistral_ocr_bill_extractor import MistralOcrBillExtractor


class BillExtractorPort(Protocol):
    def extract_from_document(self, document: BillDocument) -> ElectricityBillExtraction: ...

    def extract_from_bytes(
        self,
        *,
        data: bytes,
        content_type: str,
        kind: DocumentKind,
    ) -> ElectricityBillExtraction: ...


def get_bill_extractor(settings: Settings | None = None) -> BillExtractorPort:
    settings = settings or get_settings()
    provider = settings.bill_extraction_provider
    gemini_fallback = GeminiBillExtractor(settings)

    if provider == "mistral_ocr":
        primary = MistralOcrBillExtractor(settings)
        if settings.bill_extraction_fallback and settings.gemini_api_key:
            return FallbackBillExtractor(primary, gemini_fallback)
        return primary

    if provider == "mistral":
        primary = MistralBillExtractor(settings)
        if settings.bill_extraction_fallback and settings.gemini_api_key:
            return FallbackBillExtractor(primary, gemini_fallback)
        return primary

    return gemini_fallback
