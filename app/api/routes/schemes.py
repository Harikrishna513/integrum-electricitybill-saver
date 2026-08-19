from __future__ import annotations

from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.domain.engines.gruha_jyothi import GruhaJyothiEngine

router = APIRouter(prefix="/schemes/gruha-jyothi", tags=["schemes"])


class GruhaJyothiAssessRequest(BaseModel):
    category: str = Field(default="DOMESTIC")
    as_of: date | None = None
    baseline_fy_2022_23_avg_units: float | None = Field(
        default=None,
        description="Required for entitlement estimate. Do not invent from one recent bill.",
    )
    current_units: float | None = None
    subsidy_line_seen_on_bill: bool | None = None
    consumer_declares_enrolled: bool | None = None


@router.post("/assess")
def assess_gruha_jyothi(body: GruhaJyothiAssessRequest) -> dict:
    """
    Preliminary Gruha Jyothi conditions / entitlement estimate.

    Never returns official approval.
    """
    result = GruhaJyothiEngine().assess(
        category=body.category,
        as_of=body.as_of,
        baseline_fy_2022_23_avg_units=body.baseline_fy_2022_23_avg_units,
        current_units=body.current_units,
        subsidy_line_seen_on_bill=body.subsidy_line_seen_on_bill,
        consumer_declares_enrolled=body.consumer_declares_enrolled,
    )

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 11 — GRUHA JYOTHI")
        print("=" * 60)
        print(f"status        : {result.status.value}")
        print(f"entitlement   : {result.computed_entitlement_units}")
        print(f"current_units : {result.current_units}")
        print(f"missing       : {result.missing_inputs}")
        print(f"message       : {result.user_message}")
        print("=" * 60)

    return {
        "milestone": 11,
        "message": result.user_message,
        "assessment": result.model_dump(mode="json"),
        "labels": {
            "assessment": "SCHEME CONDITION CHECK + ENTITLEMENT ESTIMATE (Python)",
            "not": "Official enrollment approval",
        },
        "legal_note": result.official_next_step,
    }


@router.get("/rule")
def get_gruha_jyothi_rule() -> dict:
    from app.infrastructure.rules.scheme_rules import get_default_gruha_jyothi_rule

    rule = get_default_gruha_jyothi_rule()
    return {
        "milestone": 11,
        "rule": {
            "rule_version": rule.rule_version,
            "scheme_name": rule.scheme_name,
            "effective_from": rule.effective_from.isoformat(),
            "effective_to": rule.effective_to.isoformat() if rule.effective_to else None,
            "verification_status": rule.verification_status,
            "source": rule.source,
            "eligible_categories": rule.eligible_categories,
            "percent_uplift": rule.entitlement.percent_uplift,
            "hard_cap_units": rule.entitlement.hard_cap_units,
            "baseline_fy": rule.baseline.financial_year,
        },
    }
