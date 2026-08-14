export type SolarOptionKind = "individual_solar" | "vnm" | "gnm";

export type BillSolarPrefill = {
  analysis_id: string;
  connection_id: string;
  consumer_name: string | null;
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
};

export type SolarOptionsComparison = {
  analysis_id: string;
  prefill: BillSolarPrefill;
  options: SolarOptionCard[];
  best_option: SolarOptionKind | null;
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
};

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
