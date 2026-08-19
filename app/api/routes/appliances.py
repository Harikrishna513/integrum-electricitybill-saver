from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.appliance import ApplianceAnalysisEngine
from app.domain.models.appliance import HouseholdApplianceProfile

router = APIRouter(prefix="/appliances", tags=["appliances"])


class AnalyzeAppliancesRequest(BaseModel):
    profile: HouseholdApplianceProfile
    bill_units: float | None = Field(
        default=None,
        description="Optional bill kWh to compare against the estimated model total.",
    )


class TailoredSavingsRequest(BaseModel):
    profile: HouseholdApplianceProfile
    bill_units: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=2.0, ge=0)


@router.get("/questionnaire-schema")
def questionnaire_schema() -> dict:
    """Describe the optional household questions for clients/UI."""
    return {
        "milestone": 13,
        "message": "Optional questionnaire fields for estimated appliance analysis.",
        "fields": HouseholdApplianceProfile.model_json_schema(),
        "disclaimer": (
            "Answers produce ESTIMATED load shares only — not measured appliance metering."
        ),
    }


@router.post("/analyze")
def analyze_appliances(body: AnalyzeAppliancesRequest) -> dict:
    engine = ApplianceAnalysisEngine()
    result = engine.analyze(body.profile, bill_units=body.bill_units)

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 13 — APPLIANCE ANALYSIS")
        print("=" * 60)
        print(f"estimated_total: {result.estimated_total_kwh}")
        print(f"top_loads      : {result.top_loads}")
        for item in result.appliances[:5]:
            print(
                f"  {item.appliance_id}: {item.estimated_kwh_month} kWh "
                f"({item.share_of_estimated_total_percent}%)"
            )
        print("=" * 60)

    if result.status == "INVALID_INPUT":
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "milestone": 13,
        "message": result.message,
        "analysis": result.model_dump(mode="json"),
        "labels": {
            "analysis": "ESTIMATE from questionnaire + default watt tables",
            "not": "Actual sub-metered appliance percentages",
        },
    }


@router.post("/tailored-savings")
def tailored_savings(body: TailoredSavingsRequest) -> dict:
    """Analyze appliances, then estimate savings for top loads via SavingsEngine."""
    engine = ApplianceAnalysisEngine()
    analysis, estimates = engine.tailored_savings(
        body.profile,
        bill_units=body.bill_units,
        as_of=body.as_of,
        sanctioned_load_kw=body.sanctioned_load_kw,
    )
    if analysis.status == "INVALID_INPUT":
        raise HTTPException(status_code=400, detail=analysis.message)

    return {
        "milestone": 13,
        "message": (
            "Estimated appliance shares plus tailored savings suggestions. "
            "All ₹ values still come from SavingsEngine + TariffEngine."
        ),
        "analysis": analysis.model_dump(mode="json"),
        "savings_estimates": [e.model_dump(mode="json") for e in estimates],
        "labels": {
            "analysis": "ESTIMATED appliance model",
            "savings_estimates": "ESTIMATED ₹ via assumptions + tariff delta",
        },
    }
