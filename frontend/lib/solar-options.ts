export type SolarOptionKind = "individual_solar" | "vnm" | "gnm";

export type BillSolarPrefill = {
  analysis_id: string;
  connection_id: string;
  consumer_name: string | null;
  address: string | null;
  period_units_kwh: number;
  monthly_units: number;
  sanctioned_load_kw: number;
  current_monthly_bill_inr: number | null;
  tariff_code: string;
  discom: string;
  category: string;
  as_of: string;
  suggested_plant_kwp: number | null;
  bill_date: string | null;
  billing_period: string | null;
  billing_period_days?: number | null;
  billing_period_months?: number;
  is_multi_month_period?: boolean;
  period_consumption_note?: string | null;
};

export type SolarOptionCard = {
  option: SolarOptionKind;
  title: string;
  status: string;
  monthly_saving_inr: number | null;
  plant_kwp: number | null;
  message: string;
  official_next_step: string | null;
  missing_inputs: string[];
  warnings: string[];
  result: Record<string, unknown>;
  intelligence_report: SolarIntelligenceReport | null;
};

export type ReportMetric = {
  label: string;
  value: string;
  detail: string | null;
};

export type ReportSection = {
  id: string;
  title: string;
  metrics: ReportMetric[];
};

export type SolarIntelligenceReport = {
  option: SolarOptionKind;
  title: string;
  status: string;
  headline: string;
  location_line: string;
  property_type: string;
  sections: ReportSection[];
  disclaimer: string;
  actions: string[];
};

export type BillLineItem = {
  code: string;
  label: string;
  amount: number;
  detail: string | null;
};

export type BillScenario = {
  title: string;
  subtitle: string | null;
  lines: BillLineItem[];
  total: number;
  units_kwh: number | null;
  notes: string[];
};

export type MonthlyBillEstimate = {
  month_index: number;
  month_label: string;
  calendar_month: number;
  seasonal_factor: number;
  estimated_units_kwh: number;
  estimated_bescom_bill_inr: number;
  estimated_vnm_bill_inr: number;
  estimated_saving_inr: number;
};

export type VNMMethodology = {
  monthly_baseline_kwh: number;
  coverage_fraction: number;
  coverage_label: string;
  coverage_source: string;
  illustrative_plant_kwp: number | null;
  monthly_kwh_per_kwp: number | null;
  illustrative_rate_inr_per_kwh: number;
  gst_percent: number;
  seasonal_model_label: string;
  steps: string[];
};

export type VNMSetupCost = {
  label: string;
  amount_inr: number;
  detail: string;
  per_flat_inr: number | null;
};

export type VNMComparison = {
  provider: string;
  provider_website: string | null;
  sanctioned_load_kw: number;
  billing_period: string | null;
  period_units_kwh: number;
  monthly_units: number;
  billing_period_months?: number;
  is_multi_month_period?: boolean;
  period_consumption_note?: string | null;
  current_bill_total_inr: number;
  expected_vnm_solar_credit_kwh: number | null;
  needs_expected_credit: boolean;
  credit_input_prompt: string | null;
  scenario_label: string;
  solar_kwh_credited: number;
  residual_grid_kwh: number;
  estimated_generation_kwh: number;
  surplus_kwh: number;
  illustrative_coverage_fraction: number;
  coverage_source: string;
  illustrative_plant_kwp: number;
  monthly_kwh_per_kwp: number;
  plant_slider_min_kwp: number;
  plant_slider_max_kwp: number;
  plant_slider_step_kwp: number;
  default_plant_kwp: number;
  surplus_note: string | null;
  illustrative_rate_inr_per_kwh: number;
  gst_percent: number;
  vnm_energy_cost_inr: number;
  vnm_gst_inr: number;
  vnm_service_total_inr: number;
  residual_bescom_charges_inr: number;
  has_gruha_jyothi: boolean;
  gruha_jyothi_note: string | null;
  period_difference_inr: number;
  monthly_difference_inr: number;
  annual_difference_inr: number;
  is_vnm_cheaper: boolean;
  period_saving_inr: number;
  period_increase_inr: number;
  monthly_saving_inr: number;
  monthly_increase_inr: number;
  annual_saving_inr: number;
  annual_increase_inr: number;
  current_bill: BillScenario;
  vnm_bill: BillScenario;
  calculation_detail_lines: BillLineItem[];
  monthly_chart: MonthlyBillEstimate[];
  methodology: VNMMethodology | null;
  cta_primary: string;
  cta_secondary: string;
  cta_url: string;
  assumptions: string[];
  disclaimer: string;
};

export type SolarOptionsComparison = {
  analysis_id: string;
  prefill: BillSolarPrefill;
  options: SolarOptionCard[];
  best_option: SolarOptionKind | null;
  vnm_comparison: VNMComparison | null;
  disclaimer: string;
  message: string;
};

export type SolarOptionsResponse = {
  message: string;
  comparison: SolarOptionsComparison;
};

export type VNMParticipantInput = {
  connection_id: string;
  category?: string;
  monthly_units?: number;
  sanctioned_load_kw?: number;
  procurement_share_percent?: number;
};

export type GNMInstallationInput = {
  connection_id: string;
  category?: string;
  monthly_units?: number;
  sanctioned_load_kw?: number;
  priority?: number;
  is_host?: boolean;
};

export type CompareSolarOptionsPayload = {
  plant?: {
    proposed_kwp?: number;
    roof_area_m2?: number;
    same_discom_area?: boolean;
    same_consumer_name?: boolean;
  };
  vnm_participants?: VNMParticipantInput[];
  gnm_installations?: GNMInstallationInput[];
  include_individual_solar?: boolean;
  include_vnm?: boolean;
  include_gnm?: boolean;
  expected_vnm_solar_credit_kwh?: number;
  illustrative_plant_kwp?: number;
  illustrative_coverage_fraction?: number;
};

/** 1 sq ft ≈ 0.092903 m² */
export const SQFT_TO_M2 = 0.092903;

export const OPTION_LABELS: Record<SolarOptionKind, string> = {
  individual_solar: "Individual rooftop",
  vnm: "Virtual Net Metering (VNM)",
  gnm: "Group Net Metering (GNM)",
};

export function statusClass(status: string): string {
  if (status === "ESTIMATED" || status === "POTENTIALLY_SUITABLE") return "ok";
  if (status === "INSUFFICIENT_INFORMATION" || status === "NO_ROOF") return "warn";
  return "bad";
}
