"""Smoke-test Mistral Document AI OCR + optional bill file."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app.config.settings import get_settings
    from app.infrastructure.llm.mistral_ocr_client import (
        ocr_document_bytes,
        ocr_markdown_from_response,
        ping_mistral_ocr,
        resolve_mistral_ocr_model,
    )

    settings = get_settings()
    model = resolve_mistral_ocr_model(settings.mistral_ocr_model)

    print("=" * 60)
    print("MISTRAL OCR SMOKE TEST")
    print("=" * 60)
    print(f"provider : {settings.bill_extraction_provider}")
    print(f"ocr_model: {model}")
    print(f"fallback : {settings.bill_extraction_fallback}")
    print(f"parser   : {settings.gemini_model}")

    try:
        ping = ping_mistral_ocr(settings)
        print("ping     : OK", ping)
    except Exception as exc:  # noqa: BLE001
        print(f"ping     : FAILED — {type(exc).__name__}: {exc}")
        return 1

    if len(sys.argv) >= 2:
        path = Path(sys.argv[1])
        if not path.exists():
            print(f"File not found: {path}")
            return 1
        from app.domain.models.document import DocumentKind

        content_type = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"
        kind = DocumentKind.PDF if content_type == "application/pdf" else DocumentKind.IMAGE
        data = path.read_bytes()
        print(f"\nOCR file : {path} ({len(data)} bytes)")
        response = ocr_document_bytes(
            data=data,
            content_type=content_type,
            kind=kind,
            settings=settings,
        )
        md = ocr_markdown_from_response(response)
        print(f"pages    : {len(response.get('pages') or [])}")
        print(f"markdown : {len(md)} chars")
        print("-" * 40)
        print(md[:3000] or "(empty)")
        if len(md) > 3000:
            print("... (truncated)")

    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
