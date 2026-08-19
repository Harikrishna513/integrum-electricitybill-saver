"""Mistral Document AI OCR — dedicated OCR API (not Pixtral chat)."""

from __future__ import annotations

import base64
import re
from typing import Any

from app.config.settings import Settings, get_settings
from app.domain.models.document import DocumentKind

# User-friendly aliases → official Mistral OCR model IDs
_OCR_MODEL_ALIASES: dict[str, str] = {
    "mistral-ocr-3.0": "mistral-ocr-latest",
    "mistral-ocr-3": "mistral-ocr-latest",
    "mistral-ocr-2512": "mistral-ocr-latest",
}

# Mistral markdown uses table placeholders like [tbl-0.md](tbl-0.md)
_TABLE_REF = re.compile(r"\[([^\]]+\.md)\]\(\1\)")


def resolve_mistral_ocr_model(model: str) -> str:
    return _OCR_MODEL_ALIASES.get(model.strip().lower(), model)


def ocr_document_bytes(
    *,
    data: bytes,
    content_type: str,
    kind: DocumentKind,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Run Mistral OCR and return raw API response dict.
    Pricing: ~$2 / 1,000 pages (not included in free token tier — rate-limited eval).
    """
    settings = settings or get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY is required for OCR")

    from mistralai.client import Mistral

    client = Mistral(api_key=settings.mistral_api_key.get_secret_value())
    model = resolve_mistral_ocr_model(settings.mistral_ocr_model)
    b64 = base64.b64encode(data).decode("utf-8")

    if kind == DocumentKind.PDF or content_type == "application/pdf":
        document: dict[str, Any] = {
            "type": "document_url",
            "document_url": f"data:application/pdf;base64,{b64}",
        }
    else:
        document = {
            "type": "image_url",
            "image_url": f"data:{content_type};base64,{b64}",
        }

    response = client.ocr.process(
        model=model,
        document=document,
        table_format="markdown",
    )
    if hasattr(response, "model_dump"):
        return response.model_dump(mode="json")
    if isinstance(response, dict):
        return response
    return {"pages": [], "model": model, "raw": str(response)}


def ocr_markdown_from_response(response: dict[str, Any]) -> str:
    """
    Build full OCR text for field parsing.

    Mistral often returns table data in pages[].tables / pages[].blocks while
    pages[].markdown only contains placeholder links — we merge everything so
    multilingual (Kannada, Hindi, etc.) bills retain meter readings and charges.
    """
    pages = response.get("pages") or []
    parts: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        page_text = _page_ocr_text(page)
        if page_text.strip():
            parts.append(page_text.strip())
    return "\n\n".join(parts).strip()


def _page_ocr_text(page: dict[str, Any]) -> str:
    sections: list[str] = []

    header = _text_content(page.get("header"))
    if header:
        sections.append(header)

    blocks = page.get("blocks") or []
    if blocks:
        sections.extend(_blocks_reading_order(blocks))
    else:
        markdown = str(page.get("markdown") or "")
        tables = page.get("tables") or []
        inlined = _inline_table_refs(markdown, tables)
        if inlined.strip():
            sections.append(inlined.strip())
        sections.extend(_tables_not_inlined(tables, inlined))

    footer = _text_content(page.get("footer"))
    if footer:
        sections.append(footer)

    return "\n\n".join(sections)


def _blocks_reading_order(blocks: list[Any]) -> list[str]:
    """Top-to-bottom, left-to-right; skip duplicate consecutive table bodies."""
    typed = [b for b in blocks if isinstance(b, dict)]
    ordered = sorted(
        typed,
        key=lambda b: (
            int(b.get("top_left_y") or 0),
            int(b.get("top_left_x") or 0),
        ),
    )
    out: list[str] = []
    prev: str | None = None
    for block in ordered:
        content = _text_content(block.get("content"))
        if not content or content == prev:
            continue
        out.append(content)
        prev = content
    return out


def _inline_table_refs(markdown: str, tables: list[Any]) -> str:
    by_id = {
        str(t["id"]): str(t["content"]).strip()
        for t in tables
        if isinstance(t, dict) and t.get("id") and t.get("content")
    }
    if not by_id:
        return markdown

    def _replace(match: re.Match[str]) -> str:
        table_id = match.group(1)
        return by_id.get(table_id, match.group(0))

    return _TABLE_REF.sub(_replace, markdown)


def _tables_not_inlined(tables: list[Any], inlined_markdown: str) -> list[str]:
    """Append table bodies that never appeared in markdown (safety net)."""
    extra: list[str] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        content = _text_content(table.get("content"))
        if content and content not in inlined_markdown:
            extra.append(content)
    return extra


def _text_content(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    if isinstance(value, dict):
        for key in ("content", "text", "markdown"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return None


# 1×1 white PNG — minimal payload for OCR connectivity smoke test
_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def ping_mistral_ocr(settings: Settings | None = None) -> dict[str, Any]:
    """Smoke-test Mistral OCR API (uses one page on your account)."""
    settings = settings or get_settings()
    model = resolve_mistral_ocr_model(settings.mistral_ocr_model)
    response = ocr_document_bytes(
        data=_TINY_PNG,
        content_type="image/png",
        kind=DocumentKind.IMAGE,
        settings=settings,
    )
    pages = len(response.get("pages") or [])
    return {
        "provider": "mistral_ocr",
        "model": response.get("model", model),
        "pages_processed": pages,
        "note": "OCR eval tier is rate-limited; production ~$2–4 per 1,000 pages.",
    }
