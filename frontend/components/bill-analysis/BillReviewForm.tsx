"use client";

import { FormEvent, useMemo, useState } from "react";
import type { BillAnalysis, BillField } from "@/lib/bill-analysis";
import { maskAccount } from "@/lib/bill-analysis";

type Props = {
  analysis: BillAnalysis;
  busy?: boolean;
  editing?: boolean;
  onConfirm: (payload: {
    corrections: Record<string, string | number | boolean>;
    confirm_category: "DOMESTIC";
    accept_extracted_as_printed: string[];
  }) => Promise<void>;
};

export function BillReviewForm({ analysis, busy, editing, onConfirm }: Props) {
  const [showMeta, setShowMeta] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const initial = useMemo(() => buildInitialValues(analysis), [analysis]);

  function handleSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setFormError(null);
    const fd = new FormData(e.currentTarget);
    const corrections: Record<string, string | number | boolean> = {};
    const accept: string[] = [];
    const missing: string[] = [];

    for (const section of analysis.sections) {
      for (const field of section.fields) {
        if (!field.editable) continue;

        if (field.name === "account_id") {
          const real = String(
            fd.get("account_id_real") ?? fd.get("account_id") ?? field.value ?? ""
          ).trim();
          if (!real && field.required) missing.push(field.label);
          if (real) {
            if (
              field.value != null &&
              field.value !== "" &&
              String(field.value) === real
            ) {
              accept.push(field.name);
            } else {
              corrections[field.name] = real;
            }
          }
          continue;
        }

        const raw = String(fd.get(field.name) ?? "").trim();
        const prior = field.value;

        // Optional — domestic category is attested via confirm_category, not this field.
        if (field.name === "consumer_category") {
          if (raw) corrections[field.name] = raw;
          continue;
        }

        if (field.required && !raw && (prior === null || prior === undefined || prior === "")) {
          missing.push(field.label);
          continue;
        }

        if (!raw && (prior === null || prior === undefined || prior === "")) continue;

        if (field.name === "is_bescom_bill") {
          const boolVal = raw === "true";
          if (prior !== boolVal) corrections[field.name] = boolVal;
          else accept.push(field.name);
          continue;
        }

        const normalizedRaw = raw.replace(/^[₹Rs.\s]+/i, "").replace(/,/g, "");
        const num = Number(normalizedRaw);
        const priorNum =
          typeof prior === "number"
            ? prior
            : typeof prior === "string"
              ? Number(String(prior).replace(/^[₹Rs.\s]+/i, "").replace(/,/g, ""))
              : NaN;
        const isNum = !Number.isNaN(num) && /^-?[\d.]+$/.test(normalizedRaw);
        const value = isNum ? num : raw;
        const priorComparable =
          !Number.isNaN(priorNum) && isNum ? priorNum : prior;

        // Not on bill — user entry is a correction, not accept-as-printed.
        if (field.level === "MISSING" && raw) {
          corrections[field.name] = value;
          continue;
        }

        if (
          priorComparable !== null &&
          priorComparable !== undefined &&
          String(priorComparable) === String(value)
        ) {
          accept.push(field.name);
        } else if (raw) {
          corrections[field.name] = value;
        }
      }
    }

    if (missing.length) {
      setFormError(
        `Please fill all required fields before continuing: ${missing.join(", ")}.`
      );
      return;
    }

    void onConfirm({
      corrections,
      confirm_category: "DOMESTIC",
      accept_extracted_as_printed: accept,
    });
  }

  return (
    <form className="review-form" onSubmit={handleSubmit}>
      <div className="review-header">
        <h2>{editing ? "Edit bill details" : "Review your bill"}</h2>
        <p>
          {editing
            ? "Update any extracted value that does not match your printed bill — especially Net Payable / Total Amount on Gruha Jyothi bills."
            : "We extracted the following information. Please verify required fields (marked with * ) before continuing."}
        </p>
        <button
          type="button"
          className="ghost"
          onClick={() => setShowMeta((v) => !v)}
        >
          {showMeta ? "Hide extraction details" : "View extraction details"}
        </button>
      </div>

      {formError && (
        <div className="alert bad" role="alert">
          {formError}
        </div>
      )}

      {analysis.consistency_warnings.map((w, i) => (
        <div key={`consistency-${i}`} className="alert warn" role="alert">
          {w}
        </div>
      ))}

      {analysis.support.block_reasons.map((w, i) => (
        <div key={`block-${i}`} className="alert info" role="status">
          {w}
        </div>
      ))}

      {analysis.sections.map((section) => (
        <section key={section.id} className="field-section">
          <h3>{section.title}</h3>
          <div className="field-grid">
            {section.fields.map((field) => (
              <FieldInput
                key={field.name}
                field={field}
                defaultValue={initial[field.name]}
                showMeta={showMeta}
                mask={field.name === "account_id"}
                realAccountValue={initial.account_id}
                inferredCategory={analysis.support.category}
              />
            ))}
          </div>
        </section>
      ))}

      <button type="submit" className="cta" disabled={busy}>
        {busy ? "Saving…" : editing ? "Save changes" : "Confirm & continue"}
      </button>
    </form>
  );
}

function FieldInput({
  field,
  defaultValue,
  showMeta,
  mask,
  realAccountValue,
  inferredCategory,
}: {
  field: BillField;
  defaultValue: string;
  showMeta: boolean;
  mask?: boolean;
  realAccountValue?: string;
  inferredCategory?: string | null;
}) {
  const levelClass =
    field.needs_verification
      ? field.level === "LOW" || field.level === "MISSING"
        ? "field-risk"
        : "field-verify"
      : "";

  const label = (
    <>
      {field.label}
      {field.required ? <span className="required-mark"> *</span> : null}
      {!field.required ? (
        <span className="optional-tag"> (optional)</span>
      ) : null}
    </>
  );

  if (field.name === "account_id") {
    if (realAccountValue) {
      return (
        <label className={`field ${levelClass}`}>
          <span>{label}</span>
          <input
            readOnly
            value={maskAccount(realAccountValue)}
            aria-label="Account ID masked for privacy"
          />
          <input type="hidden" name="account_id_real" value={realAccountValue} />
          <FieldHint field={field} showMeta={showMeta} />
        </label>
      );
    }
    return (
      <label className={`field ${levelClass}`}>
        <span>{label}</span>
        <input
          name="account_id_real"
          defaultValue={defaultValue}
          placeholder="Not detected — please enter"
          aria-invalid={field.needs_verification}
          aria-required={field.required}
          autoComplete="off"
        />
        <FieldHint field={field} showMeta={showMeta} />
      </label>
    );
  }

  if (field.name === "is_bescom_bill") {
    return (
      <label className={`field ${levelClass}`}>
        <span>{label}</span>
        <select name={field.name} defaultValue={defaultValue || "true"}>
          <option value="true">Yes</option>
          <option value="false">No</option>
        </select>
        <FieldHint field={field} showMeta={showMeta} />
      </label>
    );
  }

  return (
    <label className={`field ${levelClass}`}>
      <span>{label}</span>
      <input
        name={field.name}
        defaultValue={defaultValue}
        placeholder={
          field.name === "consumer_category" && !defaultValue && inferredCategory
            ? `Inferred from tariff: ${inferredCategory} (optional)`
            : field.level === "MISSING"
              ? "Not detected — please enter"
              : undefined
        }
        aria-invalid={field.needs_verification}
        aria-required={field.required}
      />
      <FieldHint field={field} showMeta={showMeta} inferredCategory={inferredCategory} />
    </label>
  );
}

function FieldHint({
  field,
  showMeta,
  inferredCategory,
}: {
  field: BillField;
  showMeta: boolean;
  inferredCategory?: string | null;
}) {
  if (field.level === "MISSING" && field.required) {
    return <small className="field-hint bad">Required — please enter</small>;
  }
  if (field.level === "MISSING" && field.name === "consumer_category" && inferredCategory) {
    return (
      <small className="field-hint">
        Inferred from tariff: {inferredCategory}. Leave blank — domestic is confirmed on submit.
      </small>
    );
  }
  if (field.level === "MISSING") {
    return <small className="field-hint">Not detected on bill</small>;
  }
  if (field.needs_verification && field.level === "LOW") {
    return <small className="field-hint bad">Please verify this value</small>;
  }
  if (field.needs_verification) {
    return <small className="field-hint warn">Please verify</small>;
  }
  if (showMeta) {
    return (
      <small className="field-hint">
        {field.source} · {Math.round(field.confidence * 100)}% confidence
      </small>
    );
  }
  return null;
}

function buildInitialValues(analysis: BillAnalysis): Record<string, string> {
  const out: Record<string, string> = {};
  for (const section of analysis.sections) {
    for (const field of section.fields) {
      if (field.value === null || field.value === undefined) {
        out[field.name] = "";
      } else if (typeof field.value === "boolean") {
        out[field.name] = field.value ? "true" : "false";
      } else {
        out[field.name] = String(field.value);
      }
    }
  }
  return out;
}
