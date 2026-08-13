import type { BillAnalysis, BatchItem } from "@/lib/bill-analysis";
import { formatCurrency, formatUnits } from "@/lib/bill-analysis";

type Props = {
  analysis: BillAnalysis | null;
};

export function AnalysisSummary({ analysis }: Props) {
  if (!analysis) {
    return (
      <aside className="summary-card empty">
        <h2>Bill status</h2>
        <p>Upload your BESCOM bill to see extraction status and analysis summary.</p>
      </aside>
    );
  }

  const units =
    analysis.calculations?.units_consumed ??
    findField(analysis, "units_consumed");
  const total =
    analysis.calculations?.total_amount ?? findField(analysis, "total_amount");
  const period = findField(analysis, "billing_period");
  const discom = findField(analysis, "discom") || "BESCOM";
  const category = analysis.support.category || "Domestic";

  return (
    <aside className="summary-card">
      <div className="summary-header">
        <h2>Bill status</h2>
        <StatusPill status={analysis.status} />
      </div>
      <p className="summary-message">{analysis.message}</p>

      {analysis.status === "unsupported" ? (
        <div className="alert info">
          You can still review extracted information, but Karnataka/BESCOM domestic
          analysis is not available for this bill.
        </div>
      ) : null}

      {(analysis.status === "ready" || analysis.calculations) && (
        <>
          <div className="metric-grid">
            <Metric label="Consumption" value={formatUnits(units as number)} />
            <Metric label="Bill amount" value={formatCurrency(total as number)} />
            <Metric label="Billing period" value={String(period || "—")} />
            <Metric label="Category" value={String(category)} />
            <Metric label="DISCOM" value={String(discom)} />
            {analysis.calculations?.cost_per_unit != null && (
              <Metric
                label="Cost per unit"
                value={formatCurrency(analysis.calculations.cost_per_unit)}
              />
            )}
          </div>

          {analysis.calculations?.notes.map((note) => (
            <p key={note} className="summary-note">
              {note}
            </p>
          ))}
        </>
      )}

      {analysis.history && analysis.history.bills.length > 0 && (
        <div className="history-block">
          <h3>Consumption history</h3>
          <ul>
            {analysis.history.bills.map((b) => (
              <li key={b.analysis_id}>
                <span>{b.billing_period || b.bill_date || "Bill"}</span>
                <span>{formatUnits(b.units_consumed)}</span>
                <span>{formatCurrency(b.total_amount)}</span>
              </li>
            ))}
          </ul>
          {analysis.history.duplicate_warnings.map((w) => (
            <p key={w} className="summary-note warn">
              {w}
            </p>
          ))}
        </div>
      )}

      {analysis.validation_issues.length > 0 && (
        <div className="issues-block">
          <h3>Validation notes</h3>
          <ul>
            {analysis.validation_issues.map((i) => (
              <li key={`${i.code}-${i.field}`}>{i.message}</li>
            ))}
          </ul>
        </div>
      )}
    </aside>
  );
}

export function BatchResults({ items }: { items: BatchItem[] }) {
  if (!items.length) return null;
  return (
    <div className="batch-results">
      <h3>Uploaded bills</h3>
      <ul>
        {items.map((item) => (
          <li key={item.filename} className={item.status}>
            <div>
              <strong>{item.filename}</strong>
              <span>
                {item.billing_period || item.status}
                {item.units_consumed != null ? ` · ${item.units_consumed} kWh` : ""}
              </span>
            </div>
            <span className="batch-status">
              {item.error ? "Failed" : item.status === "needs_review" ? "Review" : "OK"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  return <span className={`pill ${status}`}>{status.replace("_", " ")}</span>;
}

function findField(analysis: BillAnalysis, name: string): unknown {
  for (const section of analysis.sections) {
    const field = section.fields.find((f) => f.name === name);
    if (field) return field.value;
  }
  return null;
}
