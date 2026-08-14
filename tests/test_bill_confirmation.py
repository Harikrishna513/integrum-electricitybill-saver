"""
Tests for Milestone 24 — user confirmation / field correction.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.application.use_cases.confirm_bill import ConfirmBillUseCase
from app.application.use_cases.extract_bill import ExtractBillUseCase
from app.application.use_cases.upload_bill import UploadBillCommand
from app.config.settings import get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.category import ConsumerCategory
from app.domain.models.confirmation import BillConfirmationRequest
from app.domain.models.extracted_field import ExtractedField
from app.domain.services.bill_confirmation import BillConfirmationError
from app.infrastructure.persistence.db import Base, create_db_engine, reset_db_engine_for_tests
from app.infrastructure.persistence.repository import BillAnalysisRepository
from app.infrastructure.storage.local_storage import LocalFileStorage
from tests.fixtures.bescom_extraction import complete_bescom_extraction


def _png_bytes() -> bytes:
    img = Image.new("RGB", (40, 30), color=(20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    db_path = tmp_path / "confirm.db"
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_engine_for_tests()

    from app.config.settings import Settings

    settings = Settings()
    engine = create_db_engine(settings)
    from app.infrastructure.persistence import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(
        bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    session = factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()
        get_settings.cache_clear()
        reset_db_engine_for_tests()


def _extract_weak_bill(db_session: Session, tmp_path: Path):
    settings = get_settings()
    fake = complete_bescom_extraction(
        units_consumed=ExtractedField(value=280, confidence=0.4, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.5, source="bill"),
        rr_number=ExtractedField(value="RRCONF1", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACCCONF1", confidence=0.9, source="bill"),
    )
    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake

    repo = BillAnalysisRepository(db_session)
    use_case = ExtractBillUseCase(
        settings=settings,
        extractor=mock_extractor,
        repository=repo,
        storage=LocalFileStorage(settings.upload_dir),
    )
    result = use_case.execute(
        UploadBillCommand(
            filename="weak.png",
            content_type="image/png",
            data=_png_bytes(),
        )
    )
    return result, repo


def test_confirm_corrects_units_and_unlocks_gate(db_session: Session, tmp_path: Path):
    extracted, repo = _extract_weak_bill(db_session, tmp_path)
    assert extracted.analysis_id
    assert "units_consumed" in extracted.needs_confirmation

    confirm = ConfirmBillUseCase(repo)
    result = confirm.execute(
        extracted.analysis_id,
        BillConfirmationRequest(
            corrections={"units_consumed": 286},
            confirm_category=ConsumerCategory.DOMESTIC,
            note="Verified against printed bill",
        ),
    )

    assert result.stored.units_consumed == 286.0
    assert result.extraction.units_consumed.source == "user"
    assert result.extraction.units_consumed.confidence == 1.0
    assert result.classification.category == ConsumerCategory.DOMESTIC
    assert result.classification.requires_user_confirmation is False
    assert result.classification.can_continue_domestic_pipeline is True
    assert "units_consumed" not in result.needs_confirmation

    reloaded = repo.get_by_id(extracted.analysis_id)
    assert reloaded is not None
    assert reloaded.units_consumed == 286.0
    assert reloaded.notes == "Verified against printed bill"


def test_accept_as_printed_bumps_confidence(db_session: Session, tmp_path: Path):
    extracted, repo = _extract_weak_bill(db_session, tmp_path)
    confirm = ConfirmBillUseCase(repo)
    result = confirm.execute(
        extracted.analysis_id,
        BillConfirmationRequest(
            accept_extracted_as_printed=["units_consumed"],
            confirm_category=ConsumerCategory.DOMESTIC,
        ),
    )
    assert result.extraction.units_consumed.value == 280
    assert result.extraction.units_consumed.confidence == 1.0
    assert "units_consumed" in result.confirmation.fields_accepted_as_printed


def test_confirm_clears_charge_mismatch_after_user_attestation(db_session: Session, tmp_path: Path):
    """INFO-level charge/total mismatch should not block confirm after user attests."""
    settings = get_settings()
    fake = complete_bescom_extraction(
        units_consumed=ExtractedField(value=59, confidence=0.95, source="bill"),
        previous_meter_reading=ExtractedField(value=2370, confidence=0.95, source="bill"),
        current_meter_reading=ExtractedField(value=2429, confidence=0.95, source="bill"),
        energy_charge=ExtractedField(value=342.3, confidence=0.95, source="bill"),
        fixed_charge=ExtractedField(value=150, confidence=0.95, source="bill"),
        electricity_tax=ExtractedField(value=30.8, confidence=0.95, source="bill"),
        fppca=ExtractedField(value=22.42, confidence=0.95, source="bill"),
        other_charges=ExtractedField(value=20.65, confidence=0.95, source="bill"),
        subsidy=ExtractedField(value=91.68, confidence=0.95, source="bill"),
        total_amount=ExtractedField(value=73, confidence=0.95, source="bill"),
        rr_number=ExtractedField(value="RR-CHG", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACC-CHG", confidence=0.9, source="bill"),
    )
    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake
    repo = BillAnalysisRepository(db_session)
    use_case = ExtractBillUseCase(
        settings=settings,
        extractor=mock_extractor,
        repository=repo,
        storage=LocalFileStorage(settings.upload_dir),
    )
    extracted = use_case.execute(
        UploadBillCommand(filename="may.png", content_type="image/png", data=_png_bytes())
    )
    assert extracted.analysis_id
    assert any(
        i.code == "POTENTIAL_CHARGE_TOTAL_MISMATCH" for i in extracted.consistency.issues
    )

    confirm = ConfirmBillUseCase(repo)
    result = confirm.execute(
        extracted.analysis_id,
        BillConfirmationRequest(
            accept_extracted_as_printed=[
                "energy_charge",
                "fixed_charge",
                "electricity_tax",
                "fppca",
                "other_charges",
                "subsidy",
                "total_amount",
            ],
            confirm_category=ConsumerCategory.DOMESTIC,
        ),
    )
    assert result.needs_confirmation == []


def test_confirm_rejects_empty_payload(db_session: Session, tmp_path: Path):
    extracted, repo = _extract_weak_bill(db_session, tmp_path)
    confirm = ConfirmBillUseCase(repo)
    with pytest.raises(BillConfirmationError):
        confirm.execute(extracted.analysis_id, BillConfirmationRequest())


def test_confirm_unknown_field(db_session: Session, tmp_path: Path):
    extracted, repo = _extract_weak_bill(db_session, tmp_path)
    confirm = ConfirmBillUseCase(repo)
    with pytest.raises(BillConfirmationError, match="non-confirmable"):
        confirm.execute(
            extracted.analysis_id,
            BillConfirmationRequest(corrections={"not_a_field": 1}),
        )
