from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.application.use_cases.compare_solar_options import (
    CompareSolarOptionsUseCase,
    SolarOptionsError,
)
from app.domain.models.solar_options import CompareSolarOptionsRequest
from app.infrastructure.persistence.db import get_db_session
from app.infrastructure.persistence.repository import BillAnalysisRepository

router = APIRouter(prefix="/bills", tags=["Solar Options"])


def get_solar_options_use_case(
    session: Session = Depends(get_db_session),
) -> CompareSolarOptionsUseCase:
    return CompareSolarOptionsUseCase(BillAnalysisRepository(session))


@router.get("/{analysis_id}/solar-options/prefill")
def solar_options_prefill(
    analysis_id: str,
    use_case: CompareSolarOptionsUseCase = Depends(get_solar_options_use_case),
) -> dict:
    try:
        view = use_case.prefill(analysis_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="Bill analysis not found.") from None
    except SolarOptionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": view.message, "comparison": view.model_dump(mode="json")}


@router.post("/{analysis_id}/solar-options")
def compare_solar_options(
    analysis_id: str,
    body: CompareSolarOptionsRequest,
    use_case: CompareSolarOptionsUseCase = Depends(get_solar_options_use_case),
) -> dict:
    try:
        result = use_case.compare(analysis_id, body)
    except LookupError:
        raise HTTPException(status_code=404, detail="Bill analysis not found.") from None
    except SolarOptionsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": result.view.message,
        "comparison": result.view.model_dump(mode="json"),
    }
