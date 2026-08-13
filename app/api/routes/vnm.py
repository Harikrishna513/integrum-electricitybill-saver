"""
VNM preliminary analysis API — Milestone 16.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.vnm import VNMAnalysisEngine
from app.domain.models.vnm import VNMParticipantInput, VNMPlantInput
from app.infrastructure.rules.vnm_rules import get_default_vnm_rule

router = APIRouter(prefix="/vnm", tags=["vnm"])


class VNMAnalyzeRequest(BaseModel):
    participants: list[VNMParticipantInput] = Field(min_length=1)
    plant: VNMPlantInput
    as_of: date
    discom: str = "BESCOM"
    tariff_code: str | None = "LT-1"


@router.get("/assumptions")
def get_assumptions() -> dict:
    rule = get_default_vnm_rule()
    return {
        "milestone": 16,
        "rule_version": rule.rule_version,
        "verification_status": rule.verification_status,
        "source": rule.source,
        "source_url": rule.source_url,
        "source_notes": rule.source_notes,
        "eligibility": rule.eligibility,
        "plant": rule.plant,
        "procurement": rule.procurement,
        "generation_defaults": rule.generation_defaults,
        "settlement": rule.settlement,
        "user_messages": rule.user_messages,
        "disclaimer": (
            "Preliminary VNM pre-screen assumptions only. Not BESCOM approval. "
            "Confirm against the latest Common SOP VNM/GNM and KERC orders."
        ),
    }


@router.post("/analyze")
def analyze_vnm(body: VNMAnalyzeRequest) -> dict:
    engine = VNMAnalysisEngine()
    result = engine.analyze(
        participants=body.participants,
        plant=body.plant,
        as_of=body.as_of,
        discom=body.discom,
        tariff_code=body.tariff_code,
    )

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 16 — VNM ANALYSIS")
        print("=" * 60)
        print(f"status : {result.status.value}")
        print(f"plant  : {result.proposed_kwp} kWp")
        print(f"saving : {result.estimated_group_monthly_saving_inr}")
        print(f"msg    : {result.message}")

    return {"milestone": 16, "result": result.model_dump(mode="json")}
