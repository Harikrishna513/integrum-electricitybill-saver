"""
Tests for Milestone 9 — consumption analysis (pure Python math).
"""

from __future__ import annotations

from datetime import date

from app.domain.models.consumption import TrendDirection
from app.domain.models.history import BillHistoryItem, BillHistorySummary
from app.domain.services.consumption_analyzer import ConsumptionAnalyzer


def _bill(
    analysis_id: str,
    bill_date: date,
    units: float,
    amount: float,
) -> BillHistoryItem:
    return BillHistoryItem(
        analysis_id=analysis_id,
        document_id=f"doc-{analysis_id}",
        bill_date=bill_date,
        billing_period=bill_date.strftime("%b-%Y"),
        units_consumed=units,
        total_amount=amount,
        category="DOMESTIC",
    )


def test_mom_and_overall_percentages():
    history = BillHistorySummary(
        consumer_id="c1",
        discom="BESCOM",
        rr_number="RR1",
        bill_count=4,
        bills=[
            _bill("1", date(2026, 1, 1), 180, 1200),
            _bill("2", date(2026, 2, 1), 200, 1400),
            _bill("3", date(2026, 3, 1), 220, 1600),
            _bill("4", date(2026, 4, 1), 242, 1800),
        ],
    )
    result = ConsumptionAnalyzer().analyze_history(history)

    assert result.status == "OK"
    assert result.sample_count == 4
    assert result.average_units == 210.5  # (180+200+220+242)/4
    assert result.min_units == 180
    assert result.max_units == 242

    assert result.month_over_month is not None
    # 242 vs 220 = +10%
    assert result.month_over_month.percent_units == 10.0
    assert result.month_over_month.absolute_units == 22.0

    assert result.overall_change is not None
    # 242 vs 180 = +34.444...%
    assert result.overall_change.from_units == 180
    assert result.overall_change.to_units == 242
    assert abs(result.overall_change.percent_units - ((242 - 180) / 180 * 100)) < 0.01

    assert result.units_trend == TrendDirection.INCREASING
    assert any("10.0%" in i or "10%" in i for i in result.insights)


def test_yoy_when_comparable_bill_exists():
    history = BillHistorySummary(
        consumer_id="c1",
        bill_count=2,
        bills=[
            _bill("old", date(2025, 4, 10), 200, 1400),
            _bill("new", date(2026, 4, 12), 250, 1750),
        ],
    )
    result = ConsumptionAnalyzer().analyze_history(history)
    assert result.year_over_year is not None
    assert result.year_over_year.percent_units == 25.0


def test_insufficient_data():
    history = BillHistorySummary(consumer_id="c1", bill_count=0, bills=[])
    result = ConsumptionAnalyzer().analyze_history(history)
    assert result.status == "INSUFFICIENT_DATA"
    assert result.units_trend == TrendDirection.INSUFFICIENT_DATA


def test_stable_trend():
    history = BillHistorySummary(
        consumer_id="c1",
        bill_count=4,
        bills=[
            _bill("1", date(2026, 1, 1), 200, 1400),
            _bill("2", date(2026, 2, 1), 202, 1410),
            _bill("3", date(2026, 3, 1), 198, 1390),
            _bill("4", date(2026, 4, 1), 201, 1405),
        ],
    )
    result = ConsumptionAnalyzer().analyze_history(history)
    assert result.units_trend == TrendDirection.STABLE
