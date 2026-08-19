"use client";

import type { BillAnalysis } from "@/lib/bill-analysis";
import { formatCurrency, formatUnits } from "@/lib/bill-analysis";

type Props = {
  analysis: BillAnalysis;
};

/**
 * Shown when automatic support gate failed but user should still complete the review form
 * (partial image, missing tariff, unclear category).
 */
export function PartialBillNotice({ analysis }: Props) {
  const units = findField(analysis, "units_consumed");
  const total = findField(analysis, "total_amount");
  const discom = findField(analysis, "discom");
  const isBescom = looksLikeBescom(analysis, discom);

  if (analysis.support.supported) return null;

  return (
    <div className="unsupported-panel partial">
      <h2>
        {isBescom
          ? "Partial or unclear bill — please complete details"
          : "Bill not supported for automatic analysis"}
      </h2>
      <p>{analysis.message || analysis.support.message}</p>
      {isBescom ? (
        <p>
          We detected <strong>BESCOM</strong> and some charge values, but the photo may be
          cropped or missing the top section (RR number, tariff, name). Use the form below
          to enter DISCOM, tariff code, account ID, and other required fields manually.
        </p>
      ) : (
        <p>
          This version supports Karnataka BESCOM domestic bills only. If this is a BESCOM
          bill, set <strong>BESCOM Bill</strong> to Yes in the form and fill the required
          fields.
        </p>
      )}
      {(units != null || total != null || discom != null) && (
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
              <span>DISCOM detected</span>
              <strong>{String(discom)}</strong>
            </div>
          )}
        </div>
      )}
      {analysis.support.block_reasons.map((reason, i) => (
        <p key={`block-${i}`} className="summary-note warn">
          {reason}
        </p>
      ))}
    </div>
  );
}

function looksLikeBescom(analysis: BillAnalysis, discom: unknown): boolean {
  if (analysis.support.is_bescom_bill === true) return true;
  if (typeof discom === "string" && discom.toUpperCase().includes("BESCOM")) return true;
  return false;
}

function findField(analysis: BillAnalysis, name: string): unknown {
  for (const section of analysis.sections) {
    const field = section.fields.find((f) => f.name === name);
    if (field?.value != null && field.value !== "") return field.value;
  }
  return null;
}
