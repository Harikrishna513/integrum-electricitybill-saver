"use client";

import { FormEvent, useMemo, useState } from "react";
import { apiGet, apiPost, apiUpload } from "@/lib/api";

type Tab = "bills" | "vnm" | "gnm" | "rag" | "agent";

type ExtractLike = {
  analysis_id?: string;
  needs_confirmation?: string[];
  support_gate?: { supported_for_money_engines?: boolean };
  validation?: {
    bill?: Record<string, { value?: string | number | boolean | null }>;
  };
};

export default function HomePage() {
  const [tab, setTab] = useState<Tab>("bills");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<unknown>(null);

  const extract = result as ExtractLike | null;
  const needsConfirm =
    tab === "bills" &&
    !!extract?.analysis_id &&
    Array.isArray(extract.needs_confirmation) &&
    extract.needs_confirmation.length > 0;

  const title = useMemo(() => {
    switch (tab) {
      case "bills":
        return "Upload BESCOM bill";
      case "vnm":
        return "Apartment VNM pre-screen";
      case "gnm":
        return "Same-name GNM pre-screen";
      case "rag":
        return "Search official docs (data/Docs)";
      case "agent":
        return "Ask the agent";
    }
  }, [tab]);

  async function run<T>(fn: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      const data = await fn();
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <p className="hint">Karnataka · BESCOM · Domestic first</p>
      <h1 className="brand">BESCOM Bill Saver</h1>
      <p className="lede">
        Upload bills, confirm weak OCR fields, pre-screen Virtual / Group Net
        Metering against versioned SOP rules, and retrieve wording from official
        docs in <code>data/Docs</code>. Engines calculate money — Gemini only
        explains.
      </p>

      <div className="tabs" role="tablist">
        {(
          [
            ["bills", "Bills"],
            ["vnm", "VNM"],
            ["gnm", "GNM"],
            ["rag", "Official docs"],
            ["agent", "Agent"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className="tab"
            role="tab"
            aria-selected={tab === id}
            onClick={() => {
              setTab(id);
              setResult(null);
              setError(null);
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="panel">
        <h2 style={{ marginTop: 0, fontFamily: "var(--serif)" }}>{title}</h2>

        {tab === "bills" && (
          <>
            <form
              onSubmit={(e: FormEvent<HTMLFormElement>) => {
                e.preventDefault();
                const file = (
                  e.currentTarget.elements.namedItem("bill") as HTMLInputElement
                ).files?.[0];
                if (!file) return;
                void run(() => apiUpload("/bills/extract", file));
              }}
            >
              <label htmlFor="bill">BESCOM bill image / PDF</label>
              <input id="bill" name="bill" type="file" accept="image/*,.pdf" />
              <p className="hint">
                Non-Karnataka bills extract but are gated from money engines via{" "}
                <code>support_gate</code>. Weak fields open a confirm form
                (Milestone 24).
              </p>
              <button className="primary" disabled={busy} type="submit">
                {busy ? "Extracting…" : "Extract & analyze"}
              </button>
            </form>

            {needsConfirm && extract?.analysis_id && (
              <ConfirmFieldsForm
                analysisId={extract.analysis_id}
                fields={extract.needs_confirmation || []}
                bill={extract.validation?.bill}
                busy={busy}
                onSubmit={(body) =>
                  void run(() =>
                    apiPost(`/bills/${extract.analysis_id}/confirm`, body)
                  )
                }
              />
            )}
          </>
        )}

        {tab === "vnm" && (
          <form
            className="grid two"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              const kwp = Number(fd.get("kwp"));
              const share = Number(fd.get("share"));
              const load = Number(fd.get("load"));
              const units = Number(fd.get("units"));
              void run(() =>
                apiPost("/vnm/analyze", {
                  as_of: String(fd.get("as_of")),
                  discom: "BESCOM",
                  tariff_code: "LT-1",
                  plant: {
                    proposed_kwp: kwp,
                    same_discom_area: true,
                    grid_topology_hint: "same_dt",
                  },
                  participants: [
                    {
                      connection_id: "Flat-A",
                      category: "DOMESTIC",
                      sanctioned_load_kw: load,
                      monthly_units: units,
                      procurement_share_percent: share,
                    },
                    {
                      connection_id: "Flat-B",
                      category: "DOMESTIC",
                      sanctioned_load_kw: load,
                      monthly_units: units,
                      procurement_share_percent: 100 - share,
                    },
                  ],
                })
              );
            }}
          >
            <div>
              <label>As of</label>
              <input name="as_of" type="date" defaultValue="2025-08-01" required />
            </div>
            <div>
              <label>Proposed plant (kWp)</label>
              <input name="kwp" type="number" step="0.5" defaultValue={6} min={0} />
            </div>
            <div>
              <label>Each flat sanctioned load (kW)</label>
              <input name="load" type="number" step="0.1" defaultValue={4} min={0} />
            </div>
            <div>
              <label>Each flat monthly units</label>
              <input name="units" type="number" defaultValue={200} min={0} />
            </div>
            <div>
              <label>Flat-A share %</label>
              <input name="share" type="number" defaultValue={50} min={0} max={100} />
            </div>
            <div style={{ alignSelf: "end" }}>
              <button className="primary" disabled={busy} type="submit">
                {busy ? "Analyzing…" : "Run VNM pre-screen"}
              </button>
            </div>
            <p className="hint" style={{ gridColumn: "1 / -1" }}>
              Never an approval — technical feasibility stays with BESCOM SRTPV.
            </p>
          </form>
        )}

        {tab === "gnm" && (
          <form
            className="grid two"
            onSubmit={(e) => {
              e.preventDefault();
              const fd = new FormData(e.currentTarget);
              void run(() =>
                apiPost("/gnm/analyze", {
                  as_of: String(fd.get("as_of")),
                  discom: "BESCOM",
                  tariff_code: "LT-1",
                  plant: {
                    proposed_kwp: Number(fd.get("kwp")),
                    same_discom_area: true,
                    same_consumer_name: true,
                    estimated_monthly_generation_kwh: Number(fd.get("gen")),
                    grid_topology_hint: "same_dt",
                  },
                  installations: [
                    {
                      connection_id: "RR-HOST",
                      category: "DOMESTIC",
                      sanctioned_load_kw: Number(fd.get("host_load")),
                      monthly_units: Number(fd.get("host_units")),
                      priority: 1,
                      is_host: true,
                    },
                    {
                      connection_id: "RR-2",
                      category: "DOMESTIC",
                      sanctioned_load_kw: Number(fd.get("rr2_load")),
                      monthly_units: Number(fd.get("rr2_units")),
                      priority: 2,
                      is_host: false,
                    },
                  ],
                })
              );
            }}
          >
            <div>
              <label>As of</label>
              <input name="as_of" type="date" defaultValue="2025-08-01" required />
            </div>
            <div>
              <label>Plant kWp</label>
              <input name="kwp" type="number" step="0.5" defaultValue={6} />
            </div>
            <div>
              <label>Est. monthly generation kWh</label>
              <input name="gen" type="number" defaultValue={1000} />
            </div>
            <div>
              <label>Host monthly units</label>
              <input name="host_units" type="number" defaultValue={50} />
            </div>
            <div>
              <label>Host load kW</label>
              <input name="host_load" type="number" defaultValue={5} />
            </div>
            <div>
              <label>RR-2 monthly units</label>
              <input name="rr2_units" type="number" defaultValue={200} />
            </div>
            <div>
              <label>RR-2 load kW</label>
              <input name="rr2_load" type="number" defaultValue={3} />
            </div>
            <div style={{ alignSelf: "end" }}>
              <button className="primary" disabled={busy} type="submit">
                {busy ? "Analyzing…" : "Run GNM pre-screen"}
              </button>
            </div>
          </form>
        )}

        {tab === "rag" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const q = (
                e.currentTarget.elements.namedItem("q") as HTMLInputElement
              ).value;
              void run(() => apiPost("/rag/search", { query: q, top_k: 5 }));
            }}
          >
            <label htmlFor="q">Ask a policy question</label>
            <input
              id="q"
              name="q"
              placeholder="What is the VNM minimum plant size?"
              defaultValue="VNM minimum plant size and 75% surplus tariff"
              required
            />
            <button className="primary" disabled={busy} type="submit">
              {busy ? "Searching…" : "Search data/Docs"}
            </button>
            <p className="hint">
              Indexed sources:{" "}
              <button
                type="button"
                className="tab"
                onClick={() => void run(() => apiGet("/rag/sources"))}
              >
                List sources
              </button>
            </p>
          </form>
        )}

        {tab === "agent" && (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const question = (
                e.currentTarget.elements.namedItem("question") as HTMLInputElement
              ).value;
              void run(() =>
                apiPost("/agent/ask", {
                  question,
                  mode: "rules",
                  session_id: "frontend-demo",
                })
              );
            }}
          >
            <label htmlFor="question">Question</label>
            <textarea
              id="question"
              name="question"
              rows={3}
              defaultValue="What is the latest VNM rule for minimum plant size?"
              required
            />
            <button className="primary" disabled={busy} type="submit">
              {busy ? "Thinking…" : "Ask (rules mode)"}
            </button>
          </form>
        )}

        {error && (
          <p className="badge bad" style={{ marginTop: "1rem" }}>
            {error}
          </p>
        )}

        {!!result && (
          <div style={{ marginTop: "1rem" }}>
            <StatusBadges data={result} />
            <pre>{JSON.stringify(result, null, 2)}</pre>
          </div>
        )}
      </section>
    </main>
  );
}

function ConfirmFieldsForm({
  analysisId,
  fields,
  bill,
  busy,
  onSubmit,
}: {
  analysisId: string;
  fields: string[];
  bill?: Record<string, { value?: string | number | boolean | null }>;
  busy: boolean;
  onSubmit: (body: {
    corrections: Record<string, string | number>;
    confirm_category: "DOMESTIC";
    accept_extracted_as_printed: string[];
    note?: string;
  }) => void;
}) {
  const editable = fields.filter((f) => f !== "consumer_category");

  return (
    <form
      className="confirm-box"
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        const corrections: Record<string, string | number> = {};
        const accept: string[] = [];

        for (const name of editable) {
          const raw = String(fd.get(name) ?? "").trim();
          const prior = bill?.[name]?.value;
          if (!raw) continue;
          const asNum = Number(raw);
          const value =
            prior !== undefined &&
            prior !== null &&
            typeof prior !== "string" &&
            !Number.isNaN(asNum) &&
            String(prior) === raw
              ? prior
              : Number.isFinite(asNum) &&
                  raw !== "" &&
                  /^-?\d+(\.\d+)?$/.test(raw)
                ? asNum
                : raw;

          if (
            prior !== undefined &&
            prior !== null &&
            String(prior) === String(value)
          ) {
            accept.push(name);
          } else {
            corrections[name] = value as string | number;
          }
        }

        onSubmit({
          corrections,
          confirm_category: "DOMESTIC",
          accept_extracted_as_printed: accept,
          note: String(fd.get("note") || "") || undefined,
        });
      }}
    >
      <h3 style={{ fontFamily: "var(--serif)", margin: "1.25rem 0 0.35rem" }}>
        Confirm weak fields
      </h3>
      <p className="hint">
        Analysis <code>{analysisId}</code>. Correct values from the printed
        bill, or leave them unchanged to accept as printed. Category will be
        attested as DOMESTIC.
      </p>
      <div className="grid two">
        {editable.map((name) => (
          <div key={name}>
            <label htmlFor={`c-${name}`}>{name}</label>
            <input
              id={`c-${name}`}
              name={name}
              defaultValue={
                bill?.[name]?.value !== undefined && bill?.[name]?.value !== null
                  ? String(bill[name].value)
                  : ""
              }
              placeholder="Enter value from printed bill"
            />
          </div>
        ))}
      </div>
      <label htmlFor="note">Optional note</label>
      <input id="note" name="note" placeholder="Verified against printed bill" />
      <button className="primary" disabled={busy} type="submit">
        {busy ? "Saving…" : "Confirm & re-validate"}
      </button>
    </form>
  );
}

function StatusBadges({ data }: { data: unknown }) {
  if (!data || typeof data !== "object") return null;
  const obj = data as Record<string, unknown>;
  const gate = obj.support_gate as Record<string, unknown> | undefined;
  const nested = (obj.result as Record<string, unknown> | undefined) || obj;
  const status = nested.status as string | undefined;
  const needs = obj.needs_confirmation as string[] | undefined;

  return (
    <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.75rem" }}>
      {status && (
        <span
          className={`badge ${
            status.includes("UNSUITABLE") || status.includes("INSUFFICIENT")
              ? "warn"
              : "ok"
          }`}
        >
          {status}
        </span>
      )}
      {gate && (
        <span
          className={`badge ${
            gate.supported_for_money_engines ? "ok" : "bad"
          }`}
        >
          money engines:{" "}
          {gate.supported_for_money_engines ? "allowed" : "gated"}
        </span>
      )}
      {needs && needs.length > 0 && (
        <span className="badge warn">needs confirm: {needs.join(", ")}</span>
      )}
    </div>
  );
}
