"""Mistral Pixtral bill extractor — alternative to Gemini when rate-limited."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from pypdf import PdfReader

from app.config.settings import Settings, get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.document import BillDocument, DocumentKind
from app.infrastructure.llm.bill_extractor import BillExtractionError
from app.infrastructure.llm.extraction_prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
)
from app.infrastructure.llm.mistral_client import build_mistral_chat_model


class MistralBillExtractor:
    """Infrastructure adapter: BillDocument bytes → ElectricityBillExtraction via Pixtral."""

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
        model = build_mistral_chat_model(self._settings)
        structured = model.with_structured_output(
            ElectricityBillExtraction,
            method="json_schema",
        )

        user_text = EXTRACTION_USER_PROMPT
        content: list[dict | str] = [{"type": "text", "text": user_text}]

        if kind == DocumentKind.PDF or content_type == "application/pdf":
            pdf_text = _pdf_text(data)
            if pdf_text.strip():
                content[0] = {
                    "type": "text",
                    "text": (
                        f"{EXTRACTION_USER_PROMPT}\n\n"
                        f"PDF text layer (use with document if image also attached):\n{pdf_text[:12000]}"
                    ),
                }
            else:
                content[0] = {
                    "type": "text",
                    "text": (
                        f"{EXTRACTION_USER_PROMPT}\n\n"
                        "This PDF has no extractable text layer. "
                        "Upload a JPG/PNG photo of the bill for best results with Mistral."
                    ),
                }
        else:
            b64 = base64.b64encode(data).decode("utf-8")
            content.append(
                {
                    "type": "image_url",
                    "image_url": f"data:{content_type};base64,{b64}",
                }
            )

        messages = [
            SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
            HumanMessage(content=content),
        ]

        try:
            result = structured.invoke(messages)
        except Exception as exc:  # noqa: BLE001
            raise BillExtractionError(
                f"Mistral bill extraction failed: {type(exc).__name__}: {exc}"
            ) from exc

        if isinstance(result, ElectricityBillExtraction):
            return result
        if isinstance(result, dict):
            return ElectricityBillExtraction.model_validate(result)
        raise BillExtractionError(
            f"Unexpected structured output type: {type(result).__name__}"
        )


def _pdf_text(data: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(data))
        parts = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(parts)
    except Exception:
        return ""
