import type { BatchItem, BillAnalysis } from "@/lib/bill-analysis";

export type MonthlyBillRow = {
  key: string;
  analysisId: string | undefined;
  label: string;
  billDate: string | null;
  units: number | null;
  amount: number | null;
  status: string;
  filename: string;
  error?: string;
  analysis?: BillAnalysis;
};

export type BatchAggregate = {
  billCount: number;
  periodLabel: string;
  totalUnits: number;
  totalAmount: number;
  avgUnits: number;
  avgAmount: number;
  meterStart: number | null;
  meterEnd: number | null;
  accountId: string | null;
  months: MonthlyBillRow[];
  allSameAccount: boolean;
};

function fieldValue(analysis: BillAnalysis | undefined, name: string): unknown {
  if (!analysis) return null;
  for (const section of analysis.sections) {
    const f = section.fields.find((x) => x.name === name);
    if (f?.value != null) return f.value;
  }
  return null;
}

function parseDateSortKey(row: MonthlyBillRow): string {
  if (row.billDate) return row.billDate;
  return row.label;
}

export function batchRows(items: BatchItem[]): MonthlyBillRow[] {
  return items.map((item) => {
    const analysis = item.analysis;
    const billDate =
      (fieldValue(analysis, "bill_date") as string | null) ??
      (analysis?.history?.bills.find((b) => b.analysis_id === item.analysis_id)
        ?.bill_date ??
        null);
    const period =
      item.billing_period ??
      (fieldValue(analysis, "billing_period") as string | null) ??
      billDate ??
      item.filename;
    return {
      key: item.analysis_id ?? item.filename,
      analysisId: item.analysis_id,
      label: String(period),
      billDate: billDate ? String(billDate) : null,
      units: item.units_consumed ?? null,
      amount: item.total_amount ?? null,
      status: item.error ? "error" : item.status,
      filename: item.filename,
      error: item.error,
      analysis,
    };
  });
}

export function computeBatchAggregate(items: BatchItem[]): BatchAggregate | null {
  if (items.length < 2) return null;

  const months = batchRows(items).sort((a, b) =>
    parseDateSortKey(a).localeCompare(parseDateSortKey(b))
  );

  const accountIds = new Set(
    months
      .map((m) => fieldValue(m.analysis, "account_id"))
      .filter((v): v is string => typeof v === "string" && v.length > 0)
  );

  const withUnits = months.filter((m) => m.units != null);
  const withAmount = months.filter((m) => m.amount != null);
  const totalUnits = withUnits.reduce((s, m) => s + (m.units ?? 0), 0);
  const totalAmount = withAmount.reduce((s, m) => s + (m.amount ?? 0), 0);

  const oldest = months[0]?.analysis;
  const newest = months[months.length - 1]?.analysis;
  const meterStart = num(fieldValue(oldest, "previous_meter_reading"));
  const meterEnd = num(fieldValue(newest, "current_meter_reading"));

  const dates = months
    .map((m) => m.billDate)
    .filter((d): d is string => !!d)
    .sort();
  let periodLabel = `${months.length} billing months`;
  if (dates.length >= 2) {
    periodLabel = `${formatShortDate(dates[0])} – ${formatShortDate(dates[dates.length - 1])}`;
  } else if (dates.length === 1) {
    periodLabel = formatShortDate(dates[0]);
  } else if (months.length >= 2) {
    periodLabel = `${months[0].label} – ${months[months.length - 1].label}`;
  }

  return {
    billCount: months.length,
    periodLabel,
    totalUnits,
    totalAmount,
    avgUnits: withUnits.length ? totalUnits / withUnits.length : 0,
    avgAmount: withAmount.length ? totalAmount / withAmount.length : 0,
    meterStart,
    meterEnd,
    accountId: accountIds.size === 1 ? [...accountIds][0] : null,
    months,
    allSameAccount: accountIds.size <= 1,
  };
}

function num(v: unknown): number | null {
  if (v == null) return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function formatShortDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("en-IN", { month: "short", year: "numeric" });
}
