"""
Tests for Milestone 5 — consumer category classification.
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
from app.domain.models.category import ClassificationStatus, ConsumerCategory
from app.domain.models.extracted_field import ExtractedField
from app.domain.models.validated_bill import (
    CanonicalElectricityBill,
    ValidatedString,
    ParseStatus,
)
from app.domain.models.extracted_field import ConfidenceLevel
from app.domain.services.category_classifier import ConsumerCategoryClassifier
from app.infrastructure.storage.local_storage import LocalFileStorage


def _png_bytes() -> bytes:
    img = Image.new("RGB", (40, 30), color=(20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _validated_string(value: str | None, confidence: float = 0.95) -> ValidatedString:
    if value is None:
        return ValidatedString(
            value=None,
            raw=None,
            confidence=0.0,
            level=ConfidenceLevel.MISSING,
            parse_status=ParseStatus.MISSING,
        )
    level = (
        ConfidenceLevel.HIGH
        if confidence >= 0.85
        else ConfidenceLevel.MEDIUM
        if confidence >= 0.6
        else ConfidenceLevel.LOW
    )
    return ValidatedString(
        value=value,
        raw=value,
        confidence=confidence,
        level=level,
        source="bill",
        parse_status=ParseStatus.OK,
    )


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    get_settings.cache_clear()
    s = get_settings()
    yield s
    get_settings.cache_clear()


def test_classify_domestic_agreeing_signals():
    bill = CanonicalElectricityBill(
        tariff_code=_validated_string("LT-1"),
        consumer_category=_validated_string("Domestic / Residential"),
    )
    result = ConsumerCategoryClassifier().classify(bill)
    assert result.category == ConsumerCategory.DOMESTIC
    assert result.status == ClassificationStatus.CLASSIFIED
    assert result.supported_by_app_v1 is True
    assert result.can_continue_domestic_pipeline is True
    assert result.verification_status == "UNVERIFIED_HYPOTHESIS"


def test_classify_commercial_not_supported_in_v1():
    bill = CanonicalElectricityBill(
        tariff_code=_validated_string("LT-3"),
        consumer_category=_validated_string("Commercial"),
    )
    result = ConsumerCategoryClassifier().classify(bill)
    assert result.category == ConsumerCategory.COMMERCIAL
    assert result.supported_by_app_v1 is False
    assert result.can_continue_domestic_pipeline is False
    assert "Domestic / Residential" in result.user_message


def test_classify_conflict_does_not_guess():
    bill = CanonicalElectricityBill(
        tariff_code=_validated_string("LT-3"),
        consumer_category=_validated_string("Residential"),
    )
    result = ConsumerCategoryClassifier().classify(bill)
    assert result.status == ClassificationStatus.CATEGORY_CONFLICT
    assert result.category == ConsumerCategory.UNKNOWN
    assert result.requires_user_confirmation is True
    assert ConsumerCategory.COMMERCIAL in result.conflicting_categories
    assert ConsumerCategory.DOMESTIC in result.conflicting_categories


def test_classify_insufficient_evidence():
    bill = CanonicalElectricityBill()
    result = ConsumerCategoryClassifier().classify(bill)
    assert result.status == ClassificationStatus.INSUFFICIENT_EVIDENCE
    assert result.category == ConsumerCategory.UNKNOWN
    assert result.supported_by_app_v1 is False


def test_extract_use_case_includes_classification(settings):
    fake_extraction = ElectricityBillExtraction(
        units_consumed=ExtractedField(value=222, confidence=0.98, source="bill"),
        total_amount=ExtractedField(value=1834.5, confidence=0.97, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.95, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.95, source="bill"),
        rr_number=ExtractedField(value="RR1", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACC1", confidence=0.9, source="bill"),
        bill_date=ExtractedField(value="01/08/2026", confidence=0.9, source="bill"),
        previous_meter_reading=ExtractedField(value=1, confidence=0.9, source="bill"),
        current_meter_reading=ExtractedField(value=223, confidence=0.9, source="bill"),
        is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
    )
    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake_extraction

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

    assert result.classification.category == ConsumerCategory.DOMESTIC
    assert result.classification.can_continue_domestic_pipeline is True
