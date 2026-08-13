import type { ProcessingStep } from "@/lib/bill-analysis";

const STEPS: ProcessingStep[] = [
  "uploading",
  "reading",
  "extracting",
  "validating",
  "checking",
];

type Props = {
  step: ProcessingStep;
};

export function ProcessingSteps({ step }: Props) {
  if (step === "idle" || step === "ready" || step === "review" || step === "error") {
    return null;
  }

  const activeIndex = STEPS.indexOf(step);

  return (
    <div className="processing" aria-live="polite">
      {STEPS.map((s, i) => {
        const done = i < activeIndex;
        const active = i === activeIndex;
        return (
          <div
            key={s}
            className={`processing-step ${done ? "done" : ""} ${active ? "active" : ""}`}
          >
            <span className="processing-dot" aria-hidden />
            <span>
              {s === "uploading" && "Uploading"}
              {s === "reading" && "Reading bill"}
              {s === "extracting" && "Extracting details"}
              {s === "validating" && "Validating"}
              {s === "checking" && "Checking eligibility"}
            </span>
          </div>
        );
      })}
    </div>
  );
}
