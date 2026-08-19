"""Bill extraction: Mistral OCR 3 → Gemini field parsing."""

from __future__ import annotations

from pathlib import Path

from app.config.settings import Settings, get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.document import BillDocument, DocumentKind
from app.infrastructure.llm.bill_extractor import BillExtractionError
from app.infrastructure.llm.bill_text_parser import parse_bill_from_ocr_text
from app.infrastructure.llm.mistral_ocr_client import (
    ocr_document_bytes,
    ocr_markdown_from_response,
    resolve_mistral_ocr_model,
)


class MistralOcrBillExtractor:
    """Mistral Document AI OCR for reading; Gemini for structured bill fields."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def extract_from_document(self, document: BillDocument) -> ElectricityBillExtraction:
        data = Path(document.storage_path).read_bytes()
        return self.extract_from_bytes(
            data=data,
            content_type=document.content_type,
            kind=document.kind,
        )

    def extract_from_bytes(
        self,
        *,
        data: bytes,
        content_type: str,
        kind: DocumentKind,
    ) -> ElectricityBillExtraction:
        model = resolve_mistral_ocr_model(self._settings.mistral_ocr_model)
        try:
            ocr_response = ocr_document_bytes(
                data=data,
                content_type=content_type,
                kind=kind,
                settings=self._settings,
            )
        except Exception as exc:  # noqa: BLE001
            raise BillExtractionError(
                f"Mistral OCR failed ({model}): {type(exc).__name__}: {exc}"
            ) from exc

        markdown = ocr_markdown_from_response(ocr_response)
        if not markdown:
            raise BillExtractionError(
                f"Mistral OCR ({model}) returned no text. "
                "Try a clearer JPG/PNG or enable Gemini fallback."
            )

        return parse_bill_from_ocr_text(
            markdown,
            settings=self._settings,
            source_label=f"Mistral OCR ({ocr_response.get('model', model)})",
        )
