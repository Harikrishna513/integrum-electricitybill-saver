"""
Bill upload / extract / confirm / retrieve API — through Milestone 24.
"""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.middleware import build_support_gate
from app.application.use_cases.confirm_bill import ConfirmBillUseCase
from app.application.use_cases.extract_bill import ExtractBillUseCase
from app.application.use_cases.upload_bill import (
    UploadBillCommand,
    UploadBillDocumentUseCase,
)
from app.config.settings import Settings, get_settings
from app.domain.models.confirmation import BillConfirmationRequest
from app.domain.services.bill_confirmation import BillConfirmationError
from app.infrastructure.llm.bill_extractor import BillExtractionError
from app.infrastructure.persistence.db import get_db_session
from app.infrastructure.persistence.repository import BillAnalysisRepository
from app.infrastructure.storage.bill_file_reader import (
    BillFileTooLargeError,
    EmptyBillFileError,
    UnsupportedBillFileError,
)

router = APIRouter(prefix="/bills", tags=["bills"])


def get_upload_use_case(
    settings: Settings = Depends(get_settings),
) -> UploadBillDocumentUseCase:
    return UploadBillDocumentUseCase(settings)


def get_extract_use_case(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db_session),
) -> ExtractBillUseCase:
    return ExtractBillUseCase(
        settings,
        repository=BillAnalysisRepository(session),
    )


def get_bill_repository(
    session: Session = Depends(get_db_session),
) -> BillAnalysisRepository:
    return BillAnalysisRepository(session)


def get_confirm_use_case(
    session: Session = Depends(get_db_session),
) -> ConfirmBillUseCase:
    return ConfirmBillUseCase(BillAnalysisRepository(session))


def _read_command(file: UploadFile, data: bytes) -> UploadBillCommand:
    return UploadBillCommand(
        filename=file.filename or "unknown",
        content_type=file.content_type,
        data=data,
    )


def _map_upload_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, EmptyBillFileError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, BillFileTooLargeError):
        return HTTPException(status_code=413, detail=str(exc))
    if isinstance(exc, UnsupportedBillFileError):
        return HTTPException(status_code=415, detail=str(exc))
    if isinstance(exc, BillExtractionError):
        return HTTPException(status_code=502, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


def _summary_item(item) -> dict:
    return {
        "analysis_id": item.id,
        "document_id": item.document_id,
        "consumer_id": item.consumer_id,
        "rr_number": item.rr_number,
        "account_id": item.account_id,
        "bill_date": item.bill_date.isoformat() if item.bill_date else None,
        "billing_period": item.billing_period,
        "units_consumed": item.units_consumed,
        "total_amount": item.total_amount,
        "category": item.category,
        "classification_status": item.classification_status,
        "consistency_status": item.consistency_status,
        "created_at": item.created_at,
    }


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_bill(
    file: UploadFile = File(..., description="BESCOM bill image or PDF"),
    use_case: UploadBillDocumentUseCase = Depends(get_upload_use_case),
) -> dict:
    data = await file.read()
    command = _read_command(file, data)

    try:
        document = use_case.execute(command)
    except (EmptyBillFileError, BillFileTooLargeError, UnsupportedBillFileError) as exc:
        raise _map_upload_errors(exc) from exc

    return {
        "milestone": 2,
        "message": "Bill file accepted and stored on disk (not yet in DB analysis table).",
        "document": document.model_dump(mode="json"),
    }


@router.post("/extract", status_code=status.HTTP_201_CREATED)
async def extract_bill(
    file: UploadFile = File(..., description="BESCOM bill image or PDF"),
    use_case: ExtractBillUseCase = Depends(get_extract_use_case),
) -> dict:
    """Analyze one bill and append it to that consumer's history."""
    data = await file.read()
    command = _read_command(file, data)

    try:
        result = use_case.execute(command)
    except (
        EmptyBillFileError,
        BillFileTooLargeError,
        UnsupportedBillFileError,
        BillExtractionError,
    ) as exc:
        raise _map_upload_errors(exc) from exc

    settings = get_settings()
    if settings.is_development:
        hist = result.history
        print("=" * 60)
        print("MILESTONE 8 — HISTORICAL BILL STORAGE")
        print("=" * 60)
        print(f"analysis_id     : {result.analysis_id}")
        print(f"consumer_id     : {result.stored.consumer_id if result.stored else None}")
        print(f"history_count   : {hist.bill_count if hist else 0}")
        print(f"ready_for_trends: {hist.ready_for_trend_analysis if hist else False}")
        if hist and hist.duplicate_warnings:
            for w in hist.duplicate_warnings:
                print(f"  duplicate: {w.code} → {w.matched_analysis_id}")
        print("=" * 60)

    support_gate = build_support_gate(
        validation=result.validation,
        classification=result.classification,
    )

    return {
        "milestone": 8,
        "message": (
            "Bill analyzed and saved into consumer history. "
            f"Consumer now has {result.history.bill_count if result.history else 1} bill(s)."
            if support_gate["supported_for_money_engines"]
            else (
                "Bill extracted, but money engines are gated. "
                + " ".join(support_gate["block_reasons"][:1])
            )
        ),
        "analysis_id": result.analysis_id,
        "model": result.model_name,
        "document": result.document.model_dump(mode="json"),
        "extraction": result.extraction.model_dump(mode="json"),
        "validation": result.validation.model_dump(mode="json"),
        "classification": result.classification.model_dump(mode="json"),
        "consistency": result.consistency.model_dump(mode="json"),
        "stored": asdict(result.stored) if result.stored else None,
        "history": result.history.model_dump(mode="json") if result.history else None,
        "needs_confirmation": result.needs_confirmation,
        "support_gate": support_gate,
        "pipeline": {
            "can_continue_domestic_analysis": (
                result.classification.can_continue_domestic_pipeline
            ),
            "supported_for_money_engines": support_gate["supported_for_money_engines"],
            "has_consistency_discrepancy": result.consistency.has_discrepancy,
            "persisted": result.stored is not None,
            "ready_for_trend_analysis": (
                result.history.ready_for_trend_analysis if result.history else False
            ),
            "app_v1_supports": ["DOMESTIC"],
            "discom_scope": ["BESCOM"],
            "state_scope": ["Karnataka"],
        },
        "labels": {
            "history": "FACT timeline of stored bills for this consumer (no MoM math yet)",
            "history.duplicate_warnings": "Possible duplicates — verify, do not auto-delete",
            "support_gate": "Whether tariff/savings/solar/VNM/GNM should be offered",
        },
        "legal_note": (
            "Consistency issues mean extracted values disagree and should be verified. "
            "They do not prove the utility overcharged the customer."
        ),
    }


@router.post("/{analysis_id}/confirm")
def confirm_bill_fields(
    analysis_id: str,
    body: BillConfirmationRequest,
    use_case: ConfirmBillUseCase = Depends(get_confirm_use_case),
) -> dict:
    """
    Milestone 24 — user corrects / accepts extracted fields, then engines re-run
    validation + category + consistency on the same analysis_id.
    """
    try:
        result = use_case.execute(analysis_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BillConfirmationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    support_gate = build_support_gate(
        validation=result.validation,
        classification=result.classification,
    )

    return {
        "milestone": 24,
        "message": result.confirmation.message,
        "analysis_id": result.analysis_id,
        "confirmation": result.confirmation.model_dump(mode="json"),
        "extraction": result.extraction.model_dump(mode="json"),
        "validation": result.validation.model_dump(mode="json"),
        "classification": result.classification.model_dump(mode="json"),
        "consistency": result.consistency.model_dump(mode="json"),
        "stored": asdict(result.stored),
        "needs_confirmation": result.needs_confirmation,
        "support_gate": support_gate,
        "pipeline": {
            "can_continue_domestic_analysis": (
                result.classification.can_continue_domestic_pipeline
            ),
            "supported_for_money_engines": support_gate["supported_for_money_engines"],
            "has_consistency_discrepancy": result.consistency.has_discrepancy,
            "persisted": True,
        },
        "legal_note": (
            "User-confirmed values are still not BESCOM official approval. "
            "Verify against the printed bill before relying on savings math."
        ),
    }


@router.post("/extract-batch", status_code=status.HTTP_201_CREATED)
async def extract_bills_batch(
    files: list[UploadFile] = File(..., description="Multiple BESCOM bill images/PDFs"),
    use_case: ExtractBillUseCase = Depends(get_extract_use_case),
) -> dict:
    """
    Upload 3–12 bills at once for the same or different consumers.
    Each file runs the full pipeline and links into history by RR/account.
    """
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required.")
    if len(files) > 12:
        raise HTTPException(status_code=400, detail="Maximum 12 bills per batch in v1.")

    results = []
    errors = []
    for file in files:
        data = await file.read()
        command = _read_command(file, data)
        try:
            result = use_case.execute(command)
            results.append(
                {
                    "filename": file.filename,
                    "analysis_id": result.analysis_id,
                    "consumer_id": result.stored.consumer_id if result.stored else None,
                    "rr_number": result.stored.rr_number if result.stored else None,
                    "bill_date": (
                        result.stored.bill_date.isoformat()
                        if result.stored and result.stored.bill_date
                        else None
                    ),
                    "units_consumed": result.stored.units_consumed if result.stored else None,
                    "history_bill_count": (
                        result.history.bill_count if result.history else None
                    ),
                    "duplicate_warnings": (
                        [w.model_dump() for w in result.history.duplicate_warnings]
                        if result.history
                        else []
                    ),
                }
            )
        except (
            EmptyBillFileError,
            BillFileTooLargeError,
            UnsupportedBillFileError,
            BillExtractionError,
        ) as exc:
            errors.append({"filename": file.filename, "error": str(exc)})

    return {
        "milestone": 8,
        "message": (
            f"Batch complete: {len(results)} saved, {len(errors)} failed. "
            "Use GET /consumers/{id}/history or GET /consumers/by-rr/{rr}/history."
        ),
        "saved_count": len(results),
        "error_count": len(errors),
        "results": results,
        "errors": errors,
    }


@router.get("/{analysis_id}")
def get_bill_analysis(
    analysis_id: str,
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    stored = repository.get_by_id(analysis_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"Analysis not found: {analysis_id}")
    return {
        "milestone": 8,
        "analysis": asdict(stored),
    }


@router.get("")
def list_bill_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    items = repository.list_recent(limit=limit)
    return {
        "milestone": 8,
        "count": len(items),
        "items": [_summary_item(item) for item in items],
    }
