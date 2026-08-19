"""
Tests for Milestone 8 — historical bill storage / consumer timeline.
"""

from __future__ import annotations

import io
from datetime import date
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
from app.domain.services.bill_history import find_duplicate_warnings
from app.infrastructure.persistence.db import Base, create_db_engine, reset_db_engine_for_tests
from app.infrastructure.persistence.repository import BillAnalysisRepository, StoredBillAnalysis
from app.infrastructure.storage.local_storage import LocalFileStorage


def _png_bytes(color: tuple[int, int, int] = (20, 80, 160)) -> bytes:
    img = Image.new("RGB", (40, 30), color=color)
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


def _fake_extraction(*, units: int, bill_date: str, period: str) -> ElectricityBillExtraction:
    return ElectricityBillExtraction(
        units_consumed=ExtractedField(value=units, confidence=0.98, source="bill"),
        total_amount=ExtractedField(value=units * 7, confidence=0.97, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.95, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.95, source="bill"),
        rr_number=ExtractedField(value="RR-HIST", confidence=0.9, source="bill"),
        account_id=ExtractedField(value="ACC-HIST", confidence=0.9, source="bill"),
        bill_date=ExtractedField(value=bill_date, confidence=0.9, source="bill"),
        billing_period=ExtractedField(value=period, confidence=0.9, source="bill"),
        previous_meter_reading=ExtractedField(value=1000, confidence=0.9, source="bill"),
        current_meter_reading=ExtractedField(value=1000 + units, confidence=0.9, source="bill"),
        discom=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
        is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
    )


def test_multiple_bills_build_consumer_history(db_session: Session):
    settings = get_settings()
    repo = BillAnalysisRepository(db_session)

    months = [
        (180, "01/01/2026", "Jan-2026"),
        (200, "01/02/2026", "Feb-2026"),
        (220, "01/03/2026", "Mar-2026"),
    ]
    consumer_ids = []
    for i, (units, bill_date, period) in enumerate(months):
        mock_extractor = MagicMock()
        mock_extractor.extract_from_document.return_value = _fake_extraction(
            units=units, bill_date=bill_date, period=period
        )
        result = ExtractBillUseCase(
            settings=settings,
            extractor=mock_extractor,
            repository=repo,
            storage=LocalFileStorage(settings.upload_dir),
        ).execute(
            UploadBillCommand(
                filename=f"bill_{i}.png",
                content_type="image/png",
                data=_png_bytes((20 + i, 80, 160)),
            )
        )
        assert result.history is not None
        consumer_ids.append(result.stored.consumer_id if result.stored else None)

    assert len(set(consumer_ids)) == 1
    assert result.history.bill_count == 3
    assert result.history.ready_for_trend_analysis is True
    assert result.history.oldest_bill_date == date(2026, 1, 1)
    assert result.history.newest_bill_date == date(2026, 3, 1)

    by_rr = repo.list_by_rr_number("RR-HIST", discom="BESCOM")
    assert len(by_rr) == 3


def test_duplicate_bill_date_warning():
    incoming = StoredBillAnalysis(
        id="new",
        document_id="d2",
        consumer_id="c1",
        model_name="gemini-2.5-flash",
        discom="BESCOM",
        rr_number="RR1",
        account_id=None,
        tariff_code="LT-1",
        category="DOMESTIC",
        classification_status="CLASSIFIED",
        consistency_status="CONSISTENT",
        supported_by_app_v1=True,
        billing_period="Jan-2026",
        bill_date=date(2026, 1, 15),
        units_consumed=100,
        total_amount=700,
        sanctioned_load=None,
        extraction={},
        validation={},
        classification={},
        consistency={},
        canonical_bill={},
        created_at="2026-01-20T00:00:00+00:00",
    )
    prior = StoredBillAnalysis(
        id="old",
        document_id="d1",
        consumer_id="c1",
        model_name="gemini-2.5-flash",
        discom="BESCOM",
        rr_number="RR1",
        account_id=None,
        tariff_code="LT-1",
        category="DOMESTIC",
        classification_status="CLASSIFIED",
        consistency_status="CONSISTENT",
        supported_by_app_v1=True,
        billing_period="Jan-2026",
        bill_date=date(2026, 1, 15),
        units_consumed=100,
        total_amount=700,
        sanctioned_load=None,
        extraction={},
        validation={},
        classification={},
        consistency={},
        canonical_bill={},
        created_at="2026-01-16T00:00:00+00:00",
    )
    warnings = find_duplicate_warnings(incoming=incoming, existing_for_consumer=[prior])
    codes = {w.code for w in warnings}
    assert "POSSIBLE_DUPLICATE_BILL_DATE" in codes
    assert "POSSIBLE_DUPLICATE_BILLING_PERIOD" in codes


def test_duplicate_warnings_deduped_by_code_when_multiple_priors_match():
    incoming = StoredBillAnalysis(
        id="new",
        document_id="d3",
        consumer_id="c1",
        model_name="gemini-2.5-flash",
        discom="BESCOM",
        rr_number="RR1",
        account_id=None,
        tariff_code="LT-1",
        category="DOMESTIC",
        classification_status="CLASSIFIED",
        consistency_status="CONSISTENT",
        supported_by_app_v1=True,
        billing_period="Jan-2026",
        bill_date=date(2026, 1, 15),
        units_consumed=100,
        total_amount=700,
        sanctioned_load=None,
        extraction={},
        validation={},
        classification={},
        consistency={},
        canonical_bill={},
        created_at="2026-01-20T00:00:00+00:00",
    )
    prior_a = StoredBillAnalysis(
        id="old-a",
        document_id="d1",
        consumer_id="c1",
        model_name="gemini-2.5-flash",
        discom="BESCOM",
        rr_number="RR1",
        account_id=None,
        tariff_code="LT-1",
        category="DOMESTIC",
        classification_status="CLASSIFIED",
        consistency_status="CONSISTENT",
        supported_by_app_v1=True,
        billing_period="Jan-2026",
        bill_date=date(2026, 1, 15),
        units_consumed=90,
        total_amount=650,
        sanctioned_load=None,
        extraction={},
        validation={},
        classification={},
        consistency={},
        canonical_bill={},
        created_at="2026-01-10T00:00:00+00:00",
    )
    from dataclasses import replace

    prior_b = replace(prior_a, id="old-b", document_id="d2")
    warnings = find_duplicate_warnings(
        incoming=incoming,
        existing_for_consumer=[prior_a, prior_b],
        incoming_sha256="abc",
        existing_sha256_by_analysis_id={"old-a": "abc", "old-b": "abc"},
    )
    assert len(warnings) == 3
    assert len({w.code for w in warnings}) == 3
