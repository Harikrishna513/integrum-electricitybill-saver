"use client";

import { formatCurrency, formatUnits } from "@/lib/bill-analysis";
import type { BatchAggregate } from "@/lib/batch-aggregate";

type Props = {
  aggregate: BatchAggregate;
  selectedId: string | null;
  onSelectMonth: (analysisId: string) => void;
};

export function MultiBillSummary({ aggregate, selectedId, onSelectMonth }: Props) {
  const maxUnits = Math.max(...aggregate.months.map((m) => m.units ?? 0), 1);

  return (
    <section className="multi-bill-summary">
      <header>
        <p className="sir-eyebrow">Consumption history</p>
        <h2>{aggregate.billCount} months · {aggregate.periodLabel}</h2>
        {aggregate.accountId && (
          <p className="hint">Account {aggregate.accountId}</p>
        )}
        {!aggregate.allSameAccount && (
          <p className="summary-note warn">
            Bills may belong to different accounts — verify account ID on each month.
          </p>
        )}
      </header>

      <div className="multi-bill-totals">
        <div className="metric">
          <span>Total units</span>
          <strong>{formatUnits(aggregate.totalUnits)}</strong>
        </div>
        <div className="metric">
          <span>Total billed</span>
          <strong>{formatCurrency(aggregate.totalAmount)}</strong>
        </div>
        <div className="metric">
          <span>Avg / month</span>
          <strong>{formatUnits(aggregate.avgUnits)}</strong>
        </div>
        <div className="metric">
          <span>Avg bill</span>
          <strong>{formatCurrency(aggregate.avgAmount)}</strong>
        </div>
        {(aggregate.meterStart != null || aggregate.meterEnd != null) && (
          <div className="metric">
            <span>Meter (period)</span>
            <strong>
              {aggregate.meterStart ?? "—"} → {aggregate.meterEnd ?? "—"}
            </strong>
          </div>
        )}
      </div>

      <div className="monthly-usage-chart">
        <h3>Monthly usage</h3>
        <ul>
          {aggregate.months.map((m) => {
            const pct = m.units != null ? (m.units / maxUnits) * 100 : 0;
            const active = m.analysisId === selectedId;
            return (
              <li key={m.key} className={active ? "active" : ""}>
                <button
                  type="button"
                  className="month-row-btn"
                  onClick={() => m.analysisId && onSelectMonth(m.analysisId)}
                  disabled={!m.analysisId || !!m.error}
                >
                  <span className="month-label">{m.label}</span>
                  <span className="month-bar-wrap">
                    <span
                      className="month-bar"
                      style={{ width: `${Math.max(pct, 4)}%` }}
                    />
                  </span>
                  <span className="month-units">{formatUnits(m.units)}</span>
                  <span className="month-amount">{formatCurrency(m.amount)}</span>
                  <span className={`pill small ${m.status}`}>
                    {m.error ? "failed" : m.status.replace(/_/g, " ")}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
