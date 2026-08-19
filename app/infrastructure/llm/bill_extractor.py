"""
Gemini Vision bill extractor (Milestone 3).

CONCEPT
  Send bill image/PDF + extraction instructions to Gemini.
  Force the reply into ElectricityBillExtraction via structured output.

WHY LANGCHAIN HERE
  with_structured_output + multimodal HumanMessage is exactly what LangChain
  is good at. Tariff math still stays in plain Python later.

WHAT MUST NOT HAPPEN
  Do not ask Gemini to calculate tariffs or savings.
  Only extract what the bill appears to show.

SPRING ANALOGY
  Like an OcrAdapter implementing BillExtractorPort.
"""

from __future__ import annotations

import base64
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from app.config.settings import Settings, get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.document import BillDocument, DocumentKind
from app.infrastructure.llm.extraction_prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
)
from app.infrastructure.llm.gemini_client import build_chat_model


class BillExtractionError(RuntimeError):
    """Gemini extraction failed or returned unusable output."""


class GeminiBillExtractor:
    """Infrastructure adapter: BillDocument bytes → ElectricityBillExtraction."""

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
        model = build_chat_model(self._settings)
        structured = model.with_structured_output(
            ElectricityBillExtraction,
            method="json_schema",
        )

        media_part = self._build_media_part(data=data, content_type=content_type, kind=kind)
        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(
                content=[
                    {"type": "text", "text": EXTRACTION_USER_PROMPT},
                    media_part,
                ]
            ),
        ]

        try:
            result = structured.invoke(messages)
        except Exception as exc:  # noqa: BLE001 — surface provider errors for learning
            raise BillExtractionError(
                f"Gemini bill extraction failed: {type(exc).__name__}: {exc}"
            ) from exc

        if isinstance(result, ElectricityBillExtraction):
            return result
        if isinstance(result, dict):
            return ElectricityBillExtraction.model_validate(result)
        raise BillExtractionError(
            f"Unexpected structured output type: {type(result).__name__}"
        )

    def _build_media_part(
        self,
        *,
        data: bytes,
        content_type: str,
        kind: DocumentKind,
    ) -> dict:
        b64 = base64.b64encode(data).decode("utf-8")

        if kind == DocumentKind.PDF or content_type == "application/pdf":
            # Modern LangChain multimodal PDF part
            return {
                "type": "file",
                "source_type": "base64",
                "mime_type": "application/pdf",
                "data": b64,
            }

        # Images: data-URI image_url
        return {
            "type": "image_url",
            "image_url": f"data:{content_type};base64,{b64}",
        }
