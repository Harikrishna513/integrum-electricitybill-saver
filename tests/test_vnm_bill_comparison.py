"""Tests for individual VNM bill comparison (sales illustrative model)."""

from __future__ import annotations

from datetime import date

from app.application.services.vnm_bill_comparison import build_vnm_comparison
from app.domain.models.solar_options import BillSolarPrefill
from app.infrastructure.persistence.repository import StoredBillAnalysis
from app.infrastructure.rules.integrum_vnm_rules import get_default_integrum_vnm_rule


def _field(value, status="ok"):
    return {"value": value, "parse_status": status}


def _stored(**validation_overrides) -> StoredBillAnalysis:
    bill = {
        "consumer_name": _field("Test"),
        "account_id": _field("ACC1"),
        "rr_number": _field("RR1"),
        "address": _field("Bengaluru 560066"),
        "utility": _field("BESCOM"),
        "discom": _field("BESCOM"),
        "tariff_code": _field("LT-1"),
        "billing_period": _field("Jan 2026"),
        "bill_date": _field("2026-02-01"),
        "units_consumed": _field(120),
        "sanctioned_load": _field(1),
        "energy_charge": _field(816),
        "fixed_charge": _field(150),
        "fppca": _field(55.2),
        "other_charges": _field(42),
        "electricity_tax": _field(86.94),
        "total_amount": _field(2300),
        "subsidy": _field(None, "missing"),
        "arrears": _field(None, "missing"),
        "late_payment_charge": _field(None, "missing"),
    }
    bill.update(validation_overrides)
    return StoredBillAnalysis(
        id="test-id",
        document_id="doc-1",
        consumer_id=None,
        model_name="test",
        discom="BESCOM",
        rr_number="RR1",
        account_id="ACC1",
        tariff_code="LT-1",
        category="DOMESTIC",
        classification_status="OK",
        consistency_status="OK",
        supported_by_app_v1=True,
        billing_period="Jan 2026",
        bill_date=date(2026, 2, 1),
        units_consumed=120,
        total_amount=2300,
        sanctioned_load=1,
        extraction={},
        validation={"bill": bill, "issues": []},
        classification={},
        consistency={},
        canonical_bill={},
        created_at="2026-02-01T00:00:00",
    )


def _prefill(**overrides) -> BillSolarPrefill:
    data = dict(
        analysis_id="test-id",
        connection_id="RR1",
        consumer_name="Test",
        address="Bengaluru 560066",
        period_units_kwh=120,
        monthly_units=120,
        sanctioned_load_kw=1,
        current_monthly_bill_inr=2300,
        tariff_code="LT-1",
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2026, 2, 1),
        suggested_plant_kwp=5,
        bill_date="2026-02-01",
        billing_period="Jan 2026",
        billing_period_months=1.0,
        is_multi_month_period=False,
    )
    data.update(overrides)
    return BillSolarPrefill(**data)


def test_default_sizes_plant_for_full_offset():
    get_default_integrum_vnm_rule.cache_clear()
    result = build_vnm_comparison(_stored(), _prefill())
    assert result.needs_expected_credit is False
    assert result.coverage_source == "illustrative_plant"
    assert result.monthly_kwh_per_kwp == 120
    assert result.illustrative_plant_kwp == 1.0  # 120 kWh → 1 kWp
    assert result.solar_kwh_credited == 120
    assert result.residual_grid_kwh == 0
    assert result.illustrative_rate_inr_per_kwh == 3.0
    assert result.vnm_energy_cost_inr == 360.0  # 120 × 3
    assert result.vnm_gst_inr == 64.8  # 18%
    assert result.vnm_service_total_inr == 424.8
    assert "1" in result.scenario_label and "kWp" in result.scenario_label
    assert not any("85%" in a for a in result.assumptions)
    assert result.methodology is not None
    assert len(result.monthly_chart) == 12


def test_plant_slider_half_kwp():
    get_default_integrum_vnm_rule.cache_clear()
    result = build_vnm_comparison(
        _stored(), _prefill(), illustrative_plant_kwp=0.5
    )
    assert result.illustrative_plant_kwp == 0.5
    assert result.solar_kwh_credited == 60  # 0.5 × 120
    assert result.residual_grid_kwh == 60
    assert result.vnm_energy_cost_inr == 180.0


def test_plant_slider_two_kwp_shows_surplus_above_consumption():
    result = build_vnm_comparison(
        _stored(), _prefill(), illustrative_plant_kwp=2.0
    )
    assert result.illustrative_plant_kwp == 2.0
    assert result.estimated_generation_kwh == 240  # 2 × 120
    assert result.solar_kwh_credited == 120  # offset capped at use
    assert result.surplus_kwh == 120
    assert result.residual_grid_kwh == 0
    assert result.surplus_note is not None
    assert any(l.code == "SURPLUS" for l in result.vnm_bill.lines)


def test_plant_five_kwp_larger_surplus():
    result = build_vnm_comparison(
        _stored(), _prefill(), illustrative_plant_kwp=5.0
    )
    assert result.estimated_generation_kwh == 600
    assert result.solar_kwh_credited == 120
    assert result.surplus_kwh == 480
    # VNM charge still only on offset units
    assert result.vnm_energy_cost_inr == 360.0


def test_provider_quote_overrides_coverage():
    get_default_integrum_vnm_rule.cache_clear()
    result = build_vnm_comparison(_stored(), _prefill(), expected_vnm_solar_credit_kwh=102)
    assert result.coverage_source == "provider_quote"
    assert result.solar_kwh_credited == 102
    assert result.residual_grid_kwh == 18
    assert result.assumed_flats is None
    assert result.community_plant_kwp is None
    assert any(l.code == "INTEGRUM_SUB" for l in result.vnm_bill.lines)
    assert any(l.code == "BESCOM_FIXED" for l in result.vnm_bill.lines)


def test_vnm_bill_lower_than_current_at_full_coverage():
    result = build_vnm_comparison(_stored(), _prefill())
    assert result.vnm_bill.total < result.current_bill.total
    assert result.is_vnm_cheaper is True
    assert result.monthly_saving_inr > 0
    assert result.annual_saving_inr > 0
    # Annual is sum of seasonal chart months (not necessarily ≠ monthly×12 when
    # surplus months keep the same saving as residual replaces BESCOM 1:1).
    assert abs(
        result.annual_saving_inr
        - sum(m.estimated_saving_inr for m in result.monthly_chart)
    ) < 0.05
    assert result.monthly_chart[0].estimated_bescom_bill_inr == result.current_bill.total


def test_fixed_charge_kept_in_residual_bescom():
    get_default_integrum_vnm_rule.cache_clear()
    stored = _stored(
        units_consumed=_field(42),
        energy_charge=_field(243.6),
        fixed_charge=_field(145),
        fppca=_field(10.08),
        other_charges=_field(15.12),
        electricity_tax=_field(21.92),
        total_amount=_field(271.88),
        subsidy=_field(163.84),
    )
    prefill = _prefill(
        period_units_kwh=42,
        monthly_units=42,
        current_monthly_bill_inr=271.88,
        billing_period="01/01/2026 - 01/02/2026",
    )
    result = build_vnm_comparison(stored, prefill, illustrative_plant_kwp=1.0)
    assert result.sanctioned_load_kw == 1
    # Fixed remains in remaining BESCOM (full offset → mostly fixed)
    assert result.residual_bescom_charges_inr >= 145
    assert any(l.code == "SUBSIDY" for l in result.current_bill.lines)
    assert result.has_gruha_jyothi is True
    assert result.gruha_jyothi_note is not None
    assert result.current_bill.total == 271.88


def test_sanctioned_load_not_altered():
    result = build_vnm_comparison(_stored(), _prefill())
    assert result.sanctioned_load_kw == 1
    assert "1 kW" in (result.current_bill.subtitle or "")


def test_multi_month_normalizes_to_monthly_average():
    get_default_integrum_vnm_rule.cache_clear()
    stored = _stored(
        billing_period=_field("01/06/2026 - 01/08/2026"),
        units_consumed=_field(94),
        energy_charge=_field(545.2),
        fixed_charge=_field(305),
        fppca=_field(15.29),
        other_charges=_field(32.9),
        electricity_tax=_field(49.07),
        total_amount=_field(482),
    )
    prefill = _prefill(
        period_units_kwh=94,
        monthly_units=47,
        sanctioned_load_kw=1,
        current_monthly_bill_inr=482,
        as_of=date(2026, 8, 1),
        bill_date="2026-08-01",
        billing_period="01/06/2026 - 01/08/2026",
        billing_period_months=2.0,
        is_multi_month_period=True,
        period_consumption_note="94 kWh is total for ~2 months, not single-month.",
    )
    result = build_vnm_comparison(stored, prefill)
    assert result.is_multi_month_period is True
    assert result.period_units_kwh == 94
    assert result.monthly_units == 47
    assert result.solar_kwh_credited == 47  # capped at monthly average
    assert result.residual_grid_kwh == 0
    assert result.illustrative_plant_kwp == 0.5  # 47/120 → round up to 0.5
    assert result.current_bill.total == 241.0  # 482 / 2
    assert result.monthly_chart[0].month_label == "Aug"  # starts from bill month


def test_multi_month_provider_quote_converted_to_monthly():
    stored = _stored(
        units_consumed=_field(94),
        total_amount=_field(482),
        fixed_charge=_field(305),
        energy_charge=_field(545.2),
        fppca=_field(15.29),
        other_charges=_field(32.9),
        electricity_tax=_field(49.07),
    )
    prefill = _prefill(
        period_units_kwh=94,
        monthly_units=47,
        billing_period_months=2.0,
        is_multi_month_period=True,
        as_of=date(2026, 8, 1),
        current_monthly_bill_inr=482,
    )
    # Quote of 65 kWh for the 2-month period → 32.5 kWh/month
    result = build_vnm_comparison(stored, prefill, expected_vnm_solar_credit_kwh=65)
    assert result.solar_kwh_credited == 32.5
    assert result.residual_grid_kwh == 14.5


def test_credit_cannot_exceed_period_consumption():
    result = build_vnm_comparison(_stored(), _prefill(), expected_vnm_solar_credit_kwh=500)
    assert result.solar_kwh_credited == 120
    assert result.residual_grid_kwh == 0


def test_electricity_tax_keeps_fixed_share_plus_residual():
    """100% offset keeps tax on fixed; partial residual adds tax on grid units."""
    get_default_integrum_vnm_rule.cache_clear()
    stored = _stored(
        units_consumed=_field(188),
        energy_charge=_field(1090.4),
        fixed_charge=_field(150),
        fppca=_field(47),
        other_charges=_field(69.56),
        electricity_tax=_field(122.13),
        total_amount=_field(1512),
    )
    prefill = _prefill(
        period_units_kwh=188,
        monthly_units=188,
        current_monthly_bill_inr=1512,
        billing_period="01/04/2026 - 01/05/2026",
    )

    full = build_vnm_comparison(stored, prefill, illustrative_plant_kwp=2.0)
    tax_full = next(l for l in full.vnm_bill.lines if l.code == "BESCOM_TAX")
    # pre_tax = 1090.4+150+47+69.56 = 1356.96; fixed share = 122.13 * 150/1356.96 ≈ 13.5
    assert abs(tax_full.amount - 13.5) < 0.05
    assert full.surplus_kwh > 0

    partial = build_vnm_comparison(stored, prefill, illustrative_plant_kwp=1.5)
    tax_partial = next(l for l in partial.vnm_bill.lines if l.code == "BESCOM_TAX")
    # Must be fixed share + residual variable tax (> fixed-only 13.5, not residual-only ~5)
    assert tax_partial.amount > tax_full.amount
    assert partial.residual_grid_kwh == 8
    assert "fixed share" in (tax_partial.detail or "")


def test_chart_first_month_matches_comparison_totals():
    get_default_integrum_vnm_rule.cache_clear()
    result = build_vnm_comparison(_stored(), _prefill(), illustrative_plant_kwp=1.0)
    assert result.monthly_chart
    first = result.monthly_chart[0]
    assert first.seasonal_factor == 1.0
    assert first.estimated_bescom_bill_inr == result.current_bill.total
    assert first.estimated_vnm_bill_inr == result.vnm_bill.total


def test_gst_shown_transparently():
    result = build_vnm_comparison(_stored(), _prefill())
    assert any(l.code == "INTEGRUM_SUB" for l in result.vnm_bill.lines)
    assert any(l.code == "D_GST" for l in result.calculation_detail_lines)
    assert result.cta_primary == "Get your VNM proposal"
    assert result.cta_url == "https://integrumenergy.in/contact/"
