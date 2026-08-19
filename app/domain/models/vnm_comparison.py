"""VNM bill comparison — individual consumer vs Integrum VNM (no society assumptions)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BillLineItem(BaseModel):
    code: str
    label: str
    amount: float
    detail: str | None = None


class BillScenario(BaseModel):
    title: str
    subtitle: str | None = None
    lines: list[BillLineItem] = Field(default_factory=list)
    total: float
    units_kwh: float | None = None
    notes: list[str] = Field(default_factory=list)


class VNMSetupCost(BaseModel):
    label: str
    amount_inr: float
    detail: str
    per_flat_inr: float | None = None


class VNMComparisonView(BaseModel):
    provider: str
    provider_website: str | None = None

    # Confirmed bill facts (from uploaded & confirmed bill only)
    sanctioned_load_kw: float
    billing_period: str | None = None
    period_units_kwh: float
    monthly_units: float
    billing_period_months: float = 1.0
    is_multi_month_period: bool = False
    period_consumption_note: str | None = None
    current_bill_total_inr: float

    # User-provided VNM scenario (from provider/society — not from the bill)
    expected_vnm_solar_credit_kwh: float | None = None
    needs_expected_credit: bool = False
    credit_input_prompt: str | None = None
    scenario_label: str = ""
    solar_kwh_credited: float = 0
    residual_grid_kwh: float = 0

    # Signed outcome: positive = cheaper with VNM, negative = more expensive
    period_difference_inr: float
    monthly_difference_inr: float
    annual_difference_inr: float
    is_vnm_cheaper: bool
    period_saving_inr: float
    period_increase_inr: float
    monthly_saving_inr: float
    monthly_increase_inr: float
    annual_saving_inr: float
    annual_increase_inr: float

    current_bill: BillScenario
    vnm_bill: BillScenario
    assumptions: list[str] = Field(default_factory=list)
    disclaimer: str

    # Legacy society fields — unused in individual comparison (kept for API compat)
    user_share_percent: float | None = None
    community_plant_kwp: float | None = None
    assumed_flats: int | None = None
    one_time_costs: list[VNMSetupCost] = Field(default_factory=list)
    one_time_total_society_inr: float | None = None
    one_time_per_flat_inr: float | None = None
