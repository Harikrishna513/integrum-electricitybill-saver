"use client";

import { useCallback, useState } from "react";
import { apiPost, apiUpload, apiUploadMany } from "@/lib/api";
import type {
  BatchItem,
  BatchResponse,
  BillAnalysis,
  ExtractResponse,
  ProcessingStep,
} from "@/lib/bill-analysis";
import { UploadPanel } from "@/components/bill-analysis/UploadPanel";
import { ProcessingSteps } from "@/components/bill-analysis/ProcessingSteps";
import { BillReviewForm } from "@/components/bill-analysis/BillReviewForm";
import {
  AnalysisSummary,
  BatchResults,
} from "@/components/bill-analysis/AnalysisSummary";

const STEP_DELAY_MS = 450;

async function runProcessingSteps(
  setStep: (s: ProcessingStep) => void
): Promise<void> {
  const steps: ProcessingStep[] = [
    "uploading",
    "reading",
    "extracting",
    "validating",
    "checking",
  ];
  for (const step of steps) {
    setStep(step);
    await new Promise((r) => setTimeout(r, STEP_DELAY_MS));
  }
}

export default function BillAnalysisPage() {
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState<ProcessingStep>("idle");
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<BillAnalysis | null>(null);
  const [batchItems, setBatchItems] = useState<BatchItem[]>([]);

  const showReview =
    analysis &&
    (analysis.status === "needs_review" ||
      analysis.status === "unsupported" ||
      analysis.needs_confirmation.length > 0) &&
    analysis.status !== "ready";

  const handleSingle = useCallback(async (file: File) => {
    setBusy(true);
    setError(null);
    setBatchItems([]);
    try {
      await runProcessingSteps(setStep);
      const res = await apiUpload<ExtractResponse>("/bills/extract", file);
      setAnalysis(res.analysis);
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
      await runProcessingSteps(setStep);
      const res = await apiUploadMany<BatchResponse>("/bills/extract-batch", files);
      setBatchItems(res.items);
      const firstReview =
        res.items.find((i) => i.analysis)?.analysis ??
        res.items.find((i) => i.analysis_id)?.analysis;
      if (firstReview) setAnalysis(firstReview);
      setStep("review");
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
        setStep(res.analysis.status === "ready" ? "ready" : "review");
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not save changes.");
      } finally {
        setBusy(false);
      }
    },
    [analysis?.analysis_id]
  );

  return (
    <div className="page">
      <header className="hero">
        <p className="eyebrow">Integrum Energy</p>
        <h1>Understand your electricity bill</h1>
        <p className="subtitle">
          Upload your BESCOM electricity bill and we&apos;ll extract, validate,
          and analyze your electricity usage.
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

          <BatchResults items={batchItems} />

          {showReview && analysis && (
            <BillReviewForm
              analysis={analysis}
              busy={busy}
              onConfirm={handleConfirm}
            />
          )}

          {analysis?.status === "ready" && (
            <div className="ready-banner">
              <h2>Bill analysis ready</h2>
              <p>
                Your bill is confirmed and saved. See the summary on the right.
              </p>
              <ul className="next-steps">
                <li>Upload more monthly bills (same RR number) to build consumption history.</li>
                <li>With 3+ bills, trend analysis becomes available in a future release.</li>
                <li>Solar and savings modules will use this history later — not in this phase.</li>
              </ul>
            </div>
          )}
        </div>

        <AnalysisSummary analysis={analysis} />
      </div>
    </div>
  );
}
