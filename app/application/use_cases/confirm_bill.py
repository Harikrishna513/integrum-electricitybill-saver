"""
ConfirmBillUseCase — Milestone 24.

Flow:
  Load stored analysis → apply user corrections → re-validate →
  re-classify → re-check consistency → persist update
"""

from __future__ import annotations

from dataclasses import dataclass

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
        fields = list(self.validation.fields_needing_confirmation)
        if self.classification.requires_user_confirmation:
            if "consumer_category" not in fields:
                fields.append("consumer_category")
        for name in self.consistency.fields_needing_confirmation:
            if name not in fields:
                fields.append(name)
        return fields


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

        updated = self._repository.update_analysis(
            analysis_id,
            extraction=patched,
            validation=validation,
            classification=classification,
            consistency=consistency,
            notes=request.note,
        )

        needs = list(validation.fields_needing_confirmation)
        if classification.requires_user_confirmation and "consumer_category" not in needs:
            needs.append("consumer_category")
        for name in consistency.fields_needing_confirmation:
            if name not in needs:
                needs.append(name)

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
