from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SolarAnalysisStatus(str, Enum):
    ESTIMATED = "ESTIMATED"
    NO_ROOF = "NO_ROOF"
    INVALID_INPUT = "INVALID_INPUT"
    TARIFF_UNAVAILABLE = "TARIFF_UNAVAILABLE"
    UNSUPPORTED_CATEGORY = "UNSUPPORTED_CATEGORY"


class SolarProfile(BaseModel):
    """Inputs for individual rooftop solar planning."""

    monthly_units: float = Field(ge=0, description="Typical monthly consumption (kWh).")
    as_of: date
    sanctioned_load_kw: float = Field(default=3.0, ge=0)
    roof_area_m2: float | None = Field(
        default=None,
        ge=0,
        description="Usable shadow-free roof area in m². None/0 → no individual rooftop.",
    )
    proposed_kwp: float | None = Field(
        default=None,
        ge=0,
        description="If set, analyze this capacity instead of recommending one.",
    )
    apply_cfa_estimate: bool = True
    discom: str = "BESCOM"
    category: str = "DOMESTIC"
    tariff_code: str | None = "LT-1"


class SolarSizing(BaseModel):
    recommended_kwp: float
    analyzed_kwp: float
    raw_kwp_before_caps: float
    capped_by: list[str] = Field(default_factory=list)
    max_from_roof_kwp: float | None = None
    max_from_load_kwp: float | None = None


class SolarGenerationEstimate(BaseModel):
    specific_yield_kwh_per_kwp_year: float
    estimated_annual_generation_kwh: float
    estimated_monthly_generation_kwh: float


class SolarEconomics(BaseModel):
    gross_capex_inr: float
    estimated_cfa_inr: float | None = None
    net_capex_inr: float
    current_monthly_bill_estimate: float | None = None
    estimated_monthly_bill_after_solar: float | None = None
    estimated_monthly_saving_inr: float | None = None
    estimated_annual_saving_inr: float | None = None
    simple_payback_years: float | None = None
    tariff_rule_version: str | None = None
    tariff_verification_status: str | None = None


class SolarAnalysisResult(BaseModel):
    status: SolarAnalysisStatus
    profile: SolarProfile
    rule_version: str | None = None
    verification_status: str | None = None
    source: str | None = None

    sizing: SolarSizing | None = None
    generation: SolarGenerationEstimate | None = None
    economics: SolarEconomics | None = None

    monthly_units_before: float | None = None
    estimated_monthly_units_after_offset: float | None = None
    estimated_monthly_units_offset: float | None = None

    offset_model: str | None = None
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    message: str
    disclaimer: str = (
        "Estimated rooftop solar planning only. Not a BESCOM sanction, CFA approval, "
        "or installer quote. Simplified bill-offset model — net metering detail is Milestone 15."
    )
