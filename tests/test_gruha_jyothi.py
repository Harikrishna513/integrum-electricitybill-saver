"""
Tests for Milestone 11 — Gruha Jyothi engine.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.gruha_jyothi import GruhaJyothiEngine
from app.domain.models.gruha_jyothi import GruhaJyothiStatus


def test_insufficient_information_without_baseline():
    result = GruhaJyothiEngine().assess(
        category="DOMESTIC",
        current_units=150,
        as_of=date(2026, 1, 1),
    )
    assert result.status == GruhaJyothiStatus.INSUFFICIENT_INFORMATION
    assert "baseline_fy_2022_23_avg_units" in result.missing_inputs
    assert "approved" not in result.user_message.lower()


def test_not_applicable_for_commercial():
    result = GruhaJyothiEngine().assess(
        category="COMMERCIAL",
        baseline_fy_2022_23_avg_units=100,
        current_units=120,
    )
    assert result.status == GruhaJyothiStatus.NOT_APPLICABLE


def test_entitlement_baseline_plus_10_percent_capped():
    # 100 * 1.10 = 110
    result = GruhaJyothiEngine().assess(
        category="DOMESTIC",
        baseline_fy_2022_23_avg_units=100,
        current_units=90,
        as_of=date(2026, 1, 1),
    )
    assert result.computed_entitlement_units == 110.0
    assert result.appears_fully_covered_this_month is True
    assert result.units_beyond_entitlement == 0
    assert result.status == GruhaJyothiStatus.REQUIRES_OFFICIAL_VERIFICATION
    assert "approved" not in result.user_message.lower()


def test_entitlement_hard_cap_200():
    # 190 * 1.10 = 209 → cap 200
    result = GruhaJyothiEngine().assess(
        category="DOMESTIC",
        baseline_fy_2022_23_avg_units=190,
        current_units=210,
    )
    assert result.computed_entitlement_units == 200.0
    assert result.units_beyond_entitlement == 10.0
    assert result.appears_fully_covered_this_month is False


def test_never_invents_baseline_from_current_only():
    result = GruhaJyothiEngine().assess(
        category="DOMESTIC",
        current_units=80,
    )
    assert result.computed_entitlement_units is None
    assert result.status == GruhaJyothiStatus.INSUFFICIENT_INFORMATION
