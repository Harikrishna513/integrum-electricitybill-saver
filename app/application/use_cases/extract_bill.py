from __future__ import annotations

from dataclasses import dataclass

from app.application.use_cases.upload_bill import (
    UploadBillCommand,
    UploadBillDocumentUseCase,
)
from app.config.settings import Settings
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.category import CategoryClassificationResult
from app.domain.models.consistency import BillConsistencyResult
from app.domain.models.document import BillDocument
from app.domain.models.history import BillHistorySummary
from app.domain.models.validated_bill import BillValidationResult
from app.domain.services.bill_consistency_validator import BillConsistencyValidator
from app.domain.services.bill_extraction_validator import BillExtractionValidator
from app.domain.services.bill_history import build_history_summary, find_duplicate_warnings
from app.domain.services.category_classifier import ConsumerCategoryClassifier
from app.domain.services.bill_confirmation_needs import compute_needs_confirmation
from app.infrastructure.llm.bill_extractor import BillExtractionError
from app.infrastructure.llm.extractor_factory import BillExtractorPort, get_bill_extractor
from app.infrastructure.persistence.repository import BillAnalysisRepository, StoredBillAnalysis
from app.infrastructure.storage.local_storage import LocalFileStorage


@dataclass(frozen=True)
class ExtractBillResult:
    document: BillDocument
    extraction: ElectricityBillExtraction
    validation: BillValidationResult
    classification: CategoryClassificationResult
    consistency: BillConsistencyResult
    model_name: str
    stored: StoredBillAnalysis | None = None
    history: BillHistorySummary | None = None

    @property
    def analysis_id(self) -> str | None:
        return self.stored.id if self.stored else None

    @property
    def needs_confirmation(self) -> list[str]:
        return compute_needs_confirmation(self.validation, self.consistency)


class ExtractBillUseCase:
    def __init__(
        self,
        settings: Settings,
        uploader: UploadBillDocumentUseCase | None = None,
        extractor: BillExtractorPort | None = None,
        validator: BillExtractionValidator | None = None,
        classifier: ConsumerCategoryClassifier | None = None,
        consistency_validator: BillConsistencyValidator | None = None,
        repository: BillAnalysisRepository | None = None,
        storage: LocalFileStorage | None = None,
    ) -> None:
        self._settings = settings
        storage = storage or LocalFileStorage(settings.upload_dir)
        self._uploader = uploader or UploadBillDocumentUseCase(settings, storage)
        self._extractor = extractor or get_bill_extractor(settings)
        self._validator = validator or BillExtractionValidator()
        self._classifier = classifier or ConsumerCategoryClassifier()
        self._consistency = consistency_validator or BillConsistencyValidator()
        self._repository = repository

    def execute(self, command: UploadBillCommand) -> ExtractBillResult:
        document = self._uploader.execute(command)
        try:
            extraction = self._extractor.extract_from_document(document)
        except BillExtractionError:
            raise

        validation = self._validator.validate(extraction)
        classification = self._classifier.classify(validation.bill)
        consistency = self._consistency.validate(validation.bill)

        stored: StoredBillAnalysis | None = None
        history: BillHistorySummary | None = None

        if self._repository is not None:
            stored = self._repository.save_analysis(
                document=document,
                extraction=extraction,
                validation=validation,
                classification=classification,
                consistency=consistency,
                model_name=self._extraction_model_label(),
            )
            history = self._build_history_after_save(stored, document.sha256)

        return ExtractBillResult(
            document=document,
            extraction=extraction,
            validation=validation,
            classification=classification,
            consistency=consistency,
            model_name=self._extraction_model_label(),
            stored=stored,
            history=history,
        )

    def execute_many(self, commands: list[UploadBillCommand]) -> list[ExtractBillResult]:
        """
        Process multiple bills sequentially (apartment/history upload helper).
        Each bill is stored and linked to its consumer when RR/account is present.
        """
        return [self.execute(command) for command in commands]

    def _extraction_model_label(self) -> str:
        provider = self._settings.bill_extraction_provider
        if provider == "mistral_ocr":
            fb = "+gemini-fallback" if self._settings.bill_extraction_fallback else ""
            return (
                f"{self._settings.mistral_ocr_model}->{self._settings.gemini_model}{fb}"
            )
        if provider == "mistral":
            return self._settings.mistral_model
        return self._settings.gemini_model

    def _build_history_after_save(
        self,
        stored: StoredBillAnalysis,
        sha256: str,
    ) -> BillHistorySummary | None:
        assert self._repository is not None
        if not stored.consumer_id:
            return BillHistorySummary(
                consumer_id="unknown",
                discom=stored.discom,
                rr_number=stored.rr_number,
                account_id=stored.account_id,
                bill_count=1,
                bills=[],
                duplicate_warnings=[],
            )

        analyses = self._repository.list_by_consumer_id(stored.consumer_id, limit=24)
        sha_map = self._repository.map_sha256_for_analyses(
            [a for a in analyses if a.id != stored.id]
        )
        duplicates = find_duplicate_warnings(
            incoming=stored,
            existing_for_consumer=[a for a in analyses if a.id != stored.id],
            incoming_sha256=sha256,
            existing_sha256_by_analysis_id=sha_map,
        )
        return build_history_summary(
            consumer_id=stored.consumer_id,
            discom=stored.discom,
            rr_number=stored.rr_number,
            account_id=stored.account_id,
            analyses=analyses,
            duplicate_warnings=duplicates,
        )
