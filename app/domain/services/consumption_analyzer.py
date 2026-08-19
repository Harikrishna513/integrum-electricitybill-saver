from __future__ import annotations

from datetime import date

from app.domain.models.consumption import (
    ChangeMetric,
    ConsumptionAnalysisResult,
    MonthlyConsumptionPoint,
    PeriodAverage,
    TrendDirection,
)
from app.domain.models.history import BillHistoryItem, BillHistorySummary

# Trend is STABLE if absolute % change across recent window is below this
STABLE_PERCENT_THRESHOLD = 5.0


class ConsumptionAnalyzer:
    def analyze_history(self, history: BillHistorySummary) -> ConsumptionAnalysisResult:
        return self.analyze_bills(
            consumer_id=history.consumer_id,
            bills=history.bills,
        )

    def analyze_bills(
        self,
        *,
        consumer_id: str,
        bills: list[BillHistoryItem],
    ) -> ConsumptionAnalysisResult:
        series = self._build_series(bills)
        assumptions = [
            "Only bills with both bill_date and units_consumed are included.",
            "Month-over-month compares the two most recent dated bills (not calendar-month aligned).",
            "Year-over-year matches bills ~11–13 months apart when available.",
            "Percentages are Python-calculated: ((new - old) / old) * 100.",
            "FACT = stored bill values; CALCULATED = derived metrics below.",
        ]

        if len(series) < 1:
            return ConsumptionAnalysisResult(
                consumer_id=consumer_id,
                status="INSUFFICIENT_DATA",
                sample_count=0,
                insights=[
                    "Not enough dated consumption data. Upload bills with readable dates and units."
                ],
                assumptions=assumptions,
            )

        units = [p.units_consumed for p in series]
        amounts = [p.total_amount for p in series if p.total_amount is not None]

        avg_units = _mean(units)
        avg_amount = _mean(amounts) if amounts else None

        result = ConsumptionAnalysisResult(
            consumer_id=consumer_id,
            status="OK",
            sample_count=len(series),
            monthly_series=series,
            min_units=min(units),
            max_units=max(units),
            min_amount=min(amounts) if amounts else None,
            max_amount=max(amounts) if amounts else None,
            average_units=avg_units,
            average_amount=avg_amount,
            averages_by_window=self._window_averages(series),
            month_over_month=self._month_over_month(series),
            overall_change=self._overall_change(series),
            year_over_year=self._year_over_year(series),
            units_trend=self._trend([p.units_consumed for p in series]),
            amount_trend=self._trend(
                [p.total_amount for p in series if p.total_amount is not None]
            ),
            assumptions=assumptions,
        )
        result.insights = self._build_insights(result)
        return result

    def _build_series(self, bills: list[BillHistoryItem]) -> list[MonthlyConsumptionPoint]:
        points: list[MonthlyConsumptionPoint] = []
        for bill in bills:
            if bill.bill_date is None or bill.units_consumed is None:
                continue
            points.append(
                MonthlyConsumptionPoint(
                    analysis_id=bill.analysis_id,
                    bill_date=bill.bill_date,
                    billing_period=bill.billing_period,
                    units_consumed=float(bill.units_consumed),
                    total_amount=(
                        float(bill.total_amount) if bill.total_amount is not None else None
                    ),
                )
            )
        points.sort(key=lambda p: p.bill_date)
        return points

    def _window_averages(
        self, series: list[MonthlyConsumptionPoint]
    ) -> list[PeriodAverage]:
        out: list[PeriodAverage] = []
        for window in (3, 6, 12):
            sample = series[-window:]
            if not sample:
                continue
            units = [p.units_consumed for p in sample]
            amounts = [p.total_amount for p in sample if p.total_amount is not None]
            out.append(
                PeriodAverage(
                    window_months=window,
                    sample_count=len(sample),
                    average_units=_mean(units),
                    average_amount=_mean(amounts) if amounts else None,
                )
            )
        return out

    def _month_over_month(
        self, series: list[MonthlyConsumptionPoint]
    ) -> ChangeMetric | None:
        if len(series) < 2:
            return None
        prev, curr = series[-2], series[-1]
        return _change_metric(
            label="month_over_month",
            from_point=prev,
            to_point=curr,
            note="Compared the two most recent dated bills in history order.",
        )

    def _overall_change(
        self, series: list[MonthlyConsumptionPoint]
    ) -> ChangeMetric | None:
        if len(series) < 2:
            return None
        return _change_metric(
            label="overall_first_to_last",
            from_point=series[0],
            to_point=series[-1],
            note=f"Compared first and last of {len(series)} dated bills.",
        )

    def _year_over_year(
        self, series: list[MonthlyConsumptionPoint]
    ) -> ChangeMetric | None:
        if len(series) < 2:
            return None
        latest = series[-1]
        # Find a prior bill roughly 11–13 months earlier
        candidates = []
        for prior in series[:-1]:
            days = (latest.bill_date - prior.bill_date).days
            if 334 <= days <= 397:  # ~11–13 months
                candidates.append(prior)
        if not candidates:
            return ChangeMetric(
                label="year_over_year",
                note="No comparable bill found ~12 months before the latest bill.",
            )
        # Prefer closest to 365 days
        prior = min(
            candidates,
            key=lambda p: abs((latest.bill_date - p.bill_date).days - 365),
        )
        return _change_metric(
            label="year_over_year",
            from_point=prior,
            to_point=latest,
            note="Compared latest bill to closest bill about one year earlier.",
        )

    def _trend(self, values: list[float]) -> TrendDirection:
        if len(values) < 3:
            return TrendDirection.INSUFFICIENT_DATA
        # Compare average of first half vs second half
        mid = len(values) // 2
        first = _mean(values[:mid])
        second = _mean(values[mid:])
        if first is None or second is None or first == 0:
            return TrendDirection.INSUFFICIENT_DATA
        percent = ((second - first) / first) * 100
        if abs(percent) < STABLE_PERCENT_THRESHOLD:
            return TrendDirection.STABLE
        return TrendDirection.INCREASING if percent > 0 else TrendDirection.DECREASING

    def _build_insights(self, result: ConsumptionAnalysisResult) -> list[str]:
        insights: list[str] = []
        if result.sample_count == 1:
            insights.append(
                f"Only one dated bill is available ({result.monthly_series[0].units_consumed:g} units). "
                "Upload more bills for trend analysis."
            )
            return insights

        if result.average_units is not None:
            insights.append(
                f"Average consumption across {result.sample_count} dated bills is "
                f"{result.average_units:.1f} units/bill."
            )

        if result.min_units is not None and result.max_units is not None:
            insights.append(
                f"Units ranged from {result.min_units:g} to {result.max_units:g}."
            )

        mom = result.month_over_month
        if mom and mom.percent_units is not None:
            direction = "increased" if mom.percent_units > 0 else "decreased"
            insights.append(
                f"Consumption {direction} {abs(mom.percent_units):.1f}% "
                f"from the previous bill "
                f"({mom.from_units:g} → {mom.to_units:g} units)."
            )
            if mom.percent_amount is not None:
                bill_dir = "increased" if mom.percent_amount > 0 else "decreased"
                insights.append(
                    f"Bill amount {bill_dir} {abs(mom.percent_amount):.1f}% "
                    f"over the same interval."
                )

        overall = result.overall_change
        if overall and overall.percent_units is not None and result.sample_count >= 3:
            direction = "increased" if overall.percent_units > 0 else "decreased"
            insights.append(
                f"Over the full history ({result.sample_count} bills), consumption "
                f"{direction} {abs(overall.percent_units):.1f}% "
                f"({overall.from_units:g} → {overall.to_units:g} units)."
            )

        yoy = result.year_over_year
        if yoy and yoy.percent_units is not None:
            direction = "increased" if yoy.percent_units > 0 else "decreased"
            insights.append(
                f"Year-over-year, consumption {direction} {abs(yoy.percent_units):.1f}%."
            )
        elif yoy and yoy.note:
            insights.append(yoy.note)

        insights.append(
            f"Units trend classification: {result.units_trend.value} "
            f"(stable threshold ±{STABLE_PERCENT_THRESHOLD:g}%)."
        )
        return insights


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _percent_change(old: float, new: float) -> float | None:
    if old == 0:
        return None
    return round(((new - old) / old) * 100.0, 4)


def _change_metric(
    *,
    label: str,
    from_point: MonthlyConsumptionPoint,
    to_point: MonthlyConsumptionPoint,
    note: str | None = None,
) -> ChangeMetric:
    abs_units = round(to_point.units_consumed - from_point.units_consumed, 4)
    pct_units = _percent_change(from_point.units_consumed, to_point.units_consumed)

    abs_amount = None
    pct_amount = None
    if from_point.total_amount is not None and to_point.total_amount is not None:
        abs_amount = round(to_point.total_amount - from_point.total_amount, 4)
        pct_amount = _percent_change(from_point.total_amount, to_point.total_amount)

    return ChangeMetric(
        label=label,
        from_units=from_point.units_consumed,
        to_units=to_point.units_consumed,
        absolute_units=abs_units,
        percent_units=pct_units,
        from_amount=from_point.total_amount,
        to_amount=to_point.total_amount,
        absolute_amount=abs_amount,
        percent_amount=pct_amount,
        from_date=from_point.bill_date,
        to_date=to_point.bill_date,
        note=note,
    )
