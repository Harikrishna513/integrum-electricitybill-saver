"""
Gruha Jyothi domain models — Milestone 11.

CRITICAL PRODUCT RULE
  Never output "You are approved for Gruha Jyothi."
  Only: conditions met / missing / not applicable / estimate.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class GruhaJyothiStatus(str, Enum):
    CONDITIONS_APPEAR_MET = "CONDITIONS_APPEAR_MET"
    CONDITIONS_NOT_MET = "CONDITIONS_NOT_MET"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    REQUIRES_OFFICIAL_VERIFICATION = "REQUIRES_OFFICIAL_VERIFICATION"


class ConditionCheck(BaseModel):
    code: str
    passed: bool | None  # None = unknown / not evaluated
    detail: str


class GruhaJyothiAssessment(BaseModel):
    status: GruhaJyothiStatus
    scheme_name: str = "Gruha Jyothi"
    rule_version: str | None = None
    verification_status: str | None = None
    source: str | None = None
    as_of: date | None = None

    category: str | None = None
    baseline_fy_2022_23_avg_units: float | None = None
    computed_entitlement_units: float | None = None
    hard_cap_units: float | None = None
    current_units: float | None = None

    units_within_entitlement: float | None = None
    units_beyond_entitlement: float | None = None
    appears_fully_covered_this_month: bool | None = None

    subsidy_line_seen_on_bill: bool | None = None
    consumer_declares_enrolled: bool | None = None

    conditions: list[ConditionCheck] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    user_message: str
    official_next_step: str = (
        "Confirm entitlement/enrollment via official BESCOM / Seva Sindhu channels. "
        "This app does not approve or reject scheme claims."
    )
