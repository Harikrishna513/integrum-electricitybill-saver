from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ReportMetric(BaseModel):
    label: str
    value: str
    detail: str | None = None


class ReportSection(BaseModel):
    id: str
    title: str
    metrics: list[ReportMetric] = Field(default_factory=list)


class SolarIntelligenceReport(BaseModel):
    option: Literal["individual_solar", "vnm", "gnm"]
    title: str
    status: str
    headline: str
    location_line: str
    property_type: str = "Residential"
    sections: list[ReportSection] = Field(default_factory=list)
    disclaimer: str
    actions: list[str] = Field(default_factory=lambda: [
        "Download Report",
        "Connect with Installer",
        "Learn About Carbon Credits",
    ])
    raw: dict[str, Any] = Field(default_factory=dict)
