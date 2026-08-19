from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.solar import SolarAnalysisEngine
from app.domain.models.solar import SolarProfile
from app.infrastructure.rules.solar_rules import get_default_solar_rooftop_rule

router = APIRouter(prefix="/solar", tags=["solar"])


class SolarAnalyzeRequest(BaseModel):
    monthly_units: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=3.0, ge=0)
    roof_area_m2: float | None = Field(default=None, ge=0)
    proposed_kwp: float | None = Field(default=None, ge=0)
    apply_cfa_estimate: bool = True
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"


@router.get("/assumptions")
def get_assumptions() -> dict:
    rule = get_default_solar_rooftop_rule()
    return {
        "milestone": 14,
        "rule_version": rule.rule_version,
        "verification_status": rule.verification_status,
        "source": rule.source,
        "source_notes": rule.source_notes,
        "generation": rule.generation,
        "sizing": rule.sizing,
        "economics": rule.economics,
        "cfa_pm_surya_ghar": rule.cfa_pm_surya_ghar,
        "user_messages": rule.user_messages,
        "disclaimer": (
            "Bootstrap planning assumptions only. Confirm against BESCOM SRTPV / "
            "KERC / PM Surya Ghar official sources before advising consumers."
        ),
    }


@router.post("/analyze")
def analyze_solar(body: SolarAnalyzeRequest) -> dict:
    engine = SolarAnalysisEngine()
    profile = SolarProfile(**body.model_dump())
    result = engine.analyze(profile)

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 14 — SOLAR ANALYSIS")
        print("=" * 60)
        print(f"status     : {result.status.value}")
        if result.sizing:
            print(f"analyzed   : {result.sizing.analyzed_kwp} kWp")
        if result.economics:
            print(f"saving/mo  : {result.economics.estimated_monthly_saving_inr}")
            print(f"payback    : {result.economics.simple_payback_years}")
        print(f"message    : {result.message}")

    return {
        "milestone": 14,
        "result": result.model_dump(mode="json"),
    }
