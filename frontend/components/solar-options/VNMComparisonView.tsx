"use client";

import { useEffect, useState, type CSSProperties } from "react";
import {
  Activity,
  Building2,
  CalendarDays,
  ClipboardList,
  Droplets,
  FileText,
  Gauge,
  IndianRupee,
  Lightbulb,
  PiggyBank,
  RefreshCw,
  Settings2,
  Sun,
  TrendingUp,
  Wallet,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { formatCurrency } from "@/lib/bill-analysis";
import type { BillLineItem, VNMComparison } from "@/lib/solar-options";

type Props = {
  comparison: VNMComparison;
  onPlantChange?: (plantKwp: number) => void;
  onApplyQuote?: (creditKwh: number) => void;
  recalculating?: boolean;
};

type ScanRow = {
  key: string;
  centerLabel: string;
  centerHint?: string;
  icon: LucideIcon;
  section?: "use" | "energy" | "solar" | "taxes" | "surplus" | "total";
  leftValue: string;
  leftDetail: string | null;
  rightValue: string;
  rightDetail: string | null;
  emphasize?: "left" | "right" | "both" | "none";
};

export function VNMComparisonView({
  comparison,
  onPlantChange,
  onApplyQuote,
  recalculating = false,
}: Props) {
  const kwhPerKwp = comparison.monthly_kwh_per_kwp || 120;
  const minKwp = comparison.plant_slider_min_kwp || 0.5;
  const maxKwp = comparison.plant_slider_max_kwp || 10;
  const stepKwp = comparison.plant_slider_step_kwp || 0.5;

  const [plantKwp, setPlantKwp] = useState(
    comparison.illustrative_plant_kwp || comparison.default_plant_kwp || 1
  );
  const [showAdvanced, setShowAdvanced] = useState(
    comparison.coverage_source === "provider_quote"
  );
  const [showMethod, setShowMethod] = useState(false);
  const [quoteInput, setQuoteInput] = useState(
    comparison.expected_vnm_solar_credit_kwh?.toString() ?? ""
  );
  const [lastQuoteEntered, setLastQuoteEntered] = useState<number | null>(
    comparison.coverage_source === "provider_quote"
      ? comparison.expected_vnm_solar_credit_kwh
      : null
  );

  useEffect(() => {
    setPlantKwp(
      comparison.illustrative_plant_kwp || comparison.default_plant_kwp || 1
    );
  }, [comparison.illustrative_plant_kwp, comparison.default_plant_kwp]);

  useEffect(() => {
    if (comparison.coverage_source === "provider_quote") {
      setShowAdvanced(true);
      if (comparison.expected_vnm_solar_credit_kwh != null) {
        setQuoteInput(String(comparison.expected_vnm_solar_credit_kwh));
      }
    }
  }, [comparison.coverage_source, comparison.expected_vnm_solar_credit_kwh]);

  const usingQuote = comparison.coverage_source === "provider_quote";
  const maxQuote = comparison.period_units_kwh;
  const quoteNumber = Number(quoteInput);
  const quoteOverMax =
    Number.isFinite(quoteNumber) && quoteNumber > maxQuote && maxQuote > 0;

  const cheaper = comparison.is_vnm_cheaper;
  const monthlyAmount = cheaper
    ? comparison.monthly_saving_inr
    : comparison.monthly_increase_inr;
  const annualAmount = cheaper
    ? comparison.annual_saving_inr
    : comparison.annual_increase_inr;

  const previewUnits = Math.round(plantKwp * kwhPerKwp * 100) / 100;
  const previewSurplus = Math.max(
    0,
    Math.round((previewUnits - comparison.monthly_units) * 100) / 100
  );
  const previewOffset = Math.min(comparison.monthly_units, previewUnits);
  const offsetOfBill =
    comparison.monthly_units > 0
      ? Math.min(
          100,
          Math.round((previewOffset / comparison.monthly_units) * 100)
        )
      : 0;

  const chart = comparison.monthly_chart ?? [];
  const maxBill = Math.max(
    1,
    ...chart.flatMap((m) => [
      m.estimated_bescom_bill_inr,
      m.estimated_vnm_bill_inr,
    ])
  );

  const rows = buildScanRows(comparison);
  const ctaUrl = comparison.cta_url || "https://integrumenergy.in/contact/";

  function commitPlant(kwp: number) {
    const clamped = Math.min(maxKwp, Math.max(minKwp, kwp));
    const snapped = Math.round(clamped / stepKwp) * stepKwp;
    const next = Math.round(snapped * 100) / 100;
    setPlantKwp(next);
    onPlantChange?.(next);
  }

  function handleQuote() {
    const value = Number(quoteInput);
    if (!Number.isFinite(value) || value < 0) return;
    setLastQuoteEntered(value);
    onApplyQuote?.(value);
  }

  function clearQuote() {
    setLastQuoteEntered(null);
    setQuoteInput("");
    setShowAdvanced(false);
    onPlantChange?.(
      comparison.default_plant_kwp || comparison.illustrative_plant_kwp || 1
    );
  }

  const leftMeta = [
    `${comparison.monthly_units} kWh/month`,
    `${comparison.sanctioned_load_kw} kW load`,
    comparison.billing_period || null,
  ]
    .filter(Boolean)
    .join(" · ");

  const rightMeta = [
    `${comparison.illustrative_plant_kwp} kWp solar`,
    `~${comparison.estimated_generation_kwh} kWh gen`,
    `${comparison.solar_kwh_credited} kWh used`,
    comparison.surplus_kwh > 0
      ? `${comparison.surplus_kwh} kWh surplus`
      : null,
    comparison.residual_grid_kwh > 0
      ? `${comparison.residual_grid_kwh} kWh from grid`
      : "0 kWh from grid",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <div className="vnm-comparison">
      <section className={`vnm-hero ${cheaper ? "save" : "increase"}`}>
        <div className="vnm-hero-grid">
          <div className="vnm-hero-main">
            <p className="vnm-hero-eyebrow">
              <span className="vnm-hero-eyebrow-mark" aria-hidden />
              Your potential savings
            </p>
            <h3>BESCOM Bill vs VNM</h3>
            <p className="vnm-hero-note">
              Save more every month with Virtual Net Metering
            </p>

            <div className={`vnm-save-card ${cheaper ? "save" : "increase"}`}>
              <div className="vnm-save-card-copy">
                <span>
                  {cheaper
                    ? "Estimated Monthly Saving"
                    : "Estimated Monthly Increase"}
                </span>
                <strong>{formatCurrency(monthlyAmount)}</strong>
                <em>({formatCurrency(annualAmount)} per year)</em>
              </div>
              <div className="vnm-save-card-art" aria-hidden>
                <MoneyBagArt />
              </div>
            </div>

            {comparison.has_gruha_jyothi && comparison.gruha_jyothi_note && (
              <p className="vnm-gj-note" role="status">
                {comparison.gruha_jyothi_note}
              </p>
            )}

            <div className="vnm-cta-row">
              <button
                type="button"
                className="vnm-text-link"
                onClick={() => {
                  setShowMethod(true);
                  document
                    .getElementById("vnm-methodology")
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                }}
              >
                See how we calculated this →
              </button>
              <a
                className="vnm-text-link"
                href={ctaUrl}
                target="_blank"
                rel="noreferrer"
              >
                Talk to an expert →
              </a>
            </div>
          </div>

          <aside className="vnm-quick-summary" aria-label="Quick summary">
            <h4>Quick Summary</h4>
            <ul>
              <li>
                <Zap size={15} strokeWidth={2} aria-hidden />
                <span>Your Load</span>
                <strong>
                  {comparison.illustrative_plant_kwp ||
                    comparison.sanctioned_load_kw}{" "}
                  kW
                </strong>
              </li>
              <li>
                <Droplets size={15} strokeWidth={2} aria-hidden />
                <span>Average Monthly Consumption</span>
                <strong>{comparison.monthly_units} kWh</strong>
              </li>
              <li>
                <Activity size={15} strokeWidth={2} aria-hidden />
                <span>Sanctioned Load</span>
                <strong>{comparison.sanctioned_load_kw} kW</strong>
              </li>
              <li>
                <Lightbulb size={15} strokeWidth={2} aria-hidden />
                <span>Tariff Area</span>
                <strong>BESCOM</strong>
              </li>
              <li>
                <CalendarDays size={15} strokeWidth={2} aria-hidden />
                <span>Period</span>
                <strong>{comparison.billing_period || "—"}</strong>
              </li>
            </ul>
          </aside>
        </div>
      </section>

      <section className={`vnm-plant-explorer ${usingQuote ? "quote-locked" : ""}`}>
        <header className="vnm-plant-explorer-head">
          <h4>Try a plant size</h4>
          <p>
            Your use: {comparison.monthly_units} kWh/month. Bill offset rule:{" "}
            <strong>
              1 kWp ≈ {kwhPerKwp} units/month
            </strong>{" "}
            (illustrative average).
          </p>
        </header>

        <div className="vnm-plant-slider-wrap">
          <input
            id="vnm-plant-slider"
            className="vnm-slider"
            type="range"
            min={minKwp}
            max={maxKwp}
            step={stepKwp}
            value={plantKwp}
            disabled={recalculating || usingQuote}
            style={
              {
                ["--vnm-slider-pct"]: `${
                  ((plantKwp - minKwp) / Math.max(0.001, maxKwp - minKwp)) * 100
                }%`,
              } as CSSProperties
            }
            onChange={(e) => setPlantKwp(Number(e.target.value))}
            onMouseUp={(e) =>
              commitPlant(Number((e.target as HTMLInputElement).value))
            }
            onTouchEnd={(e) =>
              commitPlant(Number((e.target as HTMLInputElement).value))
            }
            onKeyUp={(e) =>
              commitPlant(Number((e.target as HTMLInputElement).value))
            }
            aria-label="Plant size in kWp"
          />
          <div className="vnm-plant-mark-lines" aria-hidden>
            {[1, 2, 3, 5, 10]
              .filter((t) => t >= minKwp && t <= maxKwp)
              .map((tick) => {
                const pct =
                  ((tick - minKwp) / Math.max(0.001, maxKwp - minKwp)) * 100;
                const active = Math.abs(plantKwp - tick) < stepKwp / 2;
                return (
                  <span
                    key={tick}
                    className={`vnm-plant-mark ${active ? "active" : ""}`}
                    style={{ left: `${pct}%` }}
                  />
                );
              })}
          </div>
          <div className="vnm-plant-ticks" aria-hidden>
            {[1, 2, 3, 5, 10]
              .filter((t) => t >= minKwp && t <= maxKwp)
              .map((tick) => {
                const pct =
                  ((tick - minKwp) / Math.max(0.001, maxKwp - minKwp)) * 100;
                const active = Math.abs(plantKwp - tick) < stepKwp / 2;
                return (
                  <button
                    key={tick}
                    type="button"
                    className={`vnm-plant-tick ${active ? "active" : ""}`}
                    style={{ left: `${pct}%` }}
                    disabled={recalculating || usingQuote}
                    onClick={() => commitPlant(tick)}
                  >
                    {tick} kWp
                  </button>
                );
              })}
          </div>
        </div>

        <div className="vnm-plant-cards">
          <article className="vnm-plant-card tone-green">
            <span className="vnm-plant-card-icon" aria-hidden>
              <Zap size={16} strokeWidth={2} />
            </span>
            <p>
              <strong>
                {plantKwp} kWp → ~{previewUnits} units/month
              </strong>
            </p>
          </article>
          <article className="vnm-plant-card tone-blue">
            <span className="vnm-plant-card-icon" aria-hidden>
              <Gauge size={16} strokeWidth={2} />
            </span>
            <p>
              You use: <strong>{comparison.monthly_units} units</strong>
            </p>
          </article>
          <article className="vnm-plant-card tone-orange">
            <span className="vnm-plant-card-icon" aria-hidden>
              <TrendingUp size={16} strokeWidth={2} />
            </span>
            <p>
              You will offset up to:{" "}
              <strong>
                {previewOffset} units (≈ {offsetOfBill}%)
              </strong>
            </p>
          </article>
          <article className="vnm-plant-card tone-amber">
            <span className="vnm-plant-card-icon" aria-hidden>
              <Building2 size={16} strokeWidth={2} />
            </span>
            <p>
              Remainder:{" "}
              <strong>
                ~{Math.max(0, Math.round((comparison.monthly_units - previewOffset) * 100) / 100)}{" "}
                units
              </strong>
              {previewSurplus > 0 ? (
                <>
                  {" "}
                  (Banking: ~{previewSurplus} units)
                </>
              ) : (
                " (no surplus)"
              )}
            </p>
          </article>
        </div>

        {/* <button
          type="button"
          className="linkish vnm-plant-advanced-link"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced
            ? "Hide provider quote"
            : "Suggest a provider quote or calculate exact price"}
        </button> */}

        {showAdvanced && (
          <div className="vnm-credit-input">
            <label htmlFor="vnm-solar-credit">
              Expected solar credit for this billing period (kWh)
            </label>
            <p className="summary-note">
              Enter the kWh from your provider quote for this bill period.
              Maximum usable credit is your bill consumption:{" "}
              <strong>{maxQuote} kWh</strong>
              {comparison.is_multi_month_period
                ? ` (~${comparison.monthly_units} kWh/month avg)`
                : ""}
              .
            </p>
            <div className="vnm-credit-row">
              <input
                id="vnm-solar-credit"
                type="number"
                min={0}
                max={maxQuote}
                step={1}
                value={quoteInput}
                onChange={(e) => setQuoteInput(e.target.value)}
                placeholder={`Up to ${maxQuote}`}
              />
              <button
                type="button"
                className="primary"
                onClick={handleQuote}
                disabled={recalculating || !quoteInput.trim()}
              >
                {recalculating ? "Updating…" : "Apply quote"}
              </button>
              {usingQuote && (
                <button
                  type="button"
                  className="linkish"
                  onClick={clearQuote}
                  disabled={recalculating}
                >
                  Clear quote
                </button>
              )}
            </div>
            {quoteOverMax && (
              <p className="vnm-quote-warn" role="status">
                {quoteNumber} kWh is higher than your bill ({maxQuote} kWh). On
                Apply, it will be capped to <strong>{maxQuote} kWh</strong>.
              </p>
            )}
            {usingQuote && (
              <p className="vnm-quote-applied" role="status">
                <strong>Quote active.</strong> Using{" "}
                {comparison.expected_vnm_solar_credit_kwh ??
                  comparison.solar_kwh_credited}{" "}
                kWh for this period
                {lastQuoteEntered != null && lastQuoteEntered > maxQuote
                  ? ` (you entered ${lastQuoteEntered}; capped at your bill)`
                  : ""}
                . Offset this month:{" "}
                <strong>{comparison.solar_kwh_credited} kWh</strong>
                {comparison.residual_grid_kwh > 0
                  ? ` · still from grid: ${comparison.residual_grid_kwh} kWh`
                  : " · full bill offset"}
                . Plant slider is paused while a quote is active.
              </p>
            )}
            {recalculating && (
              <p className="summary-note" role="status">
                Recalculating comparison…
              </p>
            )}
          </div>
        )}
      </section>

      {comparison.period_consumption_note && (
        <p className="summary-note">{comparison.period_consumption_note}</p>
      )}

      <ScanCompareTable
        leftTitle="My Current BESCOM Bill"
        rightTitle="With VNM Solar — Estimated"
        leftMeta={leftMeta}
        rightMeta={rightMeta}
        rows={rows}
        cheaper={cheaper}
        monthlyAmount={monthlyAmount}
        annualAmount={annualAmount}
      />

      {comparison.surplus_kwh > 0 && (
        <p className="vnm-surplus-banner" role="note">
          <strong>Extra solar (surplus):</strong> Banks month-to-month. Cash /
          financial settlement happens only on a yearly basis under the provider
          proposal — not paid out on this monthly bill.
        </p>
      )}

      {chart.length > 0 && (
        <section className="vnm-chart" aria-label="12-month bill estimate">
          <h4>12-month estimate</h4>
          <p className="summary-note">
            First month matches the comparison totals. Later months use
            illustrative seasonal factors.
          </p>
          <div className="vnm-chart-legend">
            <span className="bescom">Normal BESCOM</span>
            <span className="vnm">VNM estimate</span>
          </div>
          <div className="vnm-chart-bars">
            {chart.map((m) => (
              <div key={m.month_index} className="vnm-chart-month">
                <div className="vnm-chart-pair">
                  <div
                    className="bar bescom"
                    style={{
                      height: `${(m.estimated_bescom_bill_inr / maxBill) * 100}%`,
                    }}
                    title={`BESCOM ${formatCurrency(m.estimated_bescom_bill_inr)}`}
                  />
                  <div
                    className="bar vnm"
                    style={{
                      height: `${(m.estimated_vnm_bill_inr / maxBill) * 100}%`,
                    }}
                    title={`VNM ${formatCurrency(m.estimated_vnm_bill_inr)}`}
                  />
                </div>
                <span>{m.month_label}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="vnm-methodology" id="vnm-methodology">
        <button
          type="button"
          className="linkish"
          onClick={() => setShowMethod((v) => !v)}
        >
          {showMethod
            ? "Hide how we estimated"
            : "How we estimated your savings"}
        </button>
        {showMethod && comparison.methodology && (
          <div className="vnm-method-body">
            <ul>
              {comparison.methodology.steps.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ul>
          </div>
        )}
      </section>

      <p className="disclaimer">{comparison.disclaimer}</p>
      {recalculating && (
        <p className="summary-note" role="status">
          Updating estimate…
        </p>
      )}
    </div>
  );
}

function MoneyBagArt() {
  return (
    <svg
      className="vnm-money-bag"
      viewBox="0 0 72 72"
      width="64"
      height="64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <ellipse cx="36" cy="62" rx="22" ry="5" fill="#ca8a04" opacity="0.55" />
      <circle cx="22" cy="58" r="6" fill="#eab308" />
      <circle cx="36" cy="60" r="7" fill="#facc15" />
      <circle cx="50" cy="58" r="6" fill="#eab308" />
      <path
        d="M28 18c0-4 3.5-7 8-7s8 3 8 7c0 2-1 3.5-2.5 4.5L46 28H26l4.5-5.5C29 21.5 28 20 28 18Z"
        fill="#16a34a"
      />
      <path
        d="M24 30c0-2 2-4 4-4h16c2 0 4 2 4 4v18c0 8-6 14-12 14s-12-6-12-14V30Z"
        fill="#22c55e"
      />
      <path
        d="M28 30h16v4c0 1.5-1.2 2.5-2.5 2.5h-11C29.2 36.5 28 35.5 28 34v-4Z"
        fill="#15803d"
      />
      <text
        x="36"
        y="52"
        textAnchor="middle"
        fill="#fff"
        fontSize="16"
        fontWeight="700"
        fontFamily="system-ui,sans-serif"
      >
        ₹
      </text>
    </svg>
  );
}

function ScanCompareTable({
  leftTitle,
  rightTitle,
  leftMeta,
  rightMeta,
  rows,
  cheaper,
  monthlyAmount,
  annualAmount,
}: {
  leftTitle: string;
  rightTitle: string;
  leftMeta: string;
  rightMeta: string;
  rows: ScanRow[];
  cheaper: boolean;
  monthlyAmount: number;
  annualAmount: number;
}) {
  return (
    <div className="vnm-scan" aria-label="Bill comparison">
      <div className="vnm-scan-head">
        <div className="vnm-scan-side left">
          <p className="vnm-scan-kicker">Today</p>
          <h4>{leftTitle}</h4>
          <p>{leftMeta}</p>
        </div>
        <div className="vnm-scan-mid-head" aria-hidden="true">
          vs
        </div>
        <div className="vnm-scan-side right">
          <p className="vnm-scan-kicker">With VNM</p>
          <h4>{rightTitle}</h4>
          <p>{rightMeta}</p>
        </div>
      </div>

      {rows.map((row) => {
        const Icon = row.icon;
        return (
          <div
            key={row.key}
            className={`vnm-scan-row ${row.section ?? ""} ${row.key === "TOTAL" ? "total" : ""}`}
          >
            <div
              className={`vnm-scan-cell left ${row.emphasize === "left" || row.emphasize === "both" ? "hot" : ""}`}
            >
              <strong>{row.leftValue}</strong>
              {row.leftDetail && <span>{row.leftDetail}</span>}
            </div>
            <div className="vnm-scan-center">
              <span className="vnm-scan-icon" aria-hidden>
                <Icon size={18} strokeWidth={1.75} />
              </span>
              <strong>{row.centerLabel}</strong>
              {row.centerHint && <span>{row.centerHint}</span>}
            </div>
            <div
              className={`vnm-scan-cell right ${row.emphasize === "right" || row.emphasize === "both" ? "hot" : ""}`}
            >
              <strong>{row.rightValue}</strong>
              {row.rightDetail && <span>{row.rightDetail}</span>}
            </div>
          </div>
        );
      })}

      <div className={`vnm-save-strip ${cheaper ? "save" : "increase"}`}>
        <div className="vnm-save-piggy" aria-hidden>
          <PiggyBank size={36} strokeWidth={1.6} />
        </div>
        <div className="vnm-save-metric">
          <span>{cheaper ? "You Save" : "Extra cost"}</span>
          <strong>{formatCurrency(monthlyAmount)}</strong>
          <span>every month</span>
        </div>
        <div className="vnm-save-metric">
          <span>That&apos;s</span>
          <strong>{formatCurrency(annualAmount)}</strong>
          <span>every year</span>
        </div>
        <p className="vnm-save-strip-note">
          Savings may vary with actual use, solar generation, and BESCOM tariff
          changes.
        </p>
      </div>
    </div>
  );
}

function buildScanRows(comparison: VNMComparison): ScanRow[] {
  const current = comparison.current_bill;
  const vnm = comparison.vnm_bill;
  const left = indexLines(current.lines);
  const right = indexLines(vnm.lines);

  const units = `${formatKwh(comparison.monthly_units)} kWh`;
  const fixedL = left.get("FIXED");
  const fixedR = right.get("BESCOM_FIXED");
  const energyL = left.get("ENERGY");
  const gridEnergy = right.get("BESCOM_ENERGY");
  const vnmService = right.get("INTEGRUM_SUB");
  const gen = right.get("SOLAR_GEN");
  const surplus = right.get("SURPLUS");
  const fppcaL = left.get("FPPCA");
  const fppcaR = right.get("BESCOM_FPPCA");
  const otherL = left.get("OTHER");
  const otherR = right.get("BESCOM_OTHER");
  const taxL = left.get("TAX");
  const taxR = right.get("BESCOM_TAX");

  const rows: ScanRow[] = [
    {
      key: "CONSUMPTION",
      section: "use",
      icon: Gauge,
      centerLabel: "Your electricity use",
      leftValue: units,
      leftDetail: "From your bill",
      rightValue: units,
      rightDetail: "Same monthly use",
      emphasize: "none",
    },
    {
      key: "FIXED",
      section: "use",
      icon: IndianRupee,
      centerLabel: "Fixed charges",
      centerHint: "Connection / load charge",
      leftValue: moneyOrDash(fixedL?.amount ?? null),
      leftDetail: fixedL?.detail ?? `${comparison.sanctioned_load_kw} kW load`,
      rightValue: moneyOrDash(fixedR?.amount ?? fixedL?.amount ?? null),
      rightDetail: "Same as your bill",
      emphasize: "none",
    },
    {
      key: "ENERGY",
      section: "energy",
      icon: Zap,
      centerLabel: "Energy from the grid",
      centerHint:
        comparison.residual_grid_kwh > 0
          ? "Only leftover units after solar"
          : "Fully covered by solar this month",
      leftValue: moneyOrDash(energyL?.amount ?? null),
      leftDetail: energyL?.detail ?? null,
      rightValue:
        gridEnergy && gridEnergy.amount > 0
          ? formatCurrency(gridEnergy.amount)
          : formatCurrency(0),
      rightDetail:
        gridEnergy && gridEnergy.amount > 0
          ? gridEnergy.detail
          : "No grid energy needed",
      emphasize:
        energyL && (!gridEnergy || gridEnergy.amount === 0) ? "left" : "none",
    },
    {
      key: "VNM_SERVICE",
      section: "energy",
      icon: RefreshCw,
      centerLabel: "Solar service charge",
      centerHint: "What you pay for VNM solar units",
      leftValue: formatCurrency(0),
      leftDetail: "No VNM on current bill",
      rightValue: moneyOrDash(vnmService?.amount ?? null),
      rightDetail: vnmService?.detail ?? null,
      emphasize: "right",
    },
    {
      key: "SOLAR_GEN",
      section: "solar",
      icon: Sun,
      centerLabel: "Solar units generated",
      centerHint: "Illustrative from plant size",
      leftValue: "—",
      leftDetail: "Not on BESCOM bill",
      rightValue: gen
        ? `${formatKwh(comparison.estimated_generation_kwh)} kWh`
        : "—",
      rightDetail: gen?.detail ?? "Plant size × units per kWp",
      emphasize: "none",
    },
    {
      key: "FPPCA",
      section: "taxes",
      icon: ClipboardList,
      centerLabel: "FPPCA",
      centerHint: "Fuel / power cost adjustment",
      leftValue: moneyOrDash(fppcaL?.amount ?? null),
      leftDetail: fppcaL?.detail ?? null,
      rightValue: moneyOrDash(
        fppcaR && fppcaR.amount > 0 ? fppcaR.amount : fppcaL ? 0 : null
      ),
      rightDetail:
        fppcaR && fppcaR.amount > 0
          ? fppcaR.detail
          : fppcaL
            ? "None on residual grid"
            : null,
      emphasize: "none",
    },
    {
      key: "OTHER",
      section: "taxes",
      icon: Settings2,
      centerLabel: "Other BESCOM charges",
      centerHint: "P and G / miscellaneous",
      leftValue: moneyOrDash(otherL?.amount ?? null),
      leftDetail: otherL?.detail ?? null,
      rightValue: moneyOrDash(
        otherR && otherR.amount > 0 ? otherR.amount : otherL ? 0 : null
      ),
      rightDetail:
        otherR && otherR.amount > 0
          ? otherR.detail
          : otherL
            ? "None on residual grid"
            : null,
      emphasize: "none",
    },
    {
      key: "TAX",
      section: "taxes",
      icon: FileText,
      centerLabel: "Electricity tax",
      leftValue: moneyOrDash(taxL?.amount ?? null),
      leftDetail: taxL?.detail ?? null,
      rightValue: moneyOrDash(taxR?.amount ?? null),
      rightDetail: taxR?.detail ?? null,
      emphasize: "none",
    },
    {
      key: "SURPLUS",
      section: "surplus",
      icon: TrendingUp,
      centerLabel: "Extra solar (surplus)",
      centerHint: "Banks monthly · settles yearly",
      leftValue: "—",
      leftDetail: "Not applicable today",
      rightValue:
        comparison.surplus_kwh > 0
          ? `${formatKwh(comparison.surplus_kwh)} kWh`
          : "None",
      rightDetail:
        comparison.surplus_kwh > 0
          ? surplus?.detail ??
            "Carried forward each month; yearly financial settlement only"
          : "Generation within your use",
      emphasize: comparison.surplus_kwh > 0 ? "right" : "none",
    },
    {
      key: "TOTAL",
      section: "total",
      icon: Wallet,
      centerLabel: "Total monthly bill",
      leftValue: formatCurrency(current.total),
      leftDetail: null,
      rightValue: formatCurrency(vnm.total),
      rightDetail: null,
      emphasize: "both",
    },
  ];

  return rows.filter((r) => {
    if (r.key === "FPPCA" && !fppcaL && !fppcaR) return false;
    if (r.key === "OTHER" && !otherL && !otherR) return false;
    if (r.key === "TAX" && !taxL && !taxR) return false;
    return true;
  });
}

function indexLines(lines: BillLineItem[]): Map<string, BillLineItem> {
  const map = new Map<string, BillLineItem>();
  for (const line of lines) map.set(line.code, line);
  return map;
}

function moneyOrDash(amount: number | null | undefined): string {
  if (amount == null) return "—";
  return formatCurrency(amount);
}

function formatKwh(units: number): string {
  return Number.isInteger(units) ? String(units) : String(units);
}
