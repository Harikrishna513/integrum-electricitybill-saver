from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.tariff import TariffEngine
from app.domain.models.tariff import TariffCalculationStatus

router = APIRouter(prefix="/tariff", tags=["tariff"])


class TariffCalculateRequest(BaseModel):
    discom: str = "BESCOM"
    category: str = Field(default="DOMESTIC", description="v1 supports DOMESTIC only")
    as_of: date = Field(description="Bill date / rule selection date")
    units: float = Field(ge=0)
    sanctioned_load_kw: float = Field(default=1.0, ge=0)
    tariff_code: str | None = Field(default="LT-1")


@router.post("/calculate")
def calculate_tariff(body: TariffCalculateRequest) -> dict:
    """
    Deterministic tariff calculation from versioned YAML rules.

    Bootstrap rules are UNVERIFIED_HYPOTHESIS until checked against KERC orders.
    """
    engine = TariffEngine()
    result = engine.calculate(
        discom=body.discom,
        category=body.category,
        as_of=body.as_of,
        units=body.units,
        sanctioned_load_kw=body.sanctioned_load_kw,
        tariff_code=body.tariff_code,
    )

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 10 — TARIFF ENGINE")
        print("=" * 60)
        print(f"as_of           : {body.as_of}")
        print(f"units           : {body.units}")
        print(f"load_kw         : {body.sanctioned_load_kw}")
        print(f"status          : {result.status.value}")
        print(f"rule_version    : {result.rule_version}")
        print(f"verification    : {result.verification_status}")
        print(f"estimated_total : {result.estimated_total}")
        for step in result.explanation_steps:
            print(f"  step: {step}")
        print("=" * 60)

    if result.status == TariffCalculationStatus.INVALID_INPUT:
        raise HTTPException(status_code=400, detail=result.message)

    return {
        "milestone": 10,
        "message": result.message,
        "calculation": result.model_dump(mode="json"),
        "labels": {
            "calculation": "CALCULATED by Python TariffEngine",
            "rule": "Versioned YAML selected by as_of date",
            "verification_status": (
                "UNVERIFIED_HYPOTHESIS means do not treat as official bill truth yet"
            ),
        },
    }


@router.get("/rules")
def list_tariff_rules() -> dict:
    """List loaded versioned tariff rules (metadata only)."""
    from app.infrastructure.rules.tariff_rules import TariffRuleRepository

    rules = TariffRuleRepository().list_rules()
    return {
        "milestone": 10,
        "count": len(rules),
        "rules": [
            {
                "rule_version": r.rule_version,
                "discom": r.discom,
                "category": r.category,
                "tariff_codes": r.tariff_codes,
                "effective_from": r.effective_from.isoformat(),
                "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                "verification_status": r.verification_status,
                "source": r.source,
            }
            for r in rules
        ],
    }
