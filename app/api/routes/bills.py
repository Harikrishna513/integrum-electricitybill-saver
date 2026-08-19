from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.application.services.bill_analysis_presenter import (
    BillAnalysisPresenter,
    build_batch_item,
)
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

router = APIRouter(prefix="/bills", tags=["Bill Analysis"])


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


def get_presenter() -> BillAnalysisPresenter:
    return BillAnalysisPresenter()


def _read_command(file: UploadFile, data: bytes) -> UploadBillCommand:
    return UploadBillCommand(
        filename=file.filename or "unknown",
        content_type=file.content_type,
        data=data,
    )


def _user_facing_error(exc: Exception) -> HTTPException:
    if isinstance(exc, EmptyBillFileError):
        return HTTPException(
            status_code=400,
            detail="Unable to read this file. Please upload a clear electricity bill.",
        )
    if isinstance(exc, BillFileTooLargeError):
        return HTTPException(
            status_code=413,
            detail="This file is too large. Please upload a bill under the size limit.",
        )
    if isinstance(exc, UnsupportedBillFileError):
        return HTTPException(
            status_code=415,
            detail="Unsupported file type. Please upload a PDF, JPG, JPEG, or PNG bill.",
        )
    if isinstance(exc, BillExtractionError):
        return HTTPException(
            status_code=502,
            detail=(
                "We could not read this bill automatically. "
                "Please try a clearer photo or PDF."
            ),
        )
    return HTTPException(
        status_code=500,
        detail="Something went wrong while processing your bill. Please try again.",
    )


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
        raise _user_facing_error(exc) from exc

    return {
        "message": "Bill file accepted.",
        "document": document.model_dump(mode="json"),
    }


@router.post("/extract", status_code=status.HTTP_201_CREATED)
async def extract_bill(
    file: UploadFile = File(..., description="BESCOM bill image or PDF"),
    use_case: ExtractBillUseCase = Depends(get_extract_use_case),
    presenter: BillAnalysisPresenter = Depends(get_presenter),
) -> dict:
    """Upload one bill and run the full Bill Analysis pipeline."""
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
        raise _user_facing_error(exc) from exc

    view = presenter.from_extract(result)
    return {
        "message": view.message,
        "analysis": view.model_dump(mode="json"),
    }


@router.post("/extract-batch", status_code=status.HTTP_201_CREATED)
async def extract_bills_batch(
    files: list[UploadFile] = File(..., description="Multiple BESCOM bill images/PDFs"),
    use_case: ExtractBillUseCase = Depends(get_extract_use_case),
    presenter: BillAnalysisPresenter = Depends(get_presenter),
) -> dict:
    """Process multiple bills independently; one failure does not block others."""
    if not files:
        raise HTTPException(status_code=400, detail="Please upload at least one bill.")
    if len(files) > 12:
        raise HTTPException(
            status_code=400,
            detail="Please upload up to 12 bills at a time.",
        )

    items = []
    success = 0
    needs_review = 0
    failed = 0

    for file in files:
        data = await file.read()
        command = _read_command(file, data)
        try:
            result = use_case.execute(command)
            view = presenter.from_extract(result)
            if view.status == "needs_review":
                needs_review += 1
            elif view.status == "error":
                failed += 1
            else:
                success += 1
            items.append(build_batch_item(filename=file.filename or "bill", result=result))
        except (
            EmptyBillFileError,
            BillFileTooLargeError,
            UnsupportedBillFileError,
            BillExtractionError,
        ) as exc:
            failed += 1
            http_exc = _user_facing_error(exc)
            items.append(
                build_batch_item(
                    filename=file.filename or "bill",
                    error=str(http_exc.detail),
                )
            )

    return {
        "message": (
            f"Processed {len(files)} bill(s): "
            f"{success} ready, {needs_review} need review, {failed} failed."
        ),
        "processed": len(files),
        "successful": success,
        "needs_review": needs_review,
        "failed": failed,
        "items": items,
    }


@router.post("/{analysis_id}/confirm")
def confirm_bill_fields(
    analysis_id: str,
    body: BillConfirmationRequest,
    use_case: ConfirmBillUseCase = Depends(get_confirm_use_case),
    presenter: BillAnalysisPresenter = Depends(get_presenter),
) -> dict:
    """Apply user corrections and re-run validation on the same analysis."""
    try:
        result = use_case.execute(analysis_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="Bill analysis not found.") from exc
    except BillConfirmationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    view = presenter.from_confirm(result)
    return {
        "message": view.message,
        "analysis": view.model_dump(mode="json"),
    }


@router.get("/{analysis_id}")
def get_bill_analysis(
    analysis_id: str,
    repository: BillAnalysisRepository = Depends(get_bill_repository),
    presenter: BillAnalysisPresenter = Depends(get_presenter),
) -> dict:
    stored = repository.get_by_id(analysis_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Bill analysis not found.")

    from app.domain.models.bill_extraction import ElectricityBillExtraction
    from app.domain.models.category import CategoryClassificationResult
    from app.domain.models.consistency import BillConsistencyResult
    from app.domain.models.validated_bill import BillValidationResult
    from app.application.use_cases.extract_bill import ExtractBillResult
    from app.domain.models.document import BillDocument, DocumentKind
    from uuid import UUID

    extraction = ElectricityBillExtraction.model_validate(stored.extraction)
    validation = BillValidationResult.model_validate(stored.validation)
    classification = CategoryClassificationResult.model_validate(stored.classification)
    consistency = BillConsistencyResult.model_validate(stored.consistency)

    result = ExtractBillResult(
        document=BillDocument(
            id=UUID(stored.document_id),
            original_filename="stored",
            stored_filename="stored",
            content_type="application/octet-stream",
            size_bytes=0,
            sha256="",
            kind=DocumentKind.UNKNOWN,
            storage_path="",
        ),
        extraction=extraction,
        validation=validation,
        classification=classification,
        consistency=consistency,
        model_name="stored",
        stored=stored,
        history=None,
    )
    view = presenter.from_extract(result)
    view = view.model_copy(
        update={
            "analysis_id": stored.id,
            "confirmed": len(view.needs_confirmation) == 0,
        }
    )
    audit = stored.validation.get("corrections_audit") if isinstance(stored.validation, dict) else []
    if audit:
        view = view.model_copy(update={"corrections_audit": audit})
    return {
        "message": view.message,
        "analysis": view.model_dump(mode="json"),
    }


@router.get("")
def list_bill_analyses(
    limit: int = Query(default=20, ge=1, le=100),
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    items = repository.list_recent(limit=limit)
    return {
        "count": len(items),
        "items": [_summary_item(item) for item in items],
    }
