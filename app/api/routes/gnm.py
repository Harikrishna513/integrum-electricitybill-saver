"""
GNM preliminary analysis API — Milestone 17.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.gnm import GNMAnalysisEngine
from app.domain.models.gnm import GNMInstallationInput, GNMPlantInput
from app.infrastructure.rules.gnm_rules import get_default_gnm_rule

router = APIRouter(prefix="/gnm", tags=["gnm"])


class GNMAnalyzeRequest(BaseModel):
    installations: list[GNMInstallationInput] = Field(min_length=1)
    plant: GNMPlantInput
    as_of: date
    discom: str = "BESCOM"
    tariff_code: str | None = "LT-1"


@router.get("/assumptions")
def get_assumptions() -> dict:
    rule = get_default_gnm_rule()
    return {
        "milestone": 17,
        "rule_version": rule.rule_version,
        "verification_status": rule.verification_status,
        "source": rule.source,
        "source_url": rule.source_url,
        "source_notes": rule.source_notes,
        "eligibility": rule.eligibility,
        "plant": rule.plant,
        "host_rule": rule.host_rule,
        "priority": rule.priority,
        "generation_defaults": rule.generation_defaults,
        "settlement": rule.settlement,
        "user_messages": rule.user_messages,
        "disclaimer": (
            "Preliminary GNM pre-screen only. Not BESCOM approval. "
            "Confirm against the latest Common SOP VNM/GNM and KERC orders."
        ),
    }


@router.post("/analyze")
def analyze_gnm(body: GNMAnalyzeRequest) -> dict:
    engine = GNMAnalysisEngine()
    result = engine.analyze(
        installations=body.installations,
        plant=body.plant,
        as_of=body.as_of,
        discom=body.discom,
        tariff_code=body.tariff_code,
    )

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 17 — GNM ANALYSIS")
        print("=" * 60)
        print(f"status : {result.status.value}")
        print(f"lapsed : {result.lapsed_kwh}")
        print(f"saving : {result.estimated_group_monthly_saving_inr}")
        print(f"msg    : {result.message}")

    return {"milestone": 17, "result": result.model_dump(mode="json")}
