"""
Tests for Milestone 23 — support gate.
"""

from __future__ import annotations

from app.api.middleware import build_support_gate
from app.domain.models.category import (
    CategoryClassificationResult,
    ClassificationStatus,
    ConsumerCategory,
)
from app.domain.models.validated_bill import (
    BillValidationResult,
    CanonicalElectricityBill,
    ValidatedBool,
    ValidationIssue,
    ValidationSeverity,
)


def _bill(*, is_bescom: bool | None) -> CanonicalElectricityBill:
    return CanonicalElectricityBill(
        is_bescom_bill=ValidatedBool(value=is_bescom),
    )


def test_gate_blocks_non_bescom():
    validation = BillValidationResult(
        bill=_bill(is_bescom=False),
        issues=[
            ValidationIssue(
                code="NOT_BESCOM_BILL",
                field="is_bescom_bill",
                severity=ValidationSeverity.WARNING,
                message="Not BESCOM",
            )
        ],
        fields_needing_confirmation=[],
    )
    classification = CategoryClassificationResult(
        category=ConsumerCategory.DOMESTIC,
        status=ClassificationStatus.CLASSIFIED,
        confidence=0.9,
        signals=[],
        conflicting_categories=[],
        supported_by_app_v1=True,
        user_message="Domestic",
        rule_version="t",
        verification_status="x",
    )
    gate = build_support_gate(validation=validation, classification=classification)
    assert gate["supported_for_money_engines"] is False


def test_gate_allows_bescom_domestic():
    validation = BillValidationResult(
        bill=_bill(is_bescom=True),
        issues=[],
        fields_needing_confirmation=[],
    )
    classification = CategoryClassificationResult(
        category=ConsumerCategory.DOMESTIC,
        status=ClassificationStatus.CLASSIFIED,
        confidence=0.95,
        signals=[],
        conflicting_categories=[],
        supported_by_app_v1=True,
        user_message="Domestic",
        rule_version="t",
        verification_status="x",
        requires_user_confirmation=False,
    )
    gate = build_support_gate(validation=validation, classification=classification)
    assert gate["supported_for_money_engines"] is True
