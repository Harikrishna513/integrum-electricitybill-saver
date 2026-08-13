"""
GNM analysis models — Milestone 17.

CRITICAL
  Never output "You are approved for GNM."
  Same-name consumer, priority waterfall, host 20% / lapse rules.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GNMStatus(str, Enum):
    POTENTIALLY_SUITABLE = "POTENTIALLY_SUITABLE"
    POTENTIALLY_UNSUITABLE = "POTENTIALLY_UNSUITABLE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    TECHNICAL_VERIFICATION_REQUIRED = "TECHNICAL_VERIFICATION_REQUIRED"


class GNMConditionCheck(BaseModel):
    code: str
    passed: bool | None
    detail: str


class GNMInstallationInput(BaseModel):
    connection_id: str = Field(description="RR / account label.")
    category: str = "DOMESTIC"
    sanctioned_load_kw: float = Field(ge=0)
    monthly_units: float = Field(ge=0)
    priority: int = Field(
        ge=1,
        description="Credit priority (1 = highest / first). Unique among installations.",
    )
    is_host: bool = False


class GNMPlantInput(BaseModel):
    proposed_kwp: float = Field(ge=0)
    estimated_monthly_generation_kwh: float | None = Field(default=None, ge=0)
    same_discom_area: bool | None = None
    same_consumer_name: bool | None = Field(
        default=None,
        description="Caller affirms all RRs are in the same consumer name.",
    )
    grid_topology_hint: str | None = None


class GNMInstallationEstimate(BaseModel):
    connection_id: str
    category: str
    sanctioned_load_kw: float
    monthly_units: float
    priority: int
    is_host: bool
    allocated_generation_kwh: float
    residual_retail_units: float
    surplus_export_kwh: float
    baseline_retail_bill_inr: float | None = None
    estimated_retail_bill_after_credit_inr: float | None = None
    estimated_surplus_credit_inr: float | None = None
    estimated_net_cost_inr: float | None = None
    estimated_monthly_saving_inr: float | None = None


class GNMAnalysisResult(BaseModel):
    status: GNMStatus
    rule_version: str | None = None
    verification_status: str | None = None
    source: str | None = None
    source_url: str | None = None
    as_of: date

    proposed_kwp: float | None = None
    combined_sanctioned_load_kw: float | None = None
    max_plant_kwp: float | None = None
    estimated_monthly_generation_kwh: float | None = None
    host_reserved_kwh: float | None = None
    lapsed_kwh: float | None = None
    unallocated_generation_kwh: float | None = None
    excess_purchase_rate_inr_per_kwh: float | None = None

    installations: list[GNMInstallationEstimate] = Field(default_factory=list)
    conditions: list[GNMConditionCheck] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)

    estimated_group_monthly_saving_inr: float | None = None
    message: str
    official_next_step: str = (
        "Apply / confirm via BESCOM SRTPV (DSPV) portal. This app does not approve "
        "GNM, clear technical feasibility, or execute a PPA."
    )
    disclaimer: str = (
        "Preliminary GNM analysis only — not BESCOM approval or technical clearance."
    )
