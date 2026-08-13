"""
Consumer history + consumption analysis API — Milestones 8–9.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.domain.services.bill_history import build_history_summary
from app.domain.services.consumption_analyzer import ConsumptionAnalyzer
from app.infrastructure.persistence.db import get_db_session
from app.infrastructure.persistence.repository import BillAnalysisRepository

router = APIRouter(prefix="/consumers", tags=["consumers"])


def get_bill_repository(
    session: Session = Depends(get_db_session),
) -> BillAnalysisRepository:
    return BillAnalysisRepository(session)


def _history_for_consumer(
    repository: BillAnalysisRepository,
    consumer_id: str,
    limit: int,
):
    consumer = repository.get_consumer(consumer_id)
    if consumer is None:
        raise HTTPException(status_code=404, detail=f"Consumer not found: {consumer_id}")
    analyses = repository.list_by_consumer_id(consumer_id, limit=limit)
    return build_history_summary(
        consumer_id=consumer_id,
        discom=consumer.discom,
        rr_number=consumer.rr_number,
        account_id=consumer.account_id,
        analyses=analyses,
    )


@router.get("/{consumer_id}/history")
def get_consumer_history(
    consumer_id: str,
    limit: int = Query(default=24, ge=1, le=36),
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    summary = _history_for_consumer(repository, consumer_id, limit)
    analysis = ConsumptionAnalyzer().analyze_history(summary)
    return {
        "milestone": 9,
        "message": (
            f"Found {summary.bill_count} bill(s). "
            + (
                "Consumption analysis included."
                if analysis.status == "OK"
                else "Need more dated bills for full trends."
            )
        ),
        "history": summary.model_dump(mode="json"),
        "consumption": analysis.model_dump(mode="json"),
        "labels": {
            "history": "FACT timeline of stored bills",
            "consumption": "CALCULATED metrics from Python (not Gemini)",
        },
    }


@router.get("/{consumer_id}/consumption")
def get_consumer_consumption(
    consumer_id: str,
    limit: int = Query(default=24, ge=1, le=36),
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    """Dedicated consumption analysis endpoint."""
    summary = _history_for_consumer(repository, consumer_id, limit)
    analysis = ConsumptionAnalyzer().analyze_history(summary)

    settings_log = None
    from app.config.settings import get_settings

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 9 — CONSUMPTION ANALYSIS")
        print("=" * 60)
        print(f"consumer_id   : {consumer_id}")
        print(f"sample_count  : {analysis.sample_count}")
        print(f"avg_units     : {analysis.average_units}")
        print(f"units_trend   : {analysis.units_trend.value}")
        if analysis.month_over_month:
            print(f"mom_units_%   : {analysis.month_over_month.percent_units}")
        for insight in analysis.insights:
            print(f"  insight: {insight}")
        print("=" * 60)
        settings_log = True

    return {
        "milestone": 9,
        "message": analysis.insights[0] if analysis.insights else "Consumption analysis complete.",
        "consumption": analysis.model_dump(mode="json"),
        "history_bill_count": summary.bill_count,
        "labels": {
            "consumption": "CALCULATED from stored FACT bills via Python",
        },
        "debug_logged": bool(settings_log),
    }


@router.get("/by-rr/{rr_number}/history")
def get_history_by_rr(
    rr_number: str,
    discom: str = Query(default="BESCOM"),
    limit: int = Query(default=24, ge=1, le=36),
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    analyses = repository.list_by_rr_number(rr_number, discom=discom, limit=limit)
    if not analyses:
        raise HTTPException(
            status_code=404,
            detail=f"No bills found for RR={rr_number} discom={discom}",
        )

    consumer_id = analyses[-1].consumer_id or analyses[0].consumer_id or "unknown"
    summary = build_history_summary(
        consumer_id=consumer_id,
        discom=discom.upper(),
        rr_number=rr_number,
        account_id=analyses[-1].account_id,
        analyses=analyses,
    )
    analysis = ConsumptionAnalyzer().analyze_history(summary)
    return {
        "milestone": 9,
        "message": f"Found {summary.bill_count} bill(s) for RR {rr_number}.",
        "history": summary.model_dump(mode="json"),
        "consumption": analysis.model_dump(mode="json"),
    }


@router.get("/by-rr/{rr_number}/consumption")
def get_consumption_by_rr(
    rr_number: str,
    discom: str = Query(default="BESCOM"),
    limit: int = Query(default=24, ge=1, le=36),
    repository: BillAnalysisRepository = Depends(get_bill_repository),
) -> dict:
    analyses = repository.list_by_rr_number(rr_number, discom=discom, limit=limit)
    if not analyses:
        raise HTTPException(
            status_code=404,
            detail=f"No bills found for RR={rr_number} discom={discom}",
        )
    consumer_id = analyses[-1].consumer_id or analyses[0].consumer_id or "unknown"
    summary = build_history_summary(
        consumer_id=consumer_id,
        discom=discom.upper(),
        rr_number=rr_number,
        account_id=analyses[-1].account_id,
        analyses=analyses,
    )
    analysis = ConsumptionAnalyzer().analyze_history(summary)
    return {
        "milestone": 9,
        "message": analysis.insights[0] if analysis.insights else "Consumption analysis complete.",
        "consumption": analysis.model_dump(mode="json"),
    }
