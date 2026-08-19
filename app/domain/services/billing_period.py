"""Parse BESCOM billing period strings — detect multi-month bills (e.g. Multiple Month BMD)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

# BESCOM often uses DD/MM/YYYY or DD-MM-YYYY in period ranges.
_PERIOD_RANGE = re.compile(
    r"(?P<start>\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\s*[-–—to]+\s*(?P<end>\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})",
    re.IGNORECASE,
)
_MULTI_MONTH_NOTE = re.compile(r"multiple\s+month", re.IGNORECASE)


@dataclass(frozen=True)
class BillingPeriodInfo:
    raw_label: str | None
    start_date: date | None
    end_date: date | None
    period_days: int | None
    approximate_months: float
    is_multi_month: bool
    multiple_month_bmd: bool
    parse_confidence: str  # high | low | unknown

    @property
    def consumption_label(self) -> str:
        """Human label for units — never call multi-month totals 'monthly' without qualification."""
        if self.is_multi_month and self.approximate_months > 1.0:
            months = self.approximate_months
            m = f"{months:g}" if months < 10 else f"{months:.0f}"
            return f"this billing period (~{m} months)"
        return "this billing period"


def parse_billing_period(
    label: str | None,
    *,
    extraction_notes: str | None = None,
) -> BillingPeriodInfo:
    text = (label or "").strip()
    notes = extraction_notes or ""
    bmd_hint = bool(_MULTI_MONTH_NOTE.search(notes))

    if not text:
        return BillingPeriodInfo(
            raw_label=None,
            start_date=None,
            end_date=None,
            period_days=None,
            approximate_months=1.0,
            is_multi_month=bmd_hint,
            multiple_month_bmd=bmd_hint,
            parse_confidence="unknown",
        )

    match = _PERIOD_RANGE.search(text)
    if not match:
        return BillingPeriodInfo(
            raw_label=text,
            start_date=None,
            end_date=None,
            period_days=None,
            approximate_months=1.0,
            is_multi_month=bmd_hint,
            multiple_month_bmd=bmd_hint,
            parse_confidence="low",
        )

    start = _parse_bescom_date(match.group("start"))
    end = _parse_bescom_date(match.group("end"))
    if start is None or end is None or end <= start:
        return BillingPeriodInfo(
            raw_label=text,
            start_date=start,
            end_date=end,
            period_days=None,
            approximate_months=1.0,
            is_multi_month=bmd_hint,
            multiple_month_bmd=bmd_hint,
            parse_confidence="low",
        )

    days = (end - start).days
    # ~30.4 days/month; >35 days or BMD note → multi-month
    approx_months = max(1.0, round(days / 30.437, 2))
    is_multi = bmd_hint or days > 35 or approx_months >= 1.9

    return BillingPeriodInfo(
        raw_label=text,
        start_date=start,
        end_date=end,
        period_days=days,
        approximate_months=approx_months if is_multi else 1.0,
        is_multi_month=is_multi,
        multiple_month_bmd=bmd_hint,
        parse_confidence="high",
    )


def normalize_period_consumption(
    period_units_kwh: float,
    period: BillingPeriodInfo,
) -> tuple[float, str | None]:
    """
    Return (monthly_equivalent_kwh, warning_note).
    Raw period_units stay unchanged on the bill; monthly equivalent is for sizing/trends only.
    """
    if period_units_kwh <= 0:
        return 0.0, None
    if not period.is_multi_month or period.approximate_months <= 1.0:
        return period_units_kwh, None
    monthly = round(period_units_kwh / period.approximate_months, 2)
    note = (
        f"Bill covers ~{period.approximate_months:g} months "
        f"({period.period_days} days). "
        f"{period_units_kwh:g} kWh is total for the period "
        f"(~{monthly:g} kWh/month average) — not single-month consumption."
    )
    if period.multiple_month_bmd:
        note += " BESCOM note: Multiple Month BMD."
    return monthly, note


def _parse_bescom_date(raw: str) -> date | None:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
