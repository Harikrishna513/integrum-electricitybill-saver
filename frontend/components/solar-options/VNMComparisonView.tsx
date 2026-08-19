"use client";

import { useState } from "react";
import { formatCurrency } from "@/lib/bill-analysis";
import type { VNMComparison } from "@/lib/solar-options";

type Props = {
  comparison: VNMComparison;
  onApplyCredit?: (creditKwh: number) => void;
  recalculating?: boolean;
};

export function VNMComparisonView({
  comparison,
  onApplyCredit,
  recalculating = false,
}: Props) {
  const multiMonth = comparison.is_multi_month_period === true;
  const needsCredit = comparison.needs_expected_credit;
  const [creditInput, setCreditInput] = useState(
    comparison.expected_vnm_solar_credit_kwh?.toString() ?? ""
  );

  const diffBannerClass = comparison.is_vnm_cheaper
    ? "vnm-saving-banner"
    : "vnm-increase-banner";
  const savingLabel = multiMonth
    ? "Estimated saving for this billing period"
    : "Estimated monthly saving";
  const increaseLabel = multiMonth
    ? "Estimated increase for this billing period"
    : "Estimated monthly increase";

  const savingAmount = multiMonth
    ? comparison.period_saving_inr
    : comparison.monthly_saving_inr;
  const increaseAmount = multiMonth
    ? comparison.period_increase_inr
    : comparison.monthly_increase_inr;

  const creditHelp = multiMonth
    ? `Enter kWh for this billing period (${comparison.billing_period ?? "see bill"}). If your provider quotes kWh/month, multiply by ~${comparison.billing_period_months ?? 2} months.`
    : "Enter the expected solar credit for this billing period from your VNM provider or society.";

  function handleApply() {
    const value = Number(creditInput);
    if (!Number.isFinite(value) || value < 0) return;
    onApplyCredit?.(value);
  }

  return (
    <div className="vnm-comparison">
      <header className="vnm-comparison-header">
        <div>
          <p className="sir-eyebrow">VNM via {comparison.provider}</p>
          <h3>Your bill vs Virtual Net Metering</h3>
          {!needsCredit && (
            <p className={diffBannerClass}>
              {comparison.is_vnm_cheaper ? (
                <>
                  {savingLabel}{" "}
                  <strong>{formatCurrency(savingAmount)}</strong>
                  {multiMonth ? (
                    <>
                      {" "}
                      (~{formatCurrency(comparison.monthly_saving_inr)}/month avg)
                    </>
                  ) : null}{" "}
                  ({formatCurrency(comparison.annual_saving_inr)}/year)
                </>
              ) : (
                <>
                  {increaseLabel}{" "}
                  <strong>{formatCurrency(increaseAmount)}</strong>
                  {multiMonth ? (
                    <>
                      {" "}
                      (~{formatCurrency(comparison.monthly_increase_inr)}/month avg)
                    </>
                  ) : null}{" "}
                  ({formatCurrency(comparison.annual_increase_inr)}/year)
                </>
              )}
            </p>
          )}
        </div>
      </header>

      <section className="vnm-credit-input">
        <label htmlFor="vnm-solar-credit">
          Expected / scenario VNM solar credit (kWh)
        </label>
        <p className="summary-note">
          {comparison.credit_input_prompt ?? creditHelp}
        </p>
        <div className="vnm-credit-row">
          <input
            id="vnm-solar-credit"
            type="number"
            min={0}
            max={comparison.period_units_kwh}
            step={1}
            value={creditInput}
            onChange={(e) => setCreditInput(e.target.value)}
            placeholder={`e.g. up to ${comparison.period_units_kwh} kWh`}
          />
          <button
            type="button"
            className="primary"
            onClick={handleApply}
            disabled={recalculating || !creditInput.trim()}
          >
            {recalculating ? "Estimating…" : "Estimate VNM bill"}
          </button>
        </div>
      </section>

      <section className="vnm-summary-facts">
        <div className="vnm-fact">
          <span>Sanctioned load</span>
          <strong>{comparison.sanctioned_load_kw} kW</strong>
        </div>
        <div className="vnm-fact">
          <span>{multiMonth ? "Units (billing period)" : "Units consumed"}</span>
          <strong>
            {comparison.period_units_kwh} kWh
            {multiMonth ? (
              <span className="line-detail">
                {" "}
                (~{comparison.monthly_units} kWh/month avg)
              </span>
            ) : null}
          </strong>
        </div>
        {!needsCredit && (
          <div className="vnm-fact">
            <span>Expected VNM solar credit</span>
            <strong>{comparison.solar_kwh_credited} kWh</strong>
          </div>
        )}
        <div className="vnm-fact">
          <span>Billing period</span>
          <strong>{comparison.billing_period ?? "—"}</strong>
        </div>
        <div className="vnm-fact">
          <span>Current BESCOM bill</span>
          <strong>{formatCurrency(comparison.current_bill_total_inr)}</strong>
        </div>
      </section>

      {comparison.period_consumption_note && (
        <p className="summary-note">{comparison.period_consumption_note}</p>
      )}

      <div className="vnm-assumptions">
        {comparison.assumptions.map((note, i) => (
          <p key={i}>{note}</p>
        ))}
      </div>

      <div className="vnm-bill-grid">
        <BillCard scenario={comparison.current_bill} variant="current" />
        {!needsCredit && (
          <BillCard scenario={comparison.vnm_bill} variant="vnm" />
        )}
      </div>

      {!needsCredit && (
        <section className="vnm-difference-summary">
          <div className="vnm-diff-row">
            <span>Current BESCOM bill</span>
            <strong>{formatCurrency(comparison.current_bill.total)}</strong>
          </div>
          <div className="vnm-diff-row">
            <span>Estimated VNM bill</span>
            <strong>{formatCurrency(comparison.vnm_bill.total)}</strong>
          </div>
          <div
            className={`vnm-diff-row total ${comparison.is_vnm_cheaper ? "save" : "increase"}`}
          >
            <span>{comparison.is_vnm_cheaper ? savingLabel : increaseLabel}</span>
            <strong>
              {comparison.is_vnm_cheaper
                ? formatCurrency(savingAmount)
                : formatCurrency(increaseAmount)}
            </strong>
          </div>
        </section>
      )}

      <p className="disclaimer">{comparison.disclaimer}</p>
    </div>
  );
}

function BillCard({
  scenario,
  variant,
}: {
  scenario: VNMComparison["current_bill"];
  variant: "current" | "vnm";
}) {
  const infoOnlyCodes = new Set([
    "CONSUMPTION",
    "SOLAR_CREDIT",
    "GRID_UNITS",
  ]);

  return (
    <article className={`vnm-bill-card ${variant}`}>
      <header>
        <h4>{scenario.title}</h4>
        {scenario.subtitle && <p>{scenario.subtitle}</p>}
      </header>
      <ul className="vnm-line-items">
        {scenario.lines
          .filter((l) => l.amount !== 0 || infoOnlyCodes.has(l.code))
          .map((line) => (
            <li key={line.code}>
              <span className="label">
                {line.label}
                {line.detail && (
                  <span className="line-detail">{line.detail}</span>
                )}
              </span>
              {!infoOnlyCodes.has(line.code) && (
                <strong>{formatCurrency(line.amount)}</strong>
              )}
            </li>
          ))}
      </ul>
      {scenario.lines.length > 0 && (
        <footer>
          <span>Total</span>
          <strong>{formatCurrency(scenario.total)}</strong>
        </footer>
      )}
      {scenario.notes.length > 0 && (
        <ul className="vnm-notes">
          {scenario.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
    </article>
  );
}
