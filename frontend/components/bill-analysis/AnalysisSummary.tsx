import type { BillAnalysis, BatchItem } from "@/lib/bill-analysis";
import { formatCurrency, formatUnits } from "@/lib/bill-analysis";
import type { BatchAggregate } from "@/lib/batch-aggregate";

type Props = {
  analysis: BillAnalysis | null;
  batchAggregate?: BatchAggregate | null;
  selectedMonthLabel?: string | null;
  onEditConfirmed?: () => void;
};
export function AnalysisSummary({ analysis, batchAggregate, selectedMonthLabel, onEditConfirmed }: Props) {
  if (!analysis && !batchAggregate) {
    return (
      <aside className="summary-card empty">
        <h2>Bill status</h2>
        <p>Upload your BESCOM bill to see extraction status and analysis summary.</p>
      </aside>
    );
  }

  if (!analysis && batchAggregate) {
    return (
      <aside className="summary-card">
        <div className="summary-header">
          <h2>{batchAggregate.billCount} bills</h2>
        </div>
        <p className="summary-message">{batchAggregate.periodLabel}</p>
        <div className="metric-grid">
          <Metric label="Total units" value={formatUnits(batchAggregate.totalUnits)} />
          <Metric label="Total billed" value={formatCurrency(batchAggregate.totalAmount)} />
          <Metric label="Avg / month" value={formatUnits(batchAggregate.avgUnits)} />
          <Metric label="Avg bill" value={formatCurrency(batchAggregate.avgAmount)} />
        </div>
        <p className="summary-note">Select a month to review or confirm.</p>
      </aside>
    );
  }

  if (!analysis) {
    return null;
  }

  const units =
    analysis.calculations?.units_consumed ??
    findField(analysis, "units_consumed");
  const monthlyEquiv = analysis.calculations?.monthly_units_equivalent;
  const multiMonth = analysis.calculations?.is_multi_month_period === true;
  const consumptionLabel = multiMonth ? "Consumption (period)" : "Consumption";
  const consumptionValue =
    multiMonth && monthlyEquiv != null && units != null
      ? `${formatUnits(units as number)} (~${formatUnits(monthlyEquiv)}/mo avg)`
      : formatUnits(units as number);
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
      {selectedMonthLabel && (
        <p className="summary-note">Reviewing: {selectedMonthLabel}</p>
      )}
      <p className="summary-message">{analysis.message}</p>

      {analysis.status === "ready" && onEditConfirmed && (
        <button type="button" className="ghost edit-bill-btn" onClick={onEditConfirmed}>
          Edit extracted bill details
        </button>
      )}

      {analysis.status === "unsupported" ? (
        <div className="alert info">
          You can still review extracted information, but Karnataka/BESCOM domestic
          analysis is not available for this bill.
        </div>
      ) : null}

      {(analysis.status === "ready" || analysis.calculations) && (
        <>
          {analysis.status === "ready" && analysis.message && (
            <p className="summary-headline">{analysis.message}</p>
          )}
          <div className="metric-grid">
            <Metric label={consumptionLabel} value={consumptionValue} />
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

          {analysis.calculations?.notes.map((note, i) => (
            <p key={`calc-note-${i}`} className="summary-note">
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
          {analysis.history.duplicate_warnings.map((w, i) => (
            <p key={`dup-warn-${i}`} className="summary-note warn">
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

export function BatchResults({
  items,
  selectedId,
  onSelect,
}: {
  items: BatchItem[];
  selectedId?: string | null;
  onSelect?: (item: BatchItem) => void;
}) {
  if (!items.length) return null;
  return (
    <div className="batch-results">
      <h3>
        {items.length} bill{items.length !== 1 ? "s" : ""} uploaded
        {items.length > 1 ? " — select a month to review" : ""}
      </h3>
      <ul>
        {items.map((item) => {
          const active = selectedId === item.analysis_id;
          return (
            <li
              key={item.filename}
              className={`${item.status} ${active ? "selected" : ""}`}
            >
              <div>
                <strong>{item.filename}</strong>
                <span>
                  {item.billing_period || item.status}
                  {item.units_consumed != null ? ` · ${item.units_consumed} kWh` : ""}
                  {item.total_amount != null
                    ? ` · ₹${item.total_amount.toLocaleString("en-IN")}`
                    : ""}
                </span>
              </div>
              {item.error ? (
                <span className="batch-status bad">Failed</span>
              ) : onSelect && item.analysis ? (
                <button
                  type="button"
                  className={`ghost batch-review-btn ${active ? "active" : ""}`}
                  onClick={() => onSelect(item)}
                >
                  {active
                    ? editingLabel(item.status)
                    : item.status === "ready"
                      ? "Edit"
                      : "Review"}
                </button>
              ) : (
                <span className="batch-status">
                  {item.status === "needs_review" ? "Review" : "OK"}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function editingLabel(status: string) {
  return status === "ready" ? "Editing" : "Reviewing";
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
