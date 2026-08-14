"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { apiGet, apiPost } from "@/lib/api";
import { formatCurrency, formatUnits } from "@/lib/bill-analysis";
import type {
  CompareSolarOptionsPayload,
  GNMInstallationInput,
  SolarOptionsComparison,
  SolarOptionsResponse,
  VNMParticipantInput,
} from "@/lib/solar-options";
import { OPTION_LABELS, statusClass } from "@/lib/solar-options";

type Props = {
  analysisId: string;
};

export function SolarOptionsPanel({ analysisId }: Props) {
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [comparison, setComparison] = useState<SolarOptionsComparison | null>(null);
  const [plantKwp, setPlantKwp] = useState("");
  const [roofArea, setRoofArea] = useState("");
  const [vnmExtras, setVnmExtras] = useState<VNMParticipantInput[]>([]);
  const [gnmExtras, setGnmExtras] = useState<GNMInstallationInput[]>([]);

  const loadPrefill = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiGet<SolarOptionsResponse>(
        `/bills/${analysisId}/solar-options/prefill`
      );
      setComparison(res.comparison);
      setPlantKwp(String(res.comparison.prefill.suggested_plant_kwp ?? 5));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load solar options.");
    } finally {
      setLoading(false);
    }
  }, [analysisId]);

  useEffect(() => {
    void loadPrefill();
  }, [loadPrefill]);

  async function runComparison(e?: FormEvent) {
    e?.preventDefault();
    setBusy(true);
    setError(null);
    const payload: CompareSolarOptionsPayload = {
      plant: {
        proposed_kwp: Number(plantKwp) || undefined,
        roof_area_m2: roofArea ? Number(roofArea) : undefined,
        same_discom_area: true,
        same_consumer_name: true,
      },
      vnm_participants: vnmExtras.filter((p) => p.connection_id.trim()),
      gnm_installations: gnmExtras.filter((p) => p.connection_id.trim()),
    };
    try {
      const res = await apiPost<SolarOptionsResponse>(
        `/bills/${analysisId}/solar-options`,
        payload
      );
      setComparison(res.comparison);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Comparison failed.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <section className="solar-options-panel">
        <h2>Compare solar options</h2>
        <p>Loading options from your confirmed bill…</p>
      </section>
    );
  }

  if (!comparison) {
    return (
      <section className="solar-options-panel">
        <h2>Compare solar options</h2>
        {error && <div className="alert bad">{error}</div>}
      </section>
    );
  }

  const prefill = comparison.prefill;

  return (
    <section className="solar-options-panel">
      <div className="solar-options-header">
        <h2>Compare solar options</h2>
        <p>
          Based on your confirmed bill ({formatUnits(prefill.monthly_units)},{" "}
          {formatCurrency(prefill.current_monthly_bill_inr)}). Compare individual
          rooftop solar, VNM (apartment/community), and GNM (same-name multi-RR).
        </p>
      </div>

      {error && <div className="alert bad" role="alert">{error}</div>}

      <form className="solar-options-form" onSubmit={runComparison}>
        <div className="field-grid">
          <label className="field">
            <span>Proposed plant size (kWp)</span>
            <input
              type="number"
              min={1}
              step={0.5}
              value={plantKwp}
              onChange={(e) => setPlantKwp(e.target.value)}
            />
          </label>
          <label className="field">
            <span>Roof area (m²) — for individual rooftop</span>
            <input
              type="number"
              min={0}
              placeholder="Optional"
              value={roofArea}
              onChange={(e) => setRoofArea(e.target.value)}
            />
          </label>
        </div>

        <ParticipantBlock
          title="VNM — add other flats / participants"
          hint="VNM needs at least 2 participants with procurement shares totalling 100%."
          rows={vnmExtras}
          onAdd={() =>
            setVnmExtras((rows) => [
              ...rows,
              { connection_id: "", procurement_share_percent: 25 },
            ])
          }
          onChange={setVnmExtras}
          renderRow={(row, i, onRowChange) => (
            <>
              <input
                placeholder="Flat / RR label"
                value={row.connection_id}
                onChange={(e) =>
                  onRowChange(i, { ...row, connection_id: e.target.value })
                }
              />
              <input
                type="number"
                placeholder="Share %"
                value={row.procurement_share_percent ?? ""}
                onChange={(e) =>
                  onRowChange(i, {
                    ...row,
                    procurement_share_percent: Number(e.target.value),
                  })
                }
              />
            </>
          )}
        />

        <ParticipantBlock
          title="GNM — add other RR numbers (same consumer name)"
          hint="GNM needs at least 2 installations; one must be the host."
          rows={gnmExtras}
          onAdd={() =>
            setGnmExtras((rows) => [
              ...rows,
              { connection_id: "", priority: rows.length + 2, is_host: false },
            ])
          }
          onChange={setGnmExtras}
          renderRow={(row, i, onRowChange) => (
            <>
              <input
                placeholder="RR number"
                value={row.connection_id}
                onChange={(e) =>
                  onRowChange(i, { ...row, connection_id: e.target.value })
                }
              />
              <input
                type="number"
                placeholder="Priority"
                value={row.priority ?? ""}
                onChange={(e) =>
                  onRowChange(i, { ...row, priority: Number(e.target.value) })
                }
              />
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={!!row.is_host}
                  onChange={(e) =>
                    onRowChange(i, { ...row, is_host: e.target.checked })
                  }
                />
                Host
              </label>
            </>
          )}
        />

        <button type="submit" className="cta" disabled={busy}>
          {busy ? "Comparing…" : "Compare options"}
        </button>
      </form>

      {comparison.options.length > 0 && (
        <div className="solar-results">
          <p className="comparison-message">{comparison.message}</p>
          <div className="option-cards">
            {comparison.options.map((opt) => (
              <article
                key={opt.option}
                className={`option-card ${statusClass(opt.status)} ${
                  comparison.best_option === opt.option ? "best" : ""
                }`}
              >
                <header>
                  <h3>{OPTION_LABELS[opt.option]}</h3>
                  {comparison.best_option === opt.option && (
                    <span className="best-badge">Highest saving</span>
                  )}
                  <span className={`pill ${statusClass(opt.status)}`}>
                    {opt.status.replace(/_/g, " ").toLowerCase()}
                  </span>
                </header>
                <div className="option-metrics">
                  <div>
                    <span>Est. monthly saving</span>
                    <strong>{formatCurrency(opt.monthly_saving_inr)}</strong>
                  </div>
                  {opt.plant_kwp != null && (
                    <div>
                      <span>Plant size</span>
                      <strong>{opt.plant_kwp} kWp</strong>
                    </div>
                  )}
                </div>
                <p>{opt.message}</p>
                {opt.missing_inputs.length > 0 && (
                  <p className="missing-hint">
                    Needs: {opt.missing_inputs.join(", ")}
                  </p>
                )}
                {opt.official_next_step && (
                  <p className="next-step">{opt.official_next_step}</p>
                )}
              </article>
            ))}
          </div>
          <p className="disclaimer">{comparison.disclaimer}</p>
        </div>
      )}
    </section>
  );
}

function ParticipantBlock<T>({
  title,
  hint,
  rows,
  onAdd,
  onChange,
  renderRow,
}: {
  title: string;
  hint: string;
  rows: T[];
  onAdd: () => void;
  onChange: (rows: T[]) => void;
  renderRow: (
    row: T,
    index: number,
    onRowChange: (index: number, row: T) => void
  ) => React.ReactNode;
}) {
  function onRowChange(index: number, row: T) {
    const next = [...rows];
    next[index] = row;
    onChange(next);
  }

  return (
    <div className="participant-block">
      <h3>{title}</h3>
      <p className="hint">{hint}</p>
      {rows.map((row, i) => (
        <div key={i} className="participant-row">
          {renderRow(row, i, onRowChange)}
        </div>
      ))}
      <button type="button" className="ghost" onClick={onAdd}>
        + Add connection
      </button>
    </div>
  );
}
