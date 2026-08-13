"""
Tests for Milestone 4 — field coercion + bill extraction validation.
"""

from __future__ import annotations

import io
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from app.application.use_cases.extract_bill import ExtractBillUseCase
from app.application.use_cases.upload_bill import UploadBillCommand
from app.config.settings import get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ExtractedField
from app.domain.models.validated_bill import ParseStatus
from app.domain.services.bill_extraction_validator import BillExtractionValidator
from app.domain.services.field_coercion import (
    normalize_tariff_code,
    parse_bool,
    parse_date,
    parse_number,
)
from app.infrastructure.storage.local_storage import LocalFileStorage


def _png_bytes() -> bytes:
    img = Image.new("RGB", (40, 30), color=(20, 80, 160))
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


def test_parse_number_strips_currency_and_units():
    assert parse_number("₹1,834.50") == (1834.5, True)
    assert parse_number("286 units")[0] == 286.0
    assert parse_number(222) == (222.0, False)
    assert parse_number("abc")[0] is None


def test_parse_date_common_formats():
    d, raw, _ = parse_date("12/07/2026")
    assert d == date(2026, 7, 12)
    assert raw == "12/07/2026"

    d2, _, _ = parse_date("2026-07-12")
    assert d2 == date(2026, 7, 12)


def test_normalize_tariff_code():
    assert normalize_tariff_code("lt1") == "LT-1"
    assert normalize_tariff_code("LT-1") == "LT-1"
    assert normalize_tariff_code("LT 2a") == "LT-2A"


def test_parse_bool():
    assert parse_bool("true") == (True, False)
    assert parse_bool("yes")[0] is True
    assert parse_bool("0")[0] is False


def test_validator_coerces_messy_extraction():
    extraction = ElectricityBillExtraction(
        utility=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
        discom=ExtractedField(value="bescom", confidence=0.95, source="bill"),
        units_consumed=ExtractedField(value="286 units", confidence=0.96, source="bill"),
        total_amount=ExtractedField(value="₹1,834.50", confidence=0.97, source="bill"),
        bill_date=ExtractedField(value="12/07/2026", confidence=0.9, source="bill"),
        tariff_code=ExtractedField(value="LT1", confidence=0.9, source="bill"),
        previous_meter_reading=ExtractedField(value=1000, confidence=0.9, source="bill"),
        current_meter_reading=ExtractedField(value=1286, confidence=0.9, source="bill"),
        is_bescom_bill=ExtractedField(value="true", confidence=0.95, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.9, source="bill"),
        rr_number=ExtractedField(value="RR123", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="A1", confidence=0.9, source="bill"),
    )

    result = BillExtractionValidator().validate(extraction)

    assert result.bill.units_consumed.value == 286.0
    assert result.bill.units_consumed.coerced is True
    assert result.bill.total_amount.value == 1834.5
    assert result.bill.bill_date.value == date(2026, 7, 12)
    assert result.bill.tariff_code.value == "LT-1"
    assert result.bill.discom.value == "BESCOM"
    assert result.bill.is_bescom_bill.value is True
    assert result.is_usable_for_analysis is True
    assert result.error_count == 0


def test_validator_flags_negative_units():
    extraction = ElectricityBillExtraction(
        units_consumed=ExtractedField(value=-5, confidence=0.9, source="bill"),
        total_amount=ExtractedField(value=100, confidence=0.9, source="bill"),
    )
    result = BillExtractionValidator().validate(extraction)
    assert any(i.code == "NUMBER_OUT_OF_RANGE" for i in result.issues)
    assert result.bill.units_consumed.parse_status == ParseStatus.OUT_OF_RANGE
    assert result.is_usable_for_analysis is False


def test_validator_parse_failed_amount():
    extraction = ElectricityBillExtraction(
        units_consumed=ExtractedField(value=100, confidence=0.9, source="bill"),
        total_amount=ExtractedField(value="not-a-price", confidence=0.8, source="bill"),
    )
    result = BillExtractionValidator().validate(extraction)
    assert result.bill.total_amount.parse_status == ParseStatus.PARSE_FAILED
    assert "total_amount" in result.fields_needing_confirmation
    assert any(i.code == "NUMBER_PARSE_FAILED" for i in result.issues)


def test_extract_use_case_includes_validation(settings):
    fake_extraction = ElectricityBillExtraction(
        units_consumed=ExtractedField(value="222", confidence=0.98, source="bill"),
        total_amount=ExtractedField(value="₹1,834.50", confidence=0.97, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.9, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.9, source="bill"),
        rr_number=ExtractedField(value="RR1", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACC1", confidence=0.9, source="bill"),
        bill_date=ExtractedField(value="01/08/2026", confidence=0.9, source="bill"),
        previous_meter_reading=ExtractedField(value=1, confidence=0.9, source="bill"),
        current_meter_reading=ExtractedField(value=223, confidence=0.9, source="bill"),
        is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
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

    assert result.validation.bill.total_amount.value == 1834.5
    assert result.validation.is_usable_for_analysis is True
    assert isinstance(result.needs_confirmation, list)
