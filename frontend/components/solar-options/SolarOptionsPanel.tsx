"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { formatCurrency } from "@/lib/bill-analysis";
import type { CompareSolarOptionsPayload, SolarOptionsComparison, SolarOptionsResponse, } from "@/lib/solar-options";
import { SolarIntelligenceReportView } from "@/components/solar-options/SolarIntelligenceReport";
import { VNMComparisonView } from "@/components/solar-options/VNMComparisonView";

type Props = {
  analysisId: string;
  enabled?: boolean;
};

export function SolarOptionsPanel({ analysisId, enabled = true }: Props) {
  const [loading, setLoading] = useState(true);
  const [recalculating, setRecalculating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<SolarOptionsComparison | null>(
    null
  );

  const loadComparison = useCallback(
    async (opts?: {
      plantKwp?: number;
      expectedCredit?: number;
    }) => {
      const isInitial = opts === undefined;
      if (isInitial) {
        setLoading(true);
      } else {
        setRecalculating(true);
      }
      setError(null);
      const payload: CompareSolarOptionsPayload = {
        include_vnm: true,
        include_individual_solar: false,
        include_gnm: false,
        ...(opts?.plantKwp !== undefined
          ? { illustrative_plant_kwp: opts.plantKwp }
          : {}),
        ...(opts?.expectedCredit !== undefined
          ? { expected_vnm_solar_credit_kwh: opts.expectedCredit }
          : {}),
      };
      try {
        const res = await apiPost<SolarOptionsResponse>(
          `/bills/${analysisId}/solar-options`,
          payload
        );
        setComparison(res.comparison);
      } catch (e) {
        if (isInitial) {
          try {
            const prefill = await apiGet<SolarOptionsResponse>(
              `/bills/${analysisId}/solar-options/prefill`
            );
            setComparison(prefill.comparison);
          } catch {
            // keep original error
          }
        }
        setError(
          e instanceof Error ? e.message : "Could not load VNM comparison."
        );
      } finally {
        if (isInitial) {
          setLoading(false);
        } else {
          setRecalculating(false);
        }
      }
    },
    [analysisId]
  );

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setError(null);
      return;
    }
    void loadComparison();
  }, [enabled, loadComparison]);

  if (!enabled) {
    return (
      <section className="solar-options-panel">
        <h2>VNM bill comparison</h2>
        <p>Confirm the selected bill above to compare with VNM.</p>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="solar-options-panel">
        <h2>VNM bill comparison</h2>
        <p>Loading your confirmed bill for VNM comparison…</p>
      </section>
    );
  }

  if (!comparison) {
    return (
      <section className="solar-options-panel">
        <h2>VNM bill comparison</h2>
        {error && <div className="alert bad">{error}</div>}
      </section>
    );
  }

  const prefill = comparison.prefill;
  const vnmOption = comparison.options.find((o) => o.option === "vnm");
  const unitsLabel = prefill.is_multi_month_period
    ? `${prefill.period_units_kwh} kWh for billing period (~${prefill.monthly_units} kWh/month avg)`
    : `${prefill.period_units_kwh} kWh`;

  return (
    <section className="solar-options-panel">
      <div className="solar-options-header">
        <h2>VNM bill comparison</h2>
        <p>
          Based on your confirmed bill ({unitsLabel},{" "}
          {prefill.sanctioned_load_kw} kW,{" "}
          {formatCurrency(prefill.current_monthly_bill_inr)}). Illustrative
          Integrum VNM estimate — not an actual allocation.
        </p>
      </div>

      {error && (
        <div className="alert bad" role="alert">
          {error}
        </div>
      )}

      {comparison.vnm_comparison && (
        <VNMComparisonView
          comparison={comparison.vnm_comparison}
          recalculating={recalculating}
          onPlantChange={(plantKwp) =>
            void loadComparison({ plantKwp })
          }
          onApplyQuote={(credit) =>
            void loadComparison({ expectedCredit: credit })
          }
        />
      )}

      {vnmOption?.intelligence_report && (
        <details className="solar-intelligence-block">
          <summary>How we estimated your savings</summary>
          <SolarIntelligenceReportView
            report={vnmOption.intelligence_report}
            highlighted
          />
        </details>
      )}

      {comparison.disclaimer && (
        <p className="disclaimer">{comparison.disclaimer}</p>
      )}
    </section>
  );
}
