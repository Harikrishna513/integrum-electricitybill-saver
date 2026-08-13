"""
Tests for Milestone 10 — versioned tariff engine.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.tariff import TariffEngine
from app.domain.models.tariff import TariffCalculationStatus
from app.infrastructure.rules.tariff_rules import TariffRuleRepository


def test_rule_selection_by_effective_date():
    repo = TariffRuleRepository()
    old = repo.get_rule(
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2024, 8, 1),
        tariff_code="LT-1",
    )
    new = repo.get_rule(
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2025, 8, 1),
        tariff_code="LT-1",
    )
    assert old is not None
    assert new is not None
    assert old.rule_version != new.rule_version
    assert "2024" in old.rule_version
    assert "2025" in new.rule_version


def test_calculate_uses_2025_rule_and_is_deterministic():
    engine = TariffEngine()
    result = engine.calculate(
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2025, 6, 15),
        units=120,
        sanctioned_load_kw=2,
        tariff_code="LT-1",
    )

    # Bootstrap 2025 slabs:
    # 50*4.50 + 50*5.80 + 20*7.00 = 225 + 290 + 140 = 655
    # fixed: 2*120 = 240
    # surcharge: 120*0.50 = 60
    # tax 9% of (655+240) = 0.09*895 = 80.55
    # total = 655+240+60+80.55 = 1035.55
    assert result.energy_charge == 655.0
    assert result.fixed_charge == 240.0
    assert result.surcharge_total == 60.0
    assert result.electricity_tax == 80.55
    assert result.estimated_total == 1035.55
    assert result.rule_version == "BESCOM_LT1_DOMESTIC_BOOTSTRAP_2025_04"
    assert result.verification_status == "UNVERIFIED_HYPOTHESIS"
    assert result.status == TariffCalculationStatus.REQUIRES_VERIFICATION


def test_calculate_2024_rule_different_total():
    engine = TariffEngine()
    result = engine.calculate(
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2024, 6, 15),
        units=120,
        sanctioned_load_kw=2,
        tariff_code="LT-1",
    )
    assert result.rule_version == "BESCOM_LT1_DOMESTIC_BOOTSTRAP_2024_04"
    # 30*4.10 + 70*5.55 + 20*7.10 = 123 + 388.5 + 142 = 653.5
    assert result.energy_charge == 653.5
    assert result.fixed_charge == 200.0  # 2 * 100


def test_unsupported_commercial():
    result = TariffEngine().calculate(
        discom="BESCOM",
        category="COMMERCIAL",
        as_of=date(2025, 6, 1),
        units=100,
    )
    assert result.status == TariffCalculationStatus.UNSUPPORTED_CATEGORY


def test_rule_not_found_before_effective():
    result = TariffEngine().calculate(
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2020, 1, 1),
        units=100,
        tariff_code="LT-1",
    )
    assert result.status == TariffCalculationStatus.RULE_NOT_FOUND
