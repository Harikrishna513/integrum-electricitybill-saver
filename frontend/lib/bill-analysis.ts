export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW" | "MISSING";

export type BillAnalysisStatus =
  | "needs_review"
  | "ready"
  | "unsupported"
  | "error";

export type BillField = {
  name: string;
  label: string;
  section: string;
  value: string | number | boolean | null;
  display_value: string;
  confidence: number;
  level: ConfidenceLevel;
  source: string;
  needs_verification: boolean;
  editable: boolean;
  required?: boolean;
};

export type BillSection = {
  id: string;
  title: string;
  fields: BillField[];
};

export type SupportInfo = {
  supported: boolean;
  state: string;
  discom: string | null;
  category: string | null;
  is_bescom_bill: boolean | null;
  can_analyze: boolean;
  message: string;
  block_reasons: string[];
};

export type BillCalculation = {
  units_consumed: number | null;
  total_amount: number | null;
  cost_per_unit: number | null;
  charge_lines_sum: number | null;
  charge_total_delta: number | null;
  annualized_units_estimate: number | null;
  annualized_amount_estimate: number | null;
  notes: string[];
};

export type HistoryBill = {
  analysis_id: string;
  billing_period: string | null;
  bill_date: string | null;
  units_consumed: number | null;
  total_amount: number | null;
};

export type HistorySummary = {
  consumer_id: string | null;
  bill_count: number;
  ready_for_trend_analysis: boolean;
  bills: HistoryBill[];
  duplicate_warnings: string[];
};

export type BillAnalysis = {
  analysis_id: string;
  status: BillAnalysisStatus;
  message: string;
  document: Record<string, unknown>;
  sections: BillSection[];
  support: SupportInfo;
  validation_issues: { code: string; message: string; field?: string; severity: string }[];
  consistency_warnings: string[];
  needs_confirmation: string[];
  calculations: BillCalculation | null;
  history: HistorySummary | null;
  corrections_audit: unknown[];
  confirmed: boolean;
};

export type ExtractResponse = {
  message: string;
  analysis: BillAnalysis;
};

export type BatchItem = {
  filename: string;
  status: string;
  analysis_id?: string;
  billing_period?: string | null;
  units_consumed?: number | null;
  total_amount?: number | null;
  needs_confirmation?: string[];
  duplicate_warnings?: string[];
  error?: string;
  analysis?: BillAnalysis;
};

export type BatchResponse = {
  message: string;
  processed: number;
  successful: number;
  needs_review: number;
  failed: number;
  items: BatchItem[];
};

export type ProcessingStep =
  | "idle"
  | "uploading"
  | "reading"
  | "extracting"
  | "validating"
  | "checking"
  | "review"
  | "ready"
  | "error";

export const PROCESSING_LABELS: Record<ProcessingStep, string> = {
  idle: "",
  uploading: "Uploading…",
  reading: "Reading bill…",
  extracting: "Extracting details…",
  validating: "Validating…",
  checking: "Checking BESCOM eligibility…",
  review: "Ready for review",
  ready: "Analysis ready",
  error: "Processing failed",
};

export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return "—";
  return `₹${value.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

export function formatUnits(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toLocaleString("en-IN", { maximumFractionDigits: 1 })} kWh`;
}

export function maskAccount(value: string | null | undefined): string {
  if (!value) return "";
  if (value.length <= 4) return value;
  return `${"*".repeat(Math.max(0, value.length - 4))}${value.slice(-4)}`;
}
