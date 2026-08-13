"""
Tests for Milestone 14 — individual rooftop solar analysis.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.solar import SolarAnalysisEngine
from app.domain.engines.tariff import TariffEngine
from app.domain.models.solar import SolarAnalysisStatus, SolarProfile


AS_OF = date(2025, 6, 15)


def test_no_roof_points_to_vnm_path():
    result = SolarAnalysisEngine().analyze(
        SolarProfile(
            monthly_units=300,
            as_of=AS_OF,
            sanctioned_load_kw=3,
            roof_area_m2=0,
        )
    )
    assert result.status == SolarAnalysisStatus.NO_ROOF
    assert "vnm" in result.message.lower() or "virtual" in result.message.lower()


def test_recommend_and_estimate_savings_via_tariff():
    profile = SolarProfile(
        monthly_units=400,
        as_of=AS_OF,
        sanctioned_load_kw=5,
        roof_area_m2=40,
        apply_cfa_estimate=True,
    )
    result = SolarAnalysisEngine().analyze(profile)

    assert result.status == SolarAnalysisStatus.ESTIMATED
    assert result.sizing is not None
    assert result.sizing.analyzed_kwp >= 1.0
    assert result.generation is not None
    assert result.generation.estimated_monthly_generation_kwh > 0
    assert result.economics is not None
    assert result.economics.estimated_monthly_saving_inr is not None
    assert result.economics.estimated_monthly_saving_inr > 0
    assert result.economics.simple_payback_years is not None
    assert result.rule_version is not None
    assert result.verification_status == "REQUIRES_VERIFICATION"
    assert "estimate" in result.disclaimer.lower() or "estimated" in result.message.lower()

    # ₹ must match TariffEngine delta under simplified residual units
    residual = result.estimated_monthly_units_after_offset
    assert residual is not None
    tariff = TariffEngine()
    old_bill = tariff.calculate(
        category="DOMESTIC",
        as_of=AS_OF,
        units=400,
        sanctioned_load_kw=5,
        tariff_code="LT-1",
    )
    new_bill = tariff.calculate(
        category="DOMESTIC",
        as_of=AS_OF,
        units=residual,
        sanctioned_load_kw=5,
        tariff_code="LT-1",
    )
    expected = round((old_bill.estimated_total or 0) - (new_bill.estimated_total or 0), 2)
    assert result.economics.estimated_monthly_saving_inr == expected


def test_roof_caps_capacity():
    small_roof = SolarAnalysisEngine().analyze(
        SolarProfile(
            monthly_units=600,
            as_of=AS_OF,
            sanctioned_load_kw=10,
            roof_area_m2=10,  # ~1 kWp at 10 m²/kWp
        )
    )
    assert small_roof.status == SolarAnalysisStatus.ESTIMATED
    assert small_roof.sizing is not None
    assert small_roof.sizing.analyzed_kwp <= 1.0 + 1e-6
    assert "roof_area" in small_roof.sizing.capped_by


def test_cfa_slabs_for_3kw():
    # 2 kWp * 30000 + 1 kWp * 18000 = 78000
    engine = SolarAnalysisEngine()
    cfa = engine._estimate_cfa(3.0, engine.rule.cfa_pm_surya_ghar)
    assert cfa == 78000.0

    # 4 kWp still capped at 3 kWp CFA band
    cfa4 = engine._estimate_cfa(4.0, engine.rule.cfa_pm_surya_ghar)
    assert cfa4 == 78000.0


def test_proposed_kwp_overrides_recommendation():
    result = SolarAnalysisEngine().analyze(
        SolarProfile(
            monthly_units=250,
            as_of=AS_OF,
            sanctioned_load_kw=3,
            roof_area_m2=50,
            proposed_kwp=2.0,
        )
    )
    assert result.status == SolarAnalysisStatus.ESTIMATED
    assert result.sizing is not None
    assert result.sizing.analyzed_kwp == 2.0
