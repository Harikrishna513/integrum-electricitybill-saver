from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.metering import NetMeteringEngine
from app.domain.models.metering import MeteringArrangement
from app.infrastructure.rules.metering_rules import get_default_metering_arrangements_rule

router = APIRouter(prefix="/metering", tags=["metering"])


class SettleRequest(BaseModel):
    arrangement: MeteringArrangement = MeteringArrangement.NET_METERING
    consumption_kwh: float = Field(ge=0)
    generation_kwh: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=3.0, ge=0)
    coincidence_fraction: float | None = Field(default=None, ge=0, le=1)
    availed_cfa: bool = False
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"


class CompareRequest(BaseModel):
    consumption_kwh: float = Field(ge=0)
    generation_kwh: float = Field(ge=0)
    as_of: date
    sanctioned_load_kw: float = Field(default=3.0, ge=0)
    coincidence_fraction: float | None = Field(default=None, ge=0, le=1)
    availed_cfa: bool = False
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"


@router.get("/concepts")
def get_concepts() -> dict:
    engine = NetMeteringEngine()
    concepts = engine.list_concepts()
    return {
        "milestone": 15,
        "rule_version": engine.rule.rule_version,
        "verification_status": engine.rule.verification_status,
        "message": (
            "Net vs Gross are estimated here. VNM / GNM are concepts until "
            "Milestones 16 / 17."
        ),
        "concepts": [c.model_dump() for c in concepts],
    }


@router.get("/assumptions")
def get_assumptions() -> dict:
    rule = get_default_metering_arrangements_rule()
    return {
        "milestone": 15,
        "rule_version": rule.rule_version,
        "verification_status": rule.verification_status,
        "source": rule.source,
        "source_notes": rule.source_notes,
        "settlement": rule.settlement,
        "export_tariffs_inr_per_kwh": rule.export_tariffs_inr_per_kwh,
        "user_messages": rule.user_messages,
        "disclaimer": (
            "Bootstrap settlement assumptions only. Confirm export tariff against "
            "the consumer PPA and latest KERC/BESCOM documents."
        ),
    }


@router.post("/settle")
def settle(body: SettleRequest) -> dict:
    engine = NetMeteringEngine()
    result = engine.settle(**body.model_dump())

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 15 — METERING SETTLEMENT")
        print("=" * 60)
        print(f"arrangement: {result.arrangement.value}")
        print(f"status     : {result.status.value}")
        print(f"saving/mo  : {result.estimated_monthly_saving_inr}")
        print(f"message    : {result.message}")

    return {"milestone": 15, "result": result.model_dump(mode="json")}


@router.post("/compare")
def compare(body: CompareRequest) -> dict:
    engine = NetMeteringEngine()
    result = engine.compare(**body.model_dump())
    return {"milestone": 15, "result": result.model_dump(mode="json")}
