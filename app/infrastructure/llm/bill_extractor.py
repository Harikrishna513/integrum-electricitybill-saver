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
from app.infrastructure.llm.gemini_client import build_chat_model

EXTRACTION_SYSTEM_PROMPT = """
You are an expert at reading Karnataka electricity bills, especially BESCOM bills.

Your job is ONLY to extract fields that are visible or clearly labeled on the document.

Rules:
1. Do NOT calculate charges, tariffs, subsidies, or totals yourself.
2. Do NOT invent missing values. If a field is not readable, set value=null and confidence=0.
3. Prefer source="bill" when the value is printed on the document.
4. Use source="inferred" only if you must lightly normalize an obvious label (rare). Prefer null over guessing.
5. confidence must reflect readability: sharp clear text ~0.9+, slightly unclear ~0.6-0.8, guessy <0.6.
6. Keep printed date/period text as shown; do not convert timezones.
7. For is_bescom_bill.value use "true" or "false" as a string.
8. If the document is not an electricity bill, still fill what you can and note that in extraction_notes.
""".strip()

EXTRACTION_USER_PROMPT = """
Extract structured fields from this electricity bill document into the schema.

Focus on BESCOM / Karnataka residential bills when applicable.
Return confidence for every field.
""".strip()


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
