"""Parse OCR text into structured bill fields — uses Gemini (text-only, not vision)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.config.settings import Settings, get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.infrastructure.llm.bill_extractor import BillExtractionError
from app.infrastructure.llm.extraction_prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    EXTRACTION_USER_PROMPT,
)
from app.domain.models.extracted_field import ExtractedField
from app.domain.services.bill_identity_guards import scrub_misplaced_identity_fields
from app.infrastructure.llm.gemini_client import build_chat_model


def parse_bill_from_ocr_text(
    ocr_text: str,
    *,
    settings: Settings | None = None,
    source_label: str = "Mistral OCR",
) -> ElectricityBillExtraction:
    """Turn OCR markdown into ElectricityBillExtraction via Gemini structured output."""
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise BillExtractionError(
            "GEMINI_API_KEY is required to parse OCR text into bill fields."
        )
    if not ocr_text.strip():
        raise BillExtractionError(f"{source_label} returned empty text.")

    model = build_chat_model(settings)
    structured = model.with_structured_output(
        ElectricityBillExtraction,
        method="json_schema",
    )
    user_prompt = (
        f"{EXTRACTION_USER_PROMPT}\n\n"
        f"The bill text below was extracted by {source_label}. "
        "Use only what appears in the text; do not calculate tariffs.\n\n"
        f"--- OCR TEXT START ---\n{ocr_text[:20000]}\n--- OCR TEXT END ---"
    )
    messages = [
        SystemMessage(content=EXTRACTION_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]
    try:
        result = structured.invoke(messages)
    except Exception as exc:  # noqa: BLE001
        raise BillExtractionError(
            f"Bill field parsing failed: {type(exc).__name__}: {exc}"
        ) from exc

    if isinstance(result, ElectricityBillExtraction):
        extraction = result
    elif isinstance(result, dict):
        extraction = ElectricityBillExtraction.model_validate(result)
    else:
        raise BillExtractionError(f"Unexpected parser output: {type(result).__name__}")

    extraction = scrub_misplaced_identity_fields(extraction, ocr_text=ocr_text)

    note = f"Fields parsed from {source_label} text via {settings.gemini_model}."
    if extraction.extraction_notes.value:
        extraction.extraction_notes.value = f"{extraction.extraction_notes.value} {note}"
    else:
        extraction.extraction_notes = ExtractedField(value=note, confidence=0.9, source="inferred")
    return extraction
