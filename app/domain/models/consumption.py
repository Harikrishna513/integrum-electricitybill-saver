from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class TrendDirection(str, Enum):
    INCREASING = "INCREASING"
    DECREASING = "DECREASING"
    STABLE = "STABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class MonthlyConsumptionPoint(BaseModel):
    analysis_id: str
    bill_date: date
    billing_period: str | None = None
    units_consumed: float
    total_amount: float | None = None


class PeriodAverage(BaseModel):
    window_months: int
    sample_count: int
    average_units: float | None = None
    average_amount: float | None = None


class ChangeMetric(BaseModel):
    label: str
    from_units: float | None = None
    to_units: float | None = None
    absolute_units: float | None = None
    percent_units: float | None = None
    from_amount: float | None = None
    to_amount: float | None = None
    absolute_amount: float | None = None
    percent_amount: float | None = None
    from_date: date | None = None
    to_date: date | None = None
    note: str | None = None


class ConsumptionAnalysisResult(BaseModel):
    consumer_id: str
    status: str  # OK | INSUFFICIENT_DATA
    sample_count: int
    monthly_series: list[MonthlyConsumptionPoint] = Field(default_factory=list)

    min_units: float | None = None
    max_units: float | None = None
    min_amount: float | None = None
    max_amount: float | None = None

    average_units: float | None = None
    average_amount: float | None = None
    averages_by_window: list[PeriodAverage] = Field(default_factory=list)

    month_over_month: ChangeMetric | None = None
    overall_change: ChangeMetric | None = None
    year_over_year: ChangeMetric | None = None

    units_trend: TrendDirection = TrendDirection.INSUFFICIENT_DATA
    amount_trend: TrendDirection = TrendDirection.INSUFFICIENT_DATA

    insights: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
