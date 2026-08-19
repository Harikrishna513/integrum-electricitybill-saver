from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, computed_field


class BillHistoryItem(BaseModel):
    analysis_id: str
    document_id: str
    bill_date: date | None = None
    billing_period: str | None = None
    units_consumed: float | None = None
    total_amount: float | None = None
    tariff_code: str | None = None
    category: str | None = None
    consistency_status: str | None = None
    created_at: str | None = None


class DuplicateBillWarning(BaseModel):
    code: str
    message: str
    matched_analysis_id: str | None = None
    match_reason: str


class BillHistorySummary(BaseModel):
    consumer_id: str
    discom: str | None = None
    rr_number: str | None = None
    account_id: str | None = None
    bill_count: int
    bills: list[BillHistoryItem] = Field(default_factory=list)
    duplicate_warnings: list[DuplicateBillWarning] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oldest_bill_date(self) -> date | None:
        dates = [b.bill_date for b in self.bills if b.bill_date is not None]
        return min(dates) if dates else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def newest_bill_date(self) -> date | None:
        dates = [b.bill_date for b in self.bills if b.bill_date is not None]
        return max(dates) if dates else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ready_for_trend_analysis(self) -> bool:
        """Milestone 9 needs ideally 3+ bills with dates/units."""
        dated = [b for b in self.bills if b.bill_date is not None and b.units_consumed is not None]
        return len(dated) >= 3
