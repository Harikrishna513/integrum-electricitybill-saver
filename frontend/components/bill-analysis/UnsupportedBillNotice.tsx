import type { BillAnalysis } from "@/lib/bill-analysis";
import { formatCurrency, formatUnits } from "@/lib/bill-analysis";

type Props = {
  analysis: BillAnalysis;
};

export function UnsupportedBillNotice({ analysis }: Props) {
  const units = findField(analysis, "units_consumed");
  const total = findField(analysis, "total_amount");
  const discom = findField(analysis, "discom");

  return (
    <div className="unsupported-panel">
      <h2>Bill not supported for analysis</h2>
      <p>{analysis.support.message}</p>
      <p>
        This version supports Karnataka BESCOM domestic bills only. You can still
        see what we extracted below, but bill calculations and savings modules
        are not available.
      </p>
      {(units != null || total != null) && (
        <div className="metric-grid compact">
          {units != null && (
            <div className="metric">
              <span>Units detected</span>
              <strong>{formatUnits(units as number)}</strong>
            </div>
          )}
          {total != null && (
            <div className="metric">
              <span>Amount detected</span>
              <strong>{formatCurrency(total as number)}</strong>
            </div>
          )}
          {discom != null && (
            <div className="metric">
              <span>DISCOM</span>
              <strong>{String(discom)}</strong>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function findField(analysis: BillAnalysis, name: string): unknown {
  for (const section of analysis.sections) {
    const field = section.fields.find((f) => f.name === name);
    if (field?.value != null && field.value !== "") return field.value;
  }
  return null;
}
