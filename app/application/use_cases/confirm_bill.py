"""
ConfirmBillUseCase — Milestone 24.

Flow:
  Load stored analysis → apply user corrections → re-validate →
  re-classify → re-check consistency → persist update
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.category import CategoryClassificationResult
from app.domain.models.confirmation import BillConfirmationApplied, BillConfirmationRequest
from app.domain.models.consistency import BillConsistencyResult
from app.domain.models.validated_bill import BillValidationResult
from app.domain.services.bill_confirmation import (
    BillConfirmationError,
    apply_extraction_corrections,
    apply_user_category_confirmation,
)
from app.domain.services.bill_consistency_validator import BillConsistencyValidator
from app.domain.services.bill_extraction_validator import BillExtractionValidator
from app.domain.services.category_classifier import ConsumerCategoryClassifier
from app.infrastructure.persistence.repository import BillAnalysisRepository, StoredBillAnalysis


@dataclass(frozen=True)
class ConfirmBillResult:
    stored: StoredBillAnalysis
    extraction: ElectricityBillExtraction
    validation: BillValidationResult
    classification: CategoryClassificationResult
    consistency: BillConsistencyResult
    confirmation: BillConfirmationApplied

    @property
    def analysis_id(self) -> str:
        return self.stored.id

    @property
    def needs_confirmation(self) -> list[str]:
        """Post-attestation list — use confirmation payload, not raw re-validation."""
        return list(self.confirmation.needs_confirmation)


class ConfirmBillUseCase:
    def __init__(
        self,
        repository: BillAnalysisRepository,
        *,
        validator: BillExtractionValidator | None = None,
        classifier: ConsumerCategoryClassifier | None = None,
        consistency_validator: BillConsistencyValidator | None = None,
    ) -> None:
        self._repository = repository
        self._validator = validator or BillExtractionValidator()
        self._classifier = classifier or ConsumerCategoryClassifier()
        self._consistency = consistency_validator or BillConsistencyValidator()

    def execute(
        self,
        analysis_id: str,
        request: BillConfirmationRequest,
    ) -> ConfirmBillResult:
        if (
            not request.corrections
            and not request.accept_extracted_as_printed
            and request.confirm_category is None
        ):
            raise BillConfirmationError(
                "Provide corrections, accept_extracted_as_printed, and/or confirm_category."
            )

        stored = self._repository.get_by_id(analysis_id)
        if stored is None:
            raise LookupError(f"Analysis not found: {analysis_id}")

        extraction = ElectricityBillExtraction.model_validate(stored.extraction)
        original = extraction.model_dump(mode="python")
        patched, corrected, accepted = apply_extraction_corrections(extraction, request)

        validation = self._validator.validate(patched)
        classification = self._classifier.classify(validation.bill)

        if request.confirm_category is not None:
            classification = apply_user_category_confirmation(
                classification,
                confirm_category=request.confirm_category,
                rule_version=classification.rule_version,
                verification_status=classification.verification_status,
            )

        consistency = self._consistency.validate(validation.bill)

        audit_entries = _build_audit_entries(
            original_extraction=original,
            patched_extraction=patched.model_dump(mode="python"),
            corrected=corrected,
            accepted=accepted,
            category_confirmed=request.confirm_category.value if request.confirm_category else None,
        )

        updated = self._repository.update_analysis(
            analysis_id,
            extraction=patched,
            validation=validation,
            classification=classification,
            consistency=consistency,
            notes=request.note,
            corrections_audit=audit_entries,
        )

        needs = list(validation.fields_needing_confirmation)
        if classification.requires_user_confirmation and "consumer_category" not in needs:
            needs.append("consumer_category")
        for name in consistency.fields_needing_confirmation:
            if name not in needs:
                needs.append(name)

        attested = set(corrected) | set(accepted)
        if request.confirm_category is not None:
            attested.add("consumer_category")
        needs = [n for n in needs if n not in attested]

        confirmation = BillConfirmationApplied(
            analysis_id=analysis_id,
            fields_corrected=corrected,
            fields_accepted_as_printed=accepted,
            category_confirmed=request.confirm_category,
            needs_confirmation=needs,
            message=(
                "User corrections applied and analysis re-validated."
                if not needs
                else (
                    "Corrections applied, but some fields still need attention: "
                    + ", ".join(needs)
                )
            ),
        )

        return ConfirmBillResult(
            stored=updated,
            extraction=patched,
            validation=validation,
            classification=classification,
            consistency=consistency,
            confirmation=confirmation,
        )


def _build_audit_entries(
    *,
    original_extraction: dict,
    patched_extraction: dict,
    corrected: list[str],
    accepted: list[str],
    category_confirmed: str | None,
) -> list[dict]:
    now = datetime.now(timezone.utc).isoformat()
    entries: list[dict] = []

    for name in corrected:
        entries.append(
            {
                "field": name,
                "original_value": _field_value(original_extraction, name),
                "corrected_value": _field_value(patched_extraction, name),
                "corrected_by_user": True,
                "corrected_at": now,
                "action": "corrected",
            }
        )

    for name in accepted:
        entries.append(
            {
                "field": name,
                "original_value": _field_value(original_extraction, name),
                "corrected_value": _field_value(patched_extraction, name),
                "corrected_by_user": True,
                "corrected_at": now,
                "action": "accepted_as_printed",
            }
        )

    if category_confirmed:
        entries.append(
            {
                "field": "consumer_category",
                "original_value": _field_value(original_extraction, "consumer_category"),
                "corrected_value": category_confirmed,
                "corrected_by_user": True,
                "corrected_at": now,
                "action": "category_confirmed",
            }
        )

    return entries


def _field_value(extraction: dict, name: str):
    field = extraction.get(name) or {}
    if isinstance(field, dict):
        return field.get("value")
    return None
