"""Tests for Mistral OCR markdown assembly (tables + multilingual blocks)."""

from __future__ import annotations

import json
from pathlib import Path

from app.infrastructure.llm.mistral_ocr_client import ocr_markdown_from_response

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "mistral_ocr_kannada_page.json"


def test_ocr_markdown_includes_table_blocks_not_only_placeholders():
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    md = ocr_markdown_from_response(payload)
    assert len(md) > 500
    assert "ಬಳಕೆ" in md
    assert "248" in md
    assert "ಹಾಲಿ ಮಾಪನ" in md
    assert "12996" in md
    assert "12748" in md
    assert "2607" in md
    assert "[tbl-0.md]" not in md


def test_inline_table_refs_when_no_blocks():
    payload = {
        "pages": [
            {
                "markdown": "Header\n[tbl-0.md](tbl-0.md)\nFooter 100",
                "tables": [
                    {
                        "id": "tbl-0.md",
                        "content": "| Units | 42 |\n| --- | --- |",
                    }
                ],
            }
        ]
    }
    md = ocr_markdown_from_response(payload)
    assert "| Units | 42 |" in md
    assert "[tbl-0.md]" not in md
    assert "Footer 100" in md
