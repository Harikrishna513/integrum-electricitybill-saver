"""Tests for Bill Analysis API presenter."""

from __future__ import annotations

from app.application.services.bill_analysis_presenter import BillAnalysisPresenter
from tests.fixtures.bescom_extraction import complete_bescom_extraction
from app.domain.models.category import CategoryClassificationResult
from app.domain.models.consistency import BillConsistencyResult, ConsistencyStatus
from app.domain.models.document import BillDocument, DocumentKind
from app.domain.models.extracted_field import ExtractedField
from app.application.use_cases.extract_bill import ExtractBillResult
from app.domain.models.validated_bill import BillValidationResult
from app.domain.services.bill_extraction_validator import BillExtractionValidator
from app.domain.services.category_classifier import ConsumerCategoryClassifier
from app.domain.services.bill_consistency_validator import BillConsistencyValidator
from datetime import datetime, timezone
from uuid import uuid4


def _result() -> ExtractBillResult:
    extraction = complete_bescom_extraction(
        units_consumed=ExtractedField(value=42, confidence=0.95, source="bill"),
        total_amount=ExtractedField(value=272, confidence=0.95, source="bill"),
        bill_date=ExtractedField(value="01/02/2026", confidence=0.9, source="bill"),
    )
    validation = BillExtractionValidator().validate(extraction)
    classification = ConsumerCategoryClassifier().classify(validation.bill)
    consistency = BillConsistencyValidator().validate(validation.bill)
    return ExtractBillResult(
        document=BillDocument(
            id=uuid4(),
            original_filename="bill.png",
            stored_filename="stored.png",
            content_type="image/png",
            size_bytes=100,
            sha256="abc",
            kind=DocumentKind.IMAGE,
            storage_path="/tmp/bill.png",
            created_at=datetime.now(timezone.utc),
        ),
        extraction=extraction,
        validation=validation,
        classification=classification,
        consistency=consistency,
        model_name="test",
        stored=None,
        history=None,
    )


def test_presenter_groups_sections_and_support():
    view = BillAnalysisPresenter().from_extract(_result())
    assert view.analysis_id == ""
    assert view.sections
    titles = [s.title for s in view.sections]
    assert "Consumer Details" in titles
    assert "Charges" in titles
    assert view.support.state == "Karnataka"
    charge_fields = next(s for s in view.sections if s.id == "charges").fields
    assert all(f.name != "subsidy" for f in charge_fields)
    required = [f for s in view.sections for f in s.fields if f.required]
    assert "units_consumed" in {f.name for f in required}
    assert "rr_number" not in {f.name for f in required}
