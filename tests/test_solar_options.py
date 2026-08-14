"""Tests for Module 2 — solar options comparison after bill confirm."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from app.application.use_cases.compare_solar_options import CompareSolarOptionsUseCase, SolarOptionsError
from app.application.use_cases.confirm_bill import ConfirmBillUseCase
from app.application.use_cases.extract_bill import ExtractBillUseCase
from app.application.use_cases.upload_bill import UploadBillCommand
from app.config.settings import get_settings
from app.domain.models.category import ConsumerCategory
from app.domain.models.confirmation import BillConfirmationRequest
from app.domain.models.extracted_field import ExtractedField
from app.domain.models.solar_options import CompareSolarOptionsRequest
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
    db_path = tmp_path / "solar_options.db"
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


def _confirmed_analysis(db_session: Session) -> str:
    settings = get_settings()
    fake = complete_bescom_extraction(
        units_consumed=ExtractedField(value=280, confidence=0.95, source="bill"),
        previous_meter_reading=ExtractedField(value=1000, confidence=0.9, source="bill"),
        current_meter_reading=ExtractedField(value=1280, confidence=0.9, source="bill"),
    )
    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake
    repo = BillAnalysisRepository(db_session)
    extracted = ExtractBillUseCase(
        settings=settings,
        extractor=mock_extractor,
        repository=repo,
        storage=LocalFileStorage(settings.upload_dir),
    ).execute(
        UploadBillCommand(filename="bill.png", content_type="image/png", data=_png_bytes())
    )
    assert extracted.analysis_id
    ConfirmBillUseCase(repo).execute(
        extracted.analysis_id,
        BillConfirmationRequest(
            accept_extracted_as_printed=[
                "consumer_name",
                "account_id",
                "address",
                "utility",
                "discom",
                "tariff_code",
                "sanctioned_load",
                "billing_period",
                "bill_date",
                "units_consumed",
                "energy_charge",
                "fixed_charge",
                "total_amount",
                "document_language",
                "is_bescom_bill",
            ],
            confirm_category=ConsumerCategory.DOMESTIC,
        ),
    )
    return extracted.analysis_id


def test_prefill_from_confirmed_bill(db_session: Session):
    analysis_id = _confirmed_analysis(db_session)
    repo = BillAnalysisRepository(db_session)
    use_case = CompareSolarOptionsUseCase(repo)
    view = use_case.prefill(analysis_id)
    assert view.prefill.monthly_units == 280.0
    assert view.prefill.suggested_plant_kwp is not None
    assert view.prefill.connection_id


def test_compare_returns_three_options(db_session: Session):
    analysis_id = _confirmed_analysis(db_session)
    repo = BillAnalysisRepository(db_session)
    use_case = CompareSolarOptionsUseCase(repo)
    result = use_case.compare(
        analysis_id,
        CompareSolarOptionsRequest(
            plant={"proposed_kwp": 5.0, "roof_area_m2": 40.0},
            vnm_participants=[
                {
                    "connection_id": "Flat-2",
                    "procurement_share_percent": 50.0,
                    "monthly_units": 250,
                }
            ],
            gnm_installations=[
                {"connection_id": "RR-SECOND", "priority": 2, "is_host": True}
            ],
        ),
    )
    kinds = {o.option for o in result.view.options}
    assert kinds == {"individual_solar", "vnm", "gnm"}
    assert result.view.message
    assert result.view.disclaimer


def test_compare_rejects_unconfirmed_bill(db_session: Session):
    settings = get_settings()
    fake = complete_bescom_extraction(
        units_consumed=ExtractedField(value=280, confidence=0.4, source="bill"),
    )
    mock_extractor = MagicMock()
    mock_extractor.extract_from_document.return_value = fake
    repo = BillAnalysisRepository(db_session)
    extracted = ExtractBillUseCase(
        settings=settings,
        extractor=mock_extractor,
        repository=repo,
        storage=LocalFileStorage(settings.upload_dir),
    ).execute(
        UploadBillCommand(filename="weak.png", content_type="image/png", data=_png_bytes())
    )
    assert extracted.analysis_id
    use_case = CompareSolarOptionsUseCase(repo)
    with pytest.raises(SolarOptionsError, match="Complete bill review"):
        use_case.compare(extracted.analysis_id, CompareSolarOptionsRequest())
