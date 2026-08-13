"""
Unit tests for Milestone 3 extraction schema + use case (Gemini mocked).
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.application.use_cases.extract_bill import ExtractBillUseCase
from app.application.use_cases.upload_bill import UploadBillCommand
from app.config.settings import get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ConfidenceLevel, ExtractedField
from app.infrastructure.storage.local_storage import LocalFileStorage


def _png_bytes(width: int = 40, height: int = 30) -> bytes:
    img = Image.new("RGB", (width, height), color=(20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1048576")
    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()


def test_extracted_field_confidence_levels():
    assert ExtractedField(value=None, confidence=0).level == ConfidenceLevel.MISSING
    assert ExtractedField(value=286, confidence=0.95).level == ConfidenceLevel.HIGH
    assert ExtractedField(value=286, confidence=0.7).level == ConfidenceLevel.MEDIUM
    assert ExtractedField(value=286, confidence=0.4).level == ConfidenceLevel.LOW


def test_electricity_bill_extraction_confidence_summary():
    extraction = ElectricityBillExtraction(
        units_consumed=ExtractedField(value=286, confidence=0.96, source="bill"),
        total_amount=ExtractedField(value=1840.5, confidence=0.7, source="bill"),
        rr_number=ExtractedField(value=None, confidence=0.0, source="unknown"),
    )
    summary = extraction.confidence_summary
    assert "units_consumed" in summary["HIGH"]
    assert "total_amount" in summary["MEDIUM"]
    assert "rr_number" in summary["MISSING"]
    assert "rr_number" in extraction.low_or_missing_critical_fields()
    assert "units_consumed" not in extraction.low_or_missing_critical_fields()


def test_extract_use_case_with_mocked_gemini(settings):
    fake_extraction = ElectricityBillExtraction(
        utility=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
        units_consumed=ExtractedField(value=222, confidence=0.98, source="bill"),
        total_amount=ExtractedField(value=1834.5, confidence=0.97, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.9, source="bill"),
        consumer_category=ExtractedField(
            value="Domestic", confidence=0.92, source="bill"
        ),
    )

    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake_extraction

    use_case = ExtractBillUseCase(
        settings=settings,
        extractor=mock_extractor,
        storage=LocalFileStorage(settings.upload_dir),
    )

    result = use_case.execute(
        UploadBillCommand(
            filename="sample.png",
            content_type="image/png",
            data=_png_bytes(),
        )
    )

    assert result.model_name == "gemini-2.5-flash"
    assert result.extraction.units_consumed.value == 222
    assert result.validation.bill.units_consumed.value == 222.0
    assert result.document.kind.value == "image"
    mock_extractor.extract_from_document.assert_called_once()
    # High confidence critical fields → not in needs_confirmation
    assert "units_consumed" not in result.needs_confirmation
