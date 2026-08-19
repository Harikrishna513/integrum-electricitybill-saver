"""
Tests for Milestone 6 — bill consistency validation.
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
from app.domain.models.consistency import ConsistencyStatus
from app.domain.models.extracted_field import ConfidenceLevel, ExtractedField
from app.domain.models.validated_bill import (
    CanonicalElectricityBill,
    ParseStatus,
    ValidatedNumber,
)
from app.domain.services.bill_consistency_validator import BillConsistencyValidator
from app.infrastructure.storage.local_storage import LocalFileStorage


def _num(value: float | None, confidence: float = 0.95) -> ValidatedNumber:
    if value is None:
        return ValidatedNumber(
            value=None,
            confidence=0.0,
            level=ConfidenceLevel.MISSING,
            parse_status=ParseStatus.MISSING,
        )
    return ValidatedNumber(
        value=value,
        raw=value,
        confidence=confidence,
        level=ConfidenceLevel.HIGH,
        source="bill",
        parse_status=ParseStatus.OK,
    )


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
    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()


def test_consistent_readings_and_units():
    bill = CanonicalElectricityBill(
        previous_meter_reading=_num(1000),
        current_meter_reading=_num(1286),
        units_consumed=_num(286),
        total_amount=_num(1800),
    )
    result = BillConsistencyValidator().validate(bill)
    assert result.status == ConsistencyStatus.CONSISTENT
    assert result.reading_delta == 286
    assert result.has_discrepancy is False


def test_meter_reading_mismatch_is_discrepancy_not_overcharge():
    bill = CanonicalElectricityBill(
        previous_meter_reading=_num(1200),
        current_meter_reading=_num(1400),
        units_consumed=_num(250),
    )
    result = BillConsistencyValidator().validate(bill)
    assert result.status == ConsistencyStatus.DISCREPANCY_DETECTED
    assert any(i.code == "POTENTIAL_METER_READING_MISMATCH" for i in result.issues)
    issue = next(i for i in result.issues if i.code == "POTENTIAL_METER_READING_MISMATCH")
    assert issue.expected_value == 200
    assert issue.observed_value == 250
    assert "overcharg" not in issue.message.lower()
    assert "verified" in issue.message.lower() or "verify" in issue.message.lower()
    assert "discrepancy" in issue.message.lower()
    assert "units_consumed" in result.fields_needing_confirmation


def test_current_before_previous():
    bill = CanonicalElectricityBill(
        previous_meter_reading=_num(5000),
        current_meter_reading=_num(100),
        units_consumed=_num(100),
    )
    result = BillConsistencyValidator().validate(bill)
    assert result.has_discrepancy is True
    assert any(i.code == "CURRENT_READING_BEFORE_PREVIOUS" for i in result.issues)


def test_insufficient_data_when_readings_missing():
    bill = CanonicalElectricityBill(units_consumed=_num(200))
    result = BillConsistencyValidator().validate(bill)
    assert result.status == ConsistencyStatus.INSUFFICIENT_DATA
    assert "meter_reading_vs_units" in result.checks_skipped


def test_charge_sum_soft_mismatch():
    bill = CanonicalElectricityBill(
        energy_charge=_num(1000),
        fixed_charge=_num(200),
        total_amount=_num(1500),
        previous_meter_reading=_num(10),
        current_meter_reading=_num(20),
        units_consumed=_num(10),
    )
    result = BillConsistencyValidator().validate(bill)
    assert any(i.code == "POTENTIAL_CHARGE_TOTAL_MISMATCH" for i in result.issues)
    assert "total_amount" in result.fields_needing_confirmation
    msg = next(
        i for i in result.issues if i.code == "POTENTIAL_CHARGE_TOTAL_MISMATCH"
    ).message
    assert "billing error" in msg.lower() or "net payable" in msg.lower()
    assert "overcharg" not in msg.lower()


def test_extract_use_case_includes_consistency(settings):
    fake = ElectricityBillExtraction(
        units_consumed=ExtractedField(value=250, confidence=0.98, source="bill"),
        previous_meter_reading=ExtractedField(value=1200, confidence=0.98, source="bill"),
        current_meter_reading=ExtractedField(value=1400, confidence=0.98, source="bill"),
        total_amount=ExtractedField(value=1800, confidence=0.97, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.95, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.95, source="bill"),
        rr_number=ExtractedField(value="RR1", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACC1", confidence=0.9, source="bill"),
        bill_date=ExtractedField(value="01/08/2026", confidence=0.9, source="bill"),
        is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
    )
    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake

    result = ExtractBillUseCase(
        settings=settings,
        extractor=mock_extractor,
        storage=LocalFileStorage(settings.upload_dir),
    ).execute(
        UploadBillCommand(
            filename="sample.png",
            content_type="image/png",
            data=_png_bytes(),
        )
    )

    assert result.consistency.status == ConsistencyStatus.DISCREPANCY_DETECTED
    assert "units_consumed" in result.needs_confirmation
