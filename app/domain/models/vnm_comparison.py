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


class MonthlyBillEstimate(BaseModel):
    month_index: int
    month_label: str
    calendar_month: int
    seasonal_factor: float
    estimated_units_kwh: float
    estimated_bescom_bill_inr: float
    estimated_vnm_bill_inr: float
    estimated_saving_inr: float


class VNMMethodology(BaseModel):
    monthly_baseline_kwh: float
    coverage_fraction: float
    coverage_label: str
    coverage_source: str
    illustrative_plant_kwp: float | None = None
    monthly_kwh_per_kwp: float | None = None
    illustrative_rate_inr_per_kwh: float
    gst_percent: float
    seasonal_model_label: str
    steps: list[str] = Field(default_factory=list)


class VNMSetupCost(BaseModel):
    label: str
    amount_inr: float
    detail: str
    per_flat_inr: float | None = None


class VNMComparisonView(BaseModel):
    provider: str
    provider_website: str | None = None

    # Confirmed bill facts
    sanctioned_load_kw: float
    billing_period: str | None = None
    period_units_kwh: float
    monthly_units: float
    billing_period_months: float = 1.0
    is_multi_month_period: bool = False
    period_consumption_note: str | None = None
    current_bill_total_inr: float

    # Scenario (illustrative coverage or advanced quote)
    expected_vnm_solar_credit_kwh: float | None = None
    needs_expected_credit: bool = False
    credit_input_prompt: str | None = None
    scenario_label: str = ""
    solar_kwh_credited: float = 0
    residual_grid_kwh: float = 0
    estimated_generation_kwh: float = 0
    surplus_kwh: float = 0
    illustrative_coverage_fraction: float = 1.0
    coverage_source: str = "illustrative_plant"
    illustrative_plant_kwp: float = 1.0
    monthly_kwh_per_kwp: float = 120.0
    plant_slider_min_kwp: float = 0.5
    plant_slider_max_kwp: float = 10.0
    plant_slider_step_kwp: float = 0.5
    default_plant_kwp: float = 1.0
    surplus_note: str | None = None

    # Rate
    illustrative_rate_inr_per_kwh: float = 3.0
    gst_percent: float = 18.0
    vnm_energy_cost_inr: float = 0
    vnm_gst_inr: float = 0
    vnm_service_total_inr: float = 0
    residual_bescom_charges_inr: float = 0

    # Gruha Jyothi
    has_gruha_jyothi: bool = False
    gruha_jyothi_note: str | None = None

    # Outcomes
    period_difference_inr: float = 0
    monthly_difference_inr: float = 0
    annual_difference_inr: float = 0
    is_vnm_cheaper: bool = False
    period_saving_inr: float = 0
    period_increase_inr: float = 0
    monthly_saving_inr: float = 0
    monthly_increase_inr: float = 0
    annual_saving_inr: float = 0
    annual_increase_inr: float = 0

    current_bill: BillScenario
    vnm_bill: BillScenario
    calculation_detail_lines: list[BillLineItem] = Field(default_factory=list)
    monthly_chart: list[MonthlyBillEstimate] = Field(default_factory=list)
    methodology: VNMMethodology | None = None
    cta_primary: str = "Get your VNM proposal"
    cta_secondary: str = "Talk to Integrum"
    cta_url: str = "https://integrumenergy.in/contact/"
    assumptions: list[str] = Field(default_factory=list)
    disclaimer: str

    # Legacy society fields — unused (API compat)
    user_share_percent: float | None = None
    community_plant_kwp: float | None = None
    assumed_flats: int | None = None
    one_time_costs: list[VNMSetupCost] = Field(default_factory=list)
    one_time_total_society_inr: float | None = None
    one_time_per_flat_inr: float | None = None
