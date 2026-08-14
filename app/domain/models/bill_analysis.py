"""
Bill Analysis presentation models — Integrum Energy production module.

These DTOs shape API responses for the Bill Analysis UI.
They do not replace domain models; they describe what the client should render.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


BillAnalysisStatus = Literal[
    "needs_review",
    "ready",
    "unsupported",
    "error",
]

ConfidenceLevel = Literal["HIGH", "MEDIUM", "LOW", "MISSING"]


class FieldAuditEntry(BaseModel):
    field: str
    original_value: Any | None = None
    corrected_value: Any | None = None
    corrected_by_user: bool = True
    corrected_at: datetime
    action: Literal["corrected", "accepted_as_printed", "category_confirmed"]


class BillFieldView(BaseModel):
    name: str
    label: str
    section: str
    value: Any | None = None
    display_value: str
    confidence: float = 0.0
    level: ConfidenceLevel = "MISSING"
    source: str = "unknown"
    needs_verification: bool = False
    editable: bool = True
    required: bool = False


class BillSectionView(BaseModel):
    id: str
    title: str
    fields: list[BillFieldView] = Field(default_factory=list)


class SupportView(BaseModel):
    supported: bool
    state: str = "Karnataka"
    discom: str | None = None
    category: str | None = None
    is_bescom_bill: bool | None = None
    can_analyze: bool = False
    message: str
    block_reasons: list[str] = Field(default_factory=list)


class ValidationIssueView(BaseModel):
    code: str
    message: str
    field: str | None = None
    severity: str = "WARNING"


class BillCalculationView(BaseModel):
    units_consumed: float | None = None
    total_amount: float | None = None
    cost_per_unit: float | None = None
    charge_lines_sum: float | None = None
    charge_total_delta: float | None = None
    annualized_units_estimate: float | None = None
    annualized_amount_estimate: float | None = None
    notes: list[str] = Field(default_factory=list)


class HistoryBillView(BaseModel):
    analysis_id: str
    billing_period: str | None = None
    bill_date: str | None = None
    units_consumed: float | None = None
    total_amount: float | None = None


class HistorySummaryView(BaseModel):
    consumer_id: str | None = None
    bill_count: int = 0
    ready_for_trend_analysis: bool = False
    bills: list[HistoryBillView] = Field(default_factory=list)
    duplicate_warnings: list[str] = Field(default_factory=list)


class BillAnalysisView(BaseModel):
    analysis_id: str
    status: BillAnalysisStatus
    message: str
    document: dict[str, Any] = Field(default_factory=dict)
    sections: list[BillSectionView] = Field(default_factory=list)
    support: SupportView
    validation_issues: list[ValidationIssueView] = Field(default_factory=list)
    consistency_warnings: list[str] = Field(default_factory=list)
    needs_confirmation: list[str] = Field(default_factory=list)
    calculations: BillCalculationView | None = None
    history: HistorySummaryView | None = None
    corrections_audit: list[FieldAuditEntry] = Field(default_factory=list)
    confirmed: bool = False
