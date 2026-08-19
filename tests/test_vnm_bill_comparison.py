"""Tests for individual VNM bill comparison (no society assumptions)."""

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


def _prefill() -> BillSolarPrefill:
    return BillSolarPrefill(
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
    )


def test_vnm_without_credit_does_not_fabricate_allocation():
    get_default_integrum_vnm_rule.cache_clear()
    result = build_vnm_comparison(_stored(), _prefill())
    assert result.needs_expected_credit is True
    assert result.expected_vnm_solar_credit_kwh is None
    assert result.solar_kwh_credited == 0
    assert result.current_bill.total == 2300
    assert result.vnm_bill.total == 0
    assert result.credit_input_prompt is not None
    assert not any("85%" in a for a in result.assumptions)


def test_vnm_comparison_uses_uploaded_bill_lines_and_user_credit():
    get_default_integrum_vnm_rule.cache_clear()
    result = build_vnm_comparison(_stored(), _prefill(), expected_vnm_solar_credit_kwh=102)
    assert result.provider == "Integrum Energy"
    assert result.current_bill.total == 2300
    assert result.sanctioned_load_kw == 1
    assert result.monthly_units == 120
    assert result.period_units_kwh == 120
    assert result.billing_period == "Jan 2026"
    assert any(l.code == "ENERGY" for l in result.current_bill.lines)
    assert any(l.code == "FPPCA" for l in result.current_bill.lines)
    assert result.solar_kwh_credited == 102
    assert result.residual_grid_kwh == 18
    assert result.needs_expected_credit is False
    assert result.assumed_flats is None
    assert result.community_plant_kwp is None
    assert not any("20-flat" in a.lower() for a in result.assumptions)
    assert not any("community plant" in a.lower() for a in result.assumptions)


def test_vnm_bill_lower_than_current_when_solar_credits_apply():
    result = build_vnm_comparison(_stored(), _prefill(), expected_vnm_solar_credit_kwh=102)
    assert result.vnm_bill.total < result.current_bill.total
    assert result.is_vnm_cheaper is True
    assert result.monthly_saving_inr > 0
    assert result.monthly_increase_inr == 0
    assert any(l.code == "INTEGRUM_SUB" for l in result.vnm_bill.lines)
    assert any(l.code == "SOLAR_CREDIT" for l in result.vnm_bill.lines)


def test_vnm_bill_uses_same_fixed_charge_from_bill():
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
    prefill = BillSolarPrefill(
        analysis_id="test-id",
        connection_id="RR1",
        consumer_name="Test",
        address="Bengaluru",
        period_units_kwh=42,
        monthly_units=42,
        sanctioned_load_kw=1,
        current_monthly_bill_inr=271.88,
        tariff_code="LT-1",
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2026, 2, 1),
        suggested_plant_kwp=5,
        bill_date="2026-02-01",
        billing_period="01/01/2026 - 01/02/2026",
    )
    result = build_vnm_comparison(stored, prefill, expected_vnm_solar_credit_kwh=30)
    fixed_lines = [l for l in result.vnm_bill.lines if l.code == "BESCOM_FIXED"]
    assert fixed_lines
    assert fixed_lines[0].amount == 145
    assert any(l.code == "SUBSIDY" for l in result.current_bill.lines)
    assert result.current_bill.total == 271.88
    assert result.residual_grid_kwh == 12


def test_sanctioned_load_not_altered_in_vnm_scenario():
    result = build_vnm_comparison(_stored(), _prefill(), expected_vnm_solar_credit_kwh=65)
    assert result.sanctioned_load_kw == 1
    assert "1 kW" in result.current_bill.subtitle


def test_multi_month_bill_uses_period_units_with_user_credit():
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
    prefill = BillSolarPrefill(
        analysis_id="test-id",
        connection_id="RR1",
        consumer_name="Test",
        address="Bengaluru",
        period_units_kwh=94,
        monthly_units=47,
        sanctioned_load_kw=1,
        current_monthly_bill_inr=482,
        tariff_code="LT-1",
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2026, 8, 1),
        suggested_plant_kwp=1,
        bill_date="2026-08-01",
        billing_period="01/06/2026 - 01/08/2026",
        billing_period_months=2.0,
        is_multi_month_period=True,
        period_consumption_note="94 kWh is total for ~2 months, not single-month.",
    )
    result = build_vnm_comparison(stored, prefill, expected_vnm_solar_credit_kwh=65)
    assert result.is_multi_month_period is True
    assert result.period_units_kwh == 94
    assert result.monthly_units == 47
    assert result.solar_kwh_credited == 65
    assert result.residual_grid_kwh == 29
    assert result.current_bill.units_kwh == 94
    assert "94" in result.current_bill.subtitle
    assert "47" in result.current_bill.subtitle


def test_credit_cannot_exceed_period_consumption():
    result = build_vnm_comparison(_stored(), _prefill(), expected_vnm_solar_credit_kwh=500)
    assert result.solar_kwh_credited == 120
    assert result.residual_grid_kwh == 0
