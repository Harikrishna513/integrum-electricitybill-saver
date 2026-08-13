"""
Tests for Milestone 12 — savings engine.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.savings import SavingsEngine
from app.domain.engines.tariff import TariffEngine
from app.domain.models.savings import SavingsStatus


def test_direct_units_saved_uses_tariff_delta():
    engine = SavingsEngine()
    as_of = date(2025, 6, 15)
    current = 200.0
    saved = 60.0

    estimate = engine.estimate_from_units_saved(
        title="Geyser reduction",
        current_units=current,
        units_saved=saved,
        as_of=as_of,
        sanctioned_load_kw=2,
    )

    tariff = TariffEngine()
    old_bill = tariff.calculate(
        category="DOMESTIC",
        as_of=as_of,
        units=current,
        sanctioned_load_kw=2,
        tariff_code="LT-1",
    )
    new_bill = tariff.calculate(
        category="DOMESTIC",
        as_of=as_of,
        units=current - saved,
        sanctioned_load_kw=2,
        tariff_code="LT-1",
    )
    expected = round((old_bill.estimated_total or 0) - (new_bill.estimated_total or 0), 2)

    assert estimate.status == SavingsStatus.ESTIMATED
    assert estimate.units_saved == 60
    assert estimate.estimated_monthly_saving == expected
    assert estimate.estimated_annual_saving == round(expected * 12, 2)
    assert estimate.tariff_rule_version is not None
    assert "ESTIMATE" in estimate.warnings[0].upper() or "estimate" in estimate.warnings[0].lower()


def test_geyser_catalog_formula():
    # 2kW * 1h * 30d * 0.5 = 30 kWh
    estimate = SavingsEngine().estimate_recommendation(
        recommendation_id="geyser_reduce_runtime",
        current_units=250,
        as_of=date(2025, 6, 15),
        sanctioned_load_kw=2,
    )
    assert estimate.status == SavingsStatus.ESTIMATED
    assert estimate.units_saved == 30.0
    assert estimate.estimated_monthly_saving is not None
    assert estimate.estimated_monthly_saving > 0


def test_bldc_fan_formula():
    # 3 * (75-35)/1000 * 10 * 30 = 3 * 0.04 * 10 * 30 = 36 kWh
    estimate = SavingsEngine().estimate_recommendation(
        recommendation_id="replace_fans_bldc",
        current_units=300,
        as_of=date(2025, 6, 15),
        sanctioned_load_kw=2,
    )
    assert estimate.units_saved == 36.0


def test_recommend_all_sorted():
    results = SavingsEngine().recommend_all(
        current_units=300,
        as_of=date(2025, 6, 15),
        sanctioned_load_kw=2,
    )
    assert len(results) >= 3
    savings = [r.estimated_monthly_saving or 0 for r in results]
    assert savings == sorted(savings, reverse=True)


def test_unknown_recommendation():
    result = SavingsEngine().estimate_recommendation(
        recommendation_id="does_not_exist",
        current_units=100,
        as_of=date(2025, 6, 15),
    )
    assert result.status == SavingsStatus.INVALID_INPUT
