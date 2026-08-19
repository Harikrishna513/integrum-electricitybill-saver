"""Tests for BESCOM billing period parsing."""

from __future__ import annotations

from app.domain.services.billing_period import (
    normalize_period_consumption,
    parse_billing_period,
)


def test_jun_july_two_month_period():
    info = parse_billing_period(
        "01/06/2026 - 01/08/2026",
        extraction_notes="Note: Bill is generated for Multiple Month BMD",
    )
    assert info.is_multi_month is True
    assert info.multiple_month_bmd is True
    assert info.period_days == 61
    assert info.approximate_months >= 1.9
    monthly, note = normalize_period_consumption(94, info)
    assert monthly == 47.0 or abs(monthly - 47) < 1.0
    assert note is not None
    assert "94" in note
    assert "not single-month" in note.lower() or "total for the period" in note


def test_single_month_period():
    info = parse_billing_period("01/01/2026 - 01/02/2026")
    assert info.is_multi_month is False
    assert info.approximate_months == 1.0
    monthly, note = normalize_period_consumption(42, info)
    assert monthly == 42
    assert note is None
