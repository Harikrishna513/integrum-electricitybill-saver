from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class VNMStatus(str, Enum):
    POTENTIALLY_SUITABLE = "POTENTIALLY_SUITABLE"
    POTENTIALLY_UNSUITABLE = "POTENTIALLY_UNSUITABLE"
    INSUFFICIENT_INFORMATION = "INSUFFICIENT_INFORMATION"
    TECHNICAL_VERIFICATION_REQUIRED = "TECHNICAL_VERIFICATION_REQUIRED"


class VNMConditionCheck(BaseModel):
    code: str
    passed: bool | None  # None = unknown / not evaluated
    detail: str


class VNMParticipantInput(BaseModel):
    connection_id: str = Field(description="RR / account / flat label for display.")
    category: str = "DOMESTIC"
    sanctioned_load_kw: float = Field(ge=0)
    monthly_units: float = Field(ge=0)
    procurement_share_percent: float = Field(
        ge=0,
        le=100,
        description="Declared share (%) of plant generation credit.",
    )


class VNMPlantInput(BaseModel):
    proposed_kwp: float = Field(ge=0)
    estimated_monthly_generation_kwh: float | None = Field(
        default=None,
        ge=0,
        description="If omitted, estimated from YAML specific yield.",
    )
    same_discom_area: bool | None = Field(
        default=None,
        description="Caller affirms plant + participants are in same licensee area.",
    )
    grid_topology_hint: str | None = Field(
        default=None,
        description="Optional: same_dt | same_feeder | same_substation | multi_substation",
    )


class VNMParticipantEstimate(BaseModel):
    connection_id: str
    category: str
    sanctioned_load_kw: float
    monthly_units: float
    procurement_share_percent: float
    allocated_generation_kwh: float
    residual_retail_units: float
    surplus_export_kwh: float
    baseline_retail_bill_inr: float | None = None
    estimated_retail_bill_after_credit_inr: float | None = None
    estimated_surplus_credit_inr: float | None = None
    estimated_net_cost_inr: float | None = None
    estimated_monthly_saving_inr: float | None = None


class VNMAnalysisResult(BaseModel):
    status: VNMStatus
    rule_version: str | None = None
    verification_status: str | None = None
    source: str | None = None
    source_url: str | None = None
    as_of: date

    proposed_kwp: float | None = None
    combined_sanctioned_load_kw: float | None = None
    max_plant_kwp: float | None = None
    estimated_monthly_generation_kwh: float | None = None
    excess_purchase_rate_inr_per_kwh: float | None = None

    participants: list[VNMParticipantEstimate] = Field(default_factory=list)
    conditions: list[VNMConditionCheck] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)

    estimated_group_monthly_saving_inr: float | None = None
    message: str
    official_next_step: str = (
        "Apply / confirm via BESCOM SRTPV (DSPV) portal. This app does not approve "
        "VNM, clear technical feasibility, or execute a PPA."
    )
    disclaimer: str = (
        "Preliminary VNM analysis only — not BESCOM approval or technical clearance."
    )
