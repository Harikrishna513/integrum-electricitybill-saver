from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class EvType(str, Enum):
    NONE = "none"
    TWO_WHEELER = "2w"
    FOUR_WHEELER = "4w"
    BOTH = "both"


class HouseholdApplianceProfile(BaseModel):
    """Optional questionnaire answers from the user."""

    people_count: int = Field(default=3, ge=1, le=20)
    ac_count: int = Field(default=0, ge=0, le=10)
    ac_hours_per_day: float | None = Field(default=None, ge=0, le=24)
    geyser: bool = False
    geyser_hours_per_day: float | None = Field(default=None, ge=0, le=24)
    refrigerator: bool = True
    washing_machine: bool = False
    fan_count: int = Field(default=3, ge=0, le=30)
    fan_hours_per_day: float | None = Field(default=None, ge=0, le=24)
    water_pump: bool = False
    induction: bool = False
    ev_type: EvType = EvType.NONE
    # Optional overrides for power ratings (watts) if user knows them
    ac_watts: float | None = None
    geyser_watts: float | None = None


class ApplianceEstimate(BaseModel):
    appliance_id: str
    label: str
    estimated_kwh_month: float
    share_of_estimated_total_percent: float
    share_of_bill_units_percent: float | None = None
    assumptions: dict = Field(default_factory=dict)
    note: str = (
        "Estimated contribution based on user-provided usage assumptions — "
        "not a measured appliance meter reading."
    )


class ApplianceAnalysisResult(BaseModel):
    status: Literal["ESTIMATED", "INVALID_INPUT"] = "ESTIMATED"
    profile: HouseholdApplianceProfile
    bill_units: float | None = None
    estimated_total_kwh: float
    bill_coverage_ratio: float | None = None
    appliances: list[ApplianceEstimate] = Field(default_factory=list)
    top_loads: list[str] = Field(default_factory=list)
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str
    disclaimer: str = (
        "These are approximate estimates from assumptions, not actual measured "
        "appliance-level consumption."
    )
