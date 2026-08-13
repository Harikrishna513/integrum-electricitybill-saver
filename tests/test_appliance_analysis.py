"""
Tests for Milestone 13 — appliance analysis.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.appliance import ApplianceAnalysisEngine
from app.domain.models.appliance import EvType, HouseholdApplianceProfile


def test_analyze_ac_geyser_shares_are_estimates():
    profile = HouseholdApplianceProfile(
        people_count=4,
        ac_count=1,
        ac_hours_per_day=6,
        geyser=True,
        geyser_hours_per_day=1,
        refrigerator=True,
        fan_count=3,
    )
    result = ApplianceAnalysisEngine().analyze(profile, bill_units=400)

    assert result.status == "ESTIMATED"
    assert result.estimated_total_kwh > 0
    ids = {a.appliance_id for a in result.appliances}
    assert "ac" in ids
    assert "geyser" in ids
    ac = next(a for a in result.appliances if a.appliance_id == "ac")
    assert ac.estimated_kwh_month == 270.0
    assert "not a measured" in ac.note.lower()
    assert abs(sum(a.share_of_estimated_total_percent for a in result.appliances) - 100) < 0.2


def test_ev_adds_load():
    base = HouseholdApplianceProfile(people_count=2, refrigerator=True, fan_count=1)
    with_ev = HouseholdApplianceProfile(
        people_count=2,
        refrigerator=True,
        fan_count=1,
        ev_type=EvType.FOUR_WHEELER,
    )
    engine = ApplianceAnalysisEngine()
    a = engine.analyze(base)
    b = engine.analyze(with_ev)
    assert b.estimated_total_kwh > a.estimated_total_kwh
    assert any(x.appliance_id == "ev_4w" for x in b.appliances)


def test_tailored_savings_uses_profile_overrides():
    profile = HouseholdApplianceProfile(
        people_count=3,
        ac_count=2,
        ac_hours_per_day=8,
        geyser=True,
        fan_count=4,
        refrigerator=True,
    )
    analysis, estimates = ApplianceAnalysisEngine().tailored_savings(
        profile,
        bill_units=500,
        as_of=date(2025, 6, 15),
        sanctioned_load_kw=3,
    )
    assert analysis.status == "ESTIMATED"
    assert estimates
    assert any(e.recommendation_id == "ac_raise_temperature" for e in estimates)
    ac_est = next(e for e in estimates if e.recommendation_id == "ac_raise_temperature")
    assert ac_est.units_saved == 144.0
