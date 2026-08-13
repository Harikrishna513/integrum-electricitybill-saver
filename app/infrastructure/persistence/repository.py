"""
Bill analysis repository — Milestone 7.

CONCEPT
  Persist and reload pipeline results.
  Application layer talks to this repository, not to SQLAlchemy sessions directly
  in business rules (we keep it thin for learning).

SPRING ANALOGY
  Like a Spring Data JpaRepository for BillAnalysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import uuid4

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.domain.models.category import CategoryClassificationResult
from app.domain.models.consistency import BillConsistencyResult
from app.domain.models.document import BillDocument
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.validated_bill import BillValidationResult
from app.infrastructure.persistence.models import BillAnalysisORM, ConsumerORM, DocumentORM


@dataclass(frozen=True)
class StoredBillAnalysis:
    """API/domain-facing read model for a persisted analysis."""

    id: str
    document_id: str
    consumer_id: str | None
    model_name: str
    discom: str | None
    rr_number: str | None
    account_id: str | None
    tariff_code: str | None
    category: str | None
    classification_status: str | None
    consistency_status: str | None
    supported_by_app_v1: bool | None
    billing_period: str | None
    bill_date: date | None
    units_consumed: float | None
    total_amount: float | None
    sanctioned_load: float | None
    extraction: dict[str, Any]
    validation: dict[str, Any]
    classification: dict[str, Any]
    consistency: dict[str, Any]
    canonical_bill: dict[str, Any]
    created_at: str
    notes: str | None = None


class BillAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_analysis(
        self,
        *,
        document: BillDocument,
        extraction: ElectricityBillExtraction,
        validation: BillValidationResult,
        classification: CategoryClassificationResult,
        consistency: BillConsistencyResult,
        model_name: str,
    ) -> StoredBillAnalysis:
        doc_row = DocumentORM(
            id=str(document.id),
            original_filename=document.original_filename,
            stored_filename=document.stored_filename,
            content_type=document.content_type,
            size_bytes=document.size_bytes,
            sha256=document.sha256,
            kind=document.kind.value,
            storage_path=document.storage_path,
            width=document.width,
            height=document.height,
            page_count=document.page_count,
            created_at=document.created_at,
        )
        self._session.add(doc_row)

        bill = validation.bill
        discom = (bill.discom.value or bill.utility.value or "BESCOM")
        if isinstance(discom, str):
            discom = discom.upper()

        rr_number = bill.rr_number.value
        account_id = bill.account_id.value
        consumer_name = bill.consumer_name.value

        consumer = self._get_or_create_consumer(
            discom=discom or "BESCOM",
            rr_number=rr_number,
            account_id=account_id,
            consumer_name=consumer_name,
        )

        analysis_id = str(uuid4())
        analysis = BillAnalysisORM(
            id=analysis_id,
            document_id=str(document.id),
            consumer_id=consumer.id if consumer else None,
            model_name=model_name,
            discom=discom,
            rr_number=rr_number,
            account_id=account_id,
            tariff_code=bill.tariff_code.value,
            category=classification.category.value,
            classification_status=classification.status.value,
            consistency_status=consistency.status.value,
            supported_by_app_v1=classification.supported_by_app_v1,
            billing_period=bill.billing_period.value,
            bill_date=bill.bill_date.value,
            units_consumed=bill.units_consumed.value,
            total_amount=bill.total_amount.value,
            sanctioned_load=bill.sanctioned_load.value,
            extraction_json=extraction.model_dump(mode="json"),
            validation_json=validation.model_dump(mode="json"),
            classification_json=classification.model_dump(mode="json"),
            consistency_json=consistency.model_dump(mode="json"),
            canonical_bill_json=bill.model_dump(mode="json"),
        )
        self._session.add(analysis)
        self._session.flush()

        return self._to_stored(analysis)

    def get_by_id(self, analysis_id: str) -> StoredBillAnalysis | None:
        row = self._session.get(BillAnalysisORM, analysis_id)
        if row is None:
            return None
        return self._to_stored(row)

    def update_analysis(
        self,
        analysis_id: str,
        *,
        extraction: ElectricityBillExtraction,
        validation: BillValidationResult,
        classification: CategoryClassificationResult,
        consistency: BillConsistencyResult,
        notes: str | None = None,
        corrections_audit: list[dict] | None = None,
    ) -> StoredBillAnalysis:
        """
        Milestone 24 — overwrite JSON snapshots + scalar columns after user confirm.
        Does not create a new analysis row (same analysis_id / document).
        """
        row = self._session.get(BillAnalysisORM, analysis_id)
        if row is None:
            raise LookupError(f"Analysis not found: {analysis_id}")

        bill = validation.bill
        row.model_name = row.model_name  # keep original extractor model
        row.discom = (bill.discom.value or bill.utility.value or row.discom)
        if isinstance(row.discom, str):
            row.discom = row.discom.upper()
        row.rr_number = bill.rr_number.value
        row.account_id = bill.account_id.value
        row.tariff_code = bill.tariff_code.value
        row.category = classification.category.value
        row.classification_status = classification.status.value
        row.consistency_status = consistency.status.value
        row.supported_by_app_v1 = classification.supported_by_app_v1
        row.billing_period = bill.billing_period.value
        row.bill_date = bill.bill_date.value
        row.units_consumed = bill.units_consumed.value
        row.total_amount = bill.total_amount.value
        row.sanctioned_load = bill.sanctioned_load.value
        row.extraction_json = extraction.model_dump(mode="json")
        validation_payload = validation.model_dump(mode="json")
        if corrections_audit:
            existing = validation_payload.get("corrections_audit") or []
            if not isinstance(existing, list):
                existing = []
            validation_payload["corrections_audit"] = existing + corrections_audit
        row.validation_json = validation_payload
        row.classification_json = classification.model_dump(mode="json")
        row.consistency_json = consistency.model_dump(mode="json")
        row.canonical_bill_json = bill.model_dump(mode="json")
        if notes is not None:
            row.notes = notes

        self._session.flush()
        return self._to_stored(row)

    def list_recent(self, *, limit: int = 20) -> list[StoredBillAnalysis]:
        stmt: Select[tuple[BillAnalysisORM]] = (
            select(BillAnalysisORM)
            .order_by(BillAnalysisORM.created_at.desc())
            .limit(limit)
        )
        rows = self._session.scalars(stmt).all()
        return [self._to_stored(row) for row in rows]

    def get_consumer(self, consumer_id: str) -> ConsumerORM | None:
        return self._session.get(ConsumerORM, consumer_id)

    def find_consumer_by_rr(
        self,
        *,
        rr_number: str,
        discom: str = "BESCOM",
    ) -> ConsumerORM | None:
        stmt = select(ConsumerORM).where(
            ConsumerORM.discom == discom.upper(),
            ConsumerORM.rr_number == rr_number,
        )
        return self._session.scalars(stmt).first()

    def list_by_consumer_id(
        self,
        consumer_id: str,
        *,
        limit: int = 24,
    ) -> list[StoredBillAnalysis]:
        stmt: Select[tuple[BillAnalysisORM]] = (
            select(BillAnalysisORM)
            .where(BillAnalysisORM.consumer_id == consumer_id)
            .order_by(BillAnalysisORM.created_at.asc())
            .limit(limit)
        )
        rows = self._session.scalars(stmt).all()
        return [self._to_stored(row) for row in rows]

    def list_by_rr_number(
        self,
        rr_number: str,
        *,
        discom: str = "BESCOM",
        limit: int = 24,
    ) -> list[StoredBillAnalysis]:
        consumer = self.find_consumer_by_rr(rr_number=rr_number, discom=discom)
        if consumer is None:
            stmt: Select[tuple[BillAnalysisORM]] = (
                select(BillAnalysisORM)
                .where(
                    BillAnalysisORM.rr_number == rr_number,
                    BillAnalysisORM.discom == discom.upper(),
                )
                .order_by(BillAnalysisORM.created_at.asc())
                .limit(limit)
            )
            rows = self._session.scalars(stmt).all()
            return [self._to_stored(row) for row in rows]
        return self.list_by_consumer_id(consumer.id, limit=limit)

    def get_document_sha256(self, document_id: str) -> str | None:
        doc = self._session.get(DocumentORM, document_id)
        return doc.sha256 if doc else None

    def map_sha256_for_analyses(self, analyses: list[StoredBillAnalysis]) -> dict[str, str]:
        result: dict[str, str] = {}
        for item in analyses:
            sha = self.get_document_sha256(item.document_id)
            if sha:
                result[item.id] = sha
        return result

    def _get_or_create_consumer(
        self,
        *,
        discom: str,
        rr_number: str | None,
        account_id: str | None,
        consumer_name: str | None,
    ) -> ConsumerORM | None:
        if not rr_number and not account_id:
            return None

        stmt = select(ConsumerORM).where(ConsumerORM.discom == discom)
        if rr_number:
            stmt = stmt.where(ConsumerORM.rr_number == rr_number)
        elif account_id:
            stmt = stmt.where(ConsumerORM.account_id == account_id)

        existing = self._session.scalars(stmt).first()
        if existing:
            if consumer_name and not existing.consumer_name:
                existing.consumer_name = consumer_name
            if account_id and not existing.account_id:
                existing.account_id = account_id
            if rr_number and not existing.rr_number:
                existing.rr_number = rr_number
            return existing

        consumer = ConsumerORM(
            discom=discom,
            rr_number=rr_number,
            account_id=account_id,
            consumer_name=consumer_name,
        )
        self._session.add(consumer)
        self._session.flush()
        return consumer

    def _to_stored(self, row: BillAnalysisORM) -> StoredBillAnalysis:
        return StoredBillAnalysis(
            id=row.id,
            document_id=row.document_id,
            consumer_id=row.consumer_id,
            model_name=row.model_name,
            discom=row.discom,
            rr_number=row.rr_number,
            account_id=row.account_id,
            tariff_code=row.tariff_code,
            category=row.category,
            classification_status=row.classification_status,
            consistency_status=row.consistency_status,
            supported_by_app_v1=row.supported_by_app_v1,
            billing_period=row.billing_period,
            bill_date=row.bill_date,
            units_consumed=row.units_consumed,
            total_amount=row.total_amount,
            sanctioned_load=row.sanctioned_load,
            extraction=row.extraction_json,
            validation=row.validation_json,
            classification=row.classification_json,
            consistency=row.consistency_json,
            canonical_bill=row.canonical_bill_json,
            created_at=row.created_at.isoformat() if row.created_at else "",
            notes=row.notes,
        )
