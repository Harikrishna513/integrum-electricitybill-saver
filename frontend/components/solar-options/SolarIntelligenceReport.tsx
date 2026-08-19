"use client";

import type { SolarIntelligenceReport as Report } from "@/lib/solar-options";
import { OPTION_LABELS } from "@/lib/solar-options";

type Props = {
  report: Report;
  highlighted?: boolean;
};

export function SolarIntelligenceReportView({ report, highlighted }: Props) {
  return (
    <article
      className={`solar-intelligence-report ${highlighted ? "highlighted" : ""}`}
    >
      <header className="sir-header">
        <div>
          <p className="sir-eyebrow">Report ready</p>
          <h3>{report.title}</h3>
          <p className="sir-headline">{report.headline}</p>
        </div>
        <span className={`sir-status ${report.status}`}>
          {OPTION_LABELS[report.option]}
        </span>
      </header>

      {report.sections.map((section) => (
        <section key={section.id} className="sir-section">
          <h4>{section.title}</h4>
          <div className="sir-metrics">
            {section.metrics.map((metric) => (
              <div key={metric.label} className="sir-metric">
                <span className="sir-metric-label">{metric.label}</span>
                <strong className="sir-metric-value">{metric.value}</strong>
                {metric.detail && (
                  <span className="sir-metric-detail">{metric.detail}</span>
                )}
              </div>
            ))}
          </div>
        </section>
      ))}

      <p className="sir-disclaimer">{report.disclaimer}</p>

      <div className="sir-actions">
        {report.actions.map((action) => (
          <button key={action} type="button" className="ghost" disabled>
            {action}
          </button>
        ))}
      </div>
    </article>
  );
}
