"use client";

import { useCallback, useMemo, useState } from "react";
import { apiPost, apiUpload, apiUploadMany } from "@/lib/api";
import type {
  BatchItem,
  BatchResponse,
  BillAnalysis,
  ExtractResponse,
  ProcessingStep,
} from "@/lib/bill-analysis";
import { computeBatchAggregate } from "@/lib/batch-aggregate";
import { UploadPanel } from "@/components/bill-analysis/UploadPanel";
import { ProcessingSteps } from "@/components/bill-analysis/ProcessingSteps";
import { BillReviewForm } from "@/components/bill-analysis/BillReviewForm";
import { PartialBillNotice } from "@/components/bill-analysis/PartialBillNotice";
import {
  AnalysisSummary,
  BatchResults,
} from "@/components/bill-analysis/AnalysisSummary";
import { MultiBillSummary } from "@/components/bill-analysis/MultiBillSummary";
import { SolarOptionsPanel } from "@/components/solar-options/SolarOptionsPanel";

const STEP_DELAY_MS = 200;

async function runProcessingSteps(
  setStep: (s: ProcessingStep) => void,
  until: ProcessingStep = "extracting"
): Promise<void> {
  const steps: ProcessingStep[] = [
    "uploading",
    "reading",
    "extracting",
    "validating",
    "checking",
  ];
  const stopAt = steps.indexOf(until);
  for (let i = 0; i <= stopAt; i++) {
    setStep(steps[i]);
    await new Promise((r) => setTimeout(r, STEP_DELAY_MS));
  }
}

function pickInitialBatchItem(items: BatchItem[]): BatchItem | undefined {
  const withAnalysis = items.filter((i) => i.analysis && !i.error);
  const needsReview = withAnalysis.find((i) => i.status === "needs_review");
  return needsReview ?? withAnalysis[withAnalysis.length - 1] ?? withAnalysis[0];
}

export default function BillAnalysisPage() {
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<ProcessingStep>("idle");
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<BillAnalysis | null>(null);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);
  const [selectedAnalysisId, setSelectedAnalysisId] = useState<string | null>(null);
  const [editConfirmed, setEditConfirmed] = useState(false);

  const batchAggregate = useMemo(
    () => computeBatchAggregate(batchItems),
    [batchItems]
  );

  const selectedMonthLabel = useMemo(() => {
    if (!selectedAnalysisId || !batchAggregate) return null;
    return (
      batchAggregate.months.find((m) => m.analysisId === selectedAnalysisId)
        ?.label ?? null
    );
  }, [selectedAnalysisId, batchAggregate]);

  const selectBatchItem = useCallback((item: BatchItem, openForEdit = false) => {
    if (!item.analysis || !item.analysis_id) return;
    setAnalysis(item.analysis);
    setSelectedAnalysisId(item.analysis_id);
    setEditConfirmed(openForEdit);
    setStep(
      item.analysis.status === "ready" && !openForEdit ? "ready" : "review"
    );
  }, []);

  const showReview =
    analysis &&
    (editConfirmed ||
      (analysis.status !== "ready" &&
        (analysis.status === "needs_review" ||
          analysis.status === "unsupported" ||
          analysis.needs_confirmation.length > 0)));

  const showPartialNotice =
    analysis && analysis.status !== "ready" && !analysis.support.supported;

  const allBatchReady =
    batchItems.length > 0 &&
    batchItems.every((i) => i.error || i.status === "ready");

  const handleSingle = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    setBatchItems([]);
    setSelectedAnalysisId(null);
    try {
      await runProcessingSteps(setStep, "extracting");
      const res = await apiUpload<ExtractResponse>("/bills/extract", file);
      setStep("validating");
      setAnalysis(res.analysis);
      setSelectedAnalysisId(res.analysis.analysis_id);
      setStep(res.analysis.status === "ready" ? "ready" : "review");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed.");
      setStep("error");
    } finally {
      setBusy(false);
    }
  }, []);

  const handleMultiple = useCallback(async (files: File[]) => {
    setBusy(true);
    setError(null);
    try {
      await runProcessingSteps(setStep, "extracting");
      const res = await apiUploadMany<BatchResponse>("/bills/extract-batch", files);
      setStep("validating");
      setBatchItems(res.items);
      const initial = pickInitialBatchItem(res.items);
      if (initial?.analysis && initial.analysis_id) {
        setAnalysis(initial.analysis);
        setSelectedAnalysisId(initial.analysis_id);
        setStep(initial.analysis.status === "ready" ? "ready" : "review");
      } else {
        setAnalysis(null);
        setSelectedAnalysisId(null);
        setStep("review");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Batch upload failed.");
      setStep("error");
    } finally {
      setBusy(false);
    }
  }, []);

  const handleConfirm = useCallback(
    async (payload: {
      corrections: Record<string, string | number | boolean>;
      confirm_category: "DOMESTIC";
      accept_extracted_as_printed: string[];
    }) => {
      if (!analysis?.analysis_id) return;
      setBusy(true);
      setError(null);
      try {
        const res = await apiPost<ExtractResponse>(
          `/bills/${analysis.analysis_id}/confirm`,
          payload
        );
        setAnalysis(res.analysis);
        setBatchItems((prev) =>
          prev.map((item) =>
            item.analysis_id === res.analysis.analysis_id
              ? {
                  ...item,
                  status: res.analysis.status,
                  analysis: res.analysis,
                  units_consumed:
                    res.analysis.calculations?.units_consumed ??
                    item.units_consumed,
                  total_amount:
                    res.analysis.calculations?.total_amount ?? item.total_amount,
                  needs_confirmation: res.analysis.needs_confirmation,
                }
              : item
          )
        );
        setStep(res.analysis.status === "ready" ? "ready" : "review");
        setEditConfirmed(false);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save changes.");
      } finally {
        setBusy(false);
      }
    },
    [analysis?.analysis_id]
  );

  const showSolar =
    (batchItems.length <= 1 && analysis?.status === "ready") ||
    (batchItems.length > 1 && allBatchReady && analysis?.status === "ready");

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Integrum Energy</p>
        <h1>Understand your electricity bill</h1>
        <p className="subtitle">
          Upload your BESCOM electricity bill and we&apos;ll extract, validate,
          and analyze your electricity usage. Upload multiple months (same account)
          to see consumption history and trends.
        </p>
        <div className="scope-badges">
          <span>Karnataka</span>
          <span>BESCOM</span>
          <span>Domestic / Residential</span>
          <span>PDF · JPG · PNG</span>
        </div>
      </header>

      <div className="workspace">
        <div className="workspace-main">
          <UploadPanel
            disabled={busy}
            onUploadSingle={handleSingle}
            onUploadMultiple={handleMultiple}
          />

          <ProcessingSteps step={step} />

          {error && (
            <div className="alert bad" role="alert">
              {error}
            </div>
          )}

          {batchAggregate && (
            <MultiBillSummary
              aggregate={batchAggregate}
              selectedId={selectedAnalysisId}
              onSelectMonth={(id) => {
                const item = batchItems.find((i) => i.analysis_id === id);
                if (item) selectBatchItem(item);
              }}
            />
          )}

          <BatchResults
            items={batchItems}
            selectedId={selectedAnalysisId}
            onSelect={(item) => selectBatchItem(item, item.status === "ready")}
          />

          {showPartialNotice && analysis && (
            <PartialBillNotice analysis={analysis} />
          )}

          {showReview && analysis && (
            <>
              {batchItems.length > 1 && (
                <p className="reviewing-month-banner">
                  {editConfirmed && analysis.status === "ready" ? (
                    <>
                      Editing <strong>{selectedMonthLabel ?? "selected month"}</strong>
                      {" "}— correct extracted values, then save.
                    </>
                  ) : (
                    <>
                      Reviewing <strong>{selectedMonthLabel ?? "selected month"}</strong>
                      {" "}— confirm this bill, then select the next month above.
                    </>
                  )}
                </p>
              )}
              <BillReviewForm
                analysis={analysis}
                busy={busy}
                editing={editConfirmed && analysis.status === "ready"}
                onConfirm={handleConfirm}
              />
            </>
          )}

          {analysis?.status === "unsupported" && (
            <div className="ready-banner error-banner">
              <h2>Bill could not be analyzed</h2>
              <p>{analysis.message}</p>
              <p>
                After review, this bill still does not meet BESCOM domestic criteria.
                Upload a full domestic BESCOM bill or contact support.
              </p>
            </div>
          )}

          {analysis?.status === "ready" && batchItems.length <= 1 && (
            <div className="ready-banner">
              <h2>Your monthly bill summary</h2>
              <p>{analysis.message}</p>
              <ul className="next-steps">
                <li>Compare VNM savings below.</li>
                <li>Upload more monthly bills (same account) to build history.</li>
              </ul>
            </div>
          )}

          {batchItems.length > 1 && allBatchReady && batchAggregate && (
            <div className="ready-banner">
              <h2>{batchAggregate.billCount} months confirmed</h2>
              <p>
                {batchAggregate.periodLabel} · {batchAggregate.totalUnits.toLocaleString("en-IN")} kWh
                total · {batchAggregate.totalAmount.toLocaleString("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 })}
              </p>
              <p className="summary-note">
                VNM comparison uses average monthly usage across confirmed bills.
              </p>
            </div>
          )}

          {analysis?.support.supported && analysis.analysis_id && (
              <SolarOptionsPanel
                analysisId={analysis.analysis_id}
                enabled={analysis.status === "ready"}
              />
            )}
        </div>

        <AnalysisSummary
          analysis={analysis}
          batchAggregate={batchAggregate}
          selectedMonthLabel={selectedMonthLabel}
          onEditConfirmed={
            analysis?.status === "ready"
              ? () => setEditConfirmed(true)
              : undefined
          }
        />
      </div>
    </div>
  );
}
