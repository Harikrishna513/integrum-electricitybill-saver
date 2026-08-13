"""
Savings estimation API — Milestone 12.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.savings import SavingsEngine
from app.domain.models.savings import SavingsStatus
from app.infrastructure.rules.savings_catalog import get_default_savings_catalog

router = APIRouter(prefix="/savings", tags=["savings"])


class DirectSavingsRequest(BaseModel):
    title: str = "Custom usage reduction"
    current_units: float = Field(ge=0)
    units_saved: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=2.0, ge=0)
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"
    assumption_notes: str | None = None


class RecommendationSavingsRequest(BaseModel):
    recommendation_id: str
    current_units: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=2.0, ge=0)
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"
    assumption_overrides: dict[str, Any] | None = None


class RecommendAllRequest(BaseModel):
    current_units: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=2.0, ge=0)
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"


@router.get("/catalog")
def get_catalog() -> dict:
    catalog = get_default_savings_catalog()
    return {
        "milestone": 12,
        "catalog_version": catalog.catalog_version,
        "verification_status": catalog.verification_status,
        "notes": catalog.notes,
        "recommendations": [r.model_dump() for r in catalog.recommendations],
    }


@router.post("/estimate")
def estimate_direct(body: DirectSavingsRequest) -> dict:
    """Estimate saving from an explicit kWh reduction + tariff engine."""
    from app.domain.models.savings import AssumptionSet

    engine = SavingsEngine()
    result = engine.estimate_from_units_saved(
        title=body.title,
        current_units=body.current_units,
        units_saved=body.units_saved,
        as_of=body.as_of,
        sanctioned_load_kw=body.sanctioned_load_kw,
        discom=body.discom,
        category=body.category,
        tariff_code=body.tariff_code,
        assumptions=AssumptionSet(
            description=body.assumption_notes or "Caller-provided units_saved",
            values={"units_saved": body.units_saved},
        ),
    )
    _log(result)
    if result.status == SavingsStatus.INVALID_INPUT:
        raise HTTPException(status_code=400, detail=result.message)
    return _response(result)


@router.post("/estimate-recommendation")
def estimate_recommendation(body: RecommendationSavingsRequest) -> dict:
    engine = SavingsEngine()
    result = engine.estimate_recommendation(
        recommendation_id=body.recommendation_id,
        current_units=body.current_units,
        as_of=body.as_of,
        sanctioned_load_kw=body.sanctioned_load_kw,
        discom=body.discom,
        category=body.category,
        tariff_code=body.tariff_code,
        assumption_overrides=body.assumption_overrides,
    )
    _log(result)
    if result.status == SavingsStatus.INVALID_INPUT:
        raise HTTPException(status_code=400, detail=result.message)
    return _response(result)


@router.post("/recommend")
def recommend_all(body: RecommendAllRequest) -> dict:
    """Rank catalog recommendations by estimated monthly saving."""
    engine = SavingsEngine()
    results = engine.recommend_all(
        current_units=body.current_units,
        as_of=body.as_of,
        sanctioned_load_kw=body.sanctioned_load_kw,
        discom=body.discom,
        category=body.category,
        tariff_code=body.tariff_code,
    )
    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 12 — SAVINGS RECOMMENDATIONS")
        print("=" * 60)
        for item in results:
            print(
                f"{item.recommendation_id}: "
                f"save {item.units_saved:g} kWh → ₹{item.estimated_monthly_saving}"
            )
        print("=" * 60)

    return {
        "milestone": 12,
        "message": (
            f"Generated {len(results)} estimate(s). "
            "All ₹ values come from TariffEngine under explicit assumptions."
        ),
        "estimates": [r.model_dump(mode="json") for r in results],
        "labels": {
            "estimates": "ESTIMATE — assumptions + Python tariff delta",
            "not": "Guaranteed savings or measured appliance telemetry",
        },
    }


def _response(result) -> dict:
    return {
        "milestone": 12,
        "message": result.message,
        "estimate": result.model_dump(mode="json"),
        "labels": {
            "estimate": "ESTIMATE from assumptions + TariffEngine",
        },
    }


def _log(result) -> None:
    if not get_settings().is_development:
        return
    print("=" * 60)
    print("MILESTONE 12 — SAVINGS ENGINE")
    print("=" * 60)
    print(f"title         : {result.title}")
    print(f"units_saved   : {result.units_saved}")
    print(f"monthly_saving: {result.estimated_monthly_saving}")
    print(f"tariff_rule   : {result.tariff_rule_version}")
    print(f"confidence    : {result.confidence.value}")
    print("=" * 60)
