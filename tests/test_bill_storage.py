"""
Tests for Milestone 7 — canonical bill storage.
"""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.application.use_cases.extract_bill import ExtractBillUseCase
from app.application.use_cases.upload_bill import UploadBillCommand
from app.config.settings import get_settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ExtractedField
from app.infrastructure.persistence.db import Base, create_db_engine, reset_db_engine_for_tests
from app.infrastructure.persistence.repository import BillAnalysisRepository
from app.infrastructure.storage.local_storage import LocalFileStorage


def _png_bytes() -> bytes:
    img = Image.new("RGB", (40, 30), color=(20, 80, 160))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def db_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Session:
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    get_settings.cache_clear()
    reset_db_engine_for_tests()

    from app.config.settings import Settings

    settings = Settings()
    engine = create_db_engine(settings)
    # Import models for metadata
    from app.infrastructure.persistence import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
        session.commit()
    finally:
        session.close()
        engine.dispose()
        get_settings.cache_clear()
        reset_db_engine_for_tests()


def test_save_and_reload_bill_analysis(db_session: Session, tmp_path: Path):
    settings = get_settings()
    fake = ElectricityBillExtraction(
        units_consumed=ExtractedField(value=286, confidence=0.98, source="bill"),
        previous_meter_reading=ExtractedField(value=1000, confidence=0.98, source="bill"),
        current_meter_reading=ExtractedField(value=1286, confidence=0.98, source="bill"),
        total_amount=ExtractedField(value=1834.5, confidence=0.97, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.95, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.95, source="bill"),
        rr_number=ExtractedField(value="RR999", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACC999", confidence=0.9, source="bill"),
        bill_date=ExtractedField(value="01/08/2026", confidence=0.9, source="bill"),
        discom=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
        is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
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
            filename="sample.png",
            content_type="image/png",
            data=_png_bytes(),
        )
    )

    assert result.analysis_id is not None
    assert result.stored is not None
    assert result.stored.rr_number == "RR999"
    assert result.stored.units_consumed == 286.0
    assert result.stored.category == "DOMESTIC"

    db_session.commit()

    reloaded = repo.get_by_id(result.analysis_id)
    assert reloaded is not None
    assert reloaded.units_consumed == 286.0
    assert reloaded.canonical_bill["units_consumed"]["value"] == 286.0

    listed = repo.list_recent(limit=10)
    assert any(item.id == result.analysis_id for item in listed)


def test_same_rr_reuses_consumer(db_session: Session):
    settings = get_settings()
    repo = BillAnalysisRepository(db_session)

    def run_once(units: int) -> str:
        fake = ElectricityBillExtraction(
            units_consumed=ExtractedField(value=units, confidence=0.98, source="bill"),
            total_amount=ExtractedField(value=1000, confidence=0.97, source="bill"),
            tariff_code=ExtractedField(value="LT-1", confidence=0.95, source="bill"),
            consumer_category=ExtractedField(value="Domestic", confidence=0.95, source="bill"),
            rr_number=ExtractedField(value="RR-SAME", confidence=0.9, source="bill"),
            previous_meter_reading=ExtractedField(value=1, confidence=0.9, source="bill"),
            current_meter_reading=ExtractedField(value=1 + units, confidence=0.9, source="bill"),
            bill_date=ExtractedField(value="01/08/2026", confidence=0.9, source="bill"),
            discom=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
            is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
        )
        mock_extractor = MagicMock()
        mock_extractor.extract_from_document.return_value = fake
        result = ExtractBillUseCase(
            settings=settings,
            extractor=mock_extractor,
            repository=repo,
            storage=LocalFileStorage(settings.upload_dir),
        ).execute(
            UploadBillCommand(
                filename=f"{units}.png",
                content_type="image/png",
                data=_png_bytes(),
            )
        )
        assert result.stored is not None
        return result.stored.consumer_id or ""

    c1 = run_once(100)
    c2 = run_once(120)
    assert c1
    assert c1 == c2
