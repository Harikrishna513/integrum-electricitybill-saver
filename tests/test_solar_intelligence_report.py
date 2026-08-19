"""Tests for Solar Intelligence Report builder."""

from __future__ import annotations

from datetime import date

from app.application.services.solar_intelligence_report import build_solar_intelligence_report
from app.domain.models.solar_options import BillSolarPrefill, SolarOptionCard


def _prefill(**kwargs) -> BillSolarPrefill:
    base = dict(
        analysis_id="test-id",
        connection_id="RR123",
        consumer_name="Test User",
        address="123 MG Road, Bengaluru 560066",
        period_units_kwh=248.0,
        monthly_units=248.0,
        sanctioned_load_kw=3.0,
        current_monthly_bill_inr=2607.0,
        tariff_code="LT-1",
        discom="BESCOM",
        category="DOMESTIC",
        as_of=date(2026, 2, 1),
        suggested_plant_kwp=1.5,
        bill_date="2026-02-01",
        billing_period="01/01/2026 - 01/02/2026",
    )
    base.update(kwargs)
    return BillSolarPrefill(**base)


def test_individual_report_uses_engine_numbers():
    option = SolarOptionCard(
        option="individual_solar",
        title="Individual rooftop solar",
        status="ESTIMATED",
        monthly_saving_inr=367.0,
        plant_kwp=1.5,
        message="Estimated",
        result={
            "sizing": {"analyzed_kwp": 1.5},
            "generation": {
                "specific_yield_kwh_per_kwp_year": 1480,
                "estimated_annual_generation_kwh": 2220,
                "estimated_monthly_generation_kwh": 185,
            },
            "economics": {
                "gross_capex_inr": 75000,
                "estimated_cfa_inr": 48000,
                "net_capex_inr": 27000,
                "estimated_annual_saving_inr": 4404,
                "simple_payback_years": 6.1,
            },
            "estimated_monthly_units_offset": 185,
        },
    )
    report = build_solar_intelligence_report(option, _prefill())
    assert report.status == "ready"
    assert "560066" in report.headline
    assert report.sections[0].title == "System Recommendation"
    size_metric = report.sections[0].metrics[0]
    assert "1.5 kW" in size_metric.value
    assert size_metric.detail is not None
    assert "%" in size_metric.detail
    financial = report.sections[1]
    assert any(m.label == "PM Surya Ghar Subsidy" for m in financial.metrics)
    returns = report.sections[2]
    annual = next(m for m in returns.metrics if m.label == "Annual Electricity Savings")
    assert "4,404" in annual.value


def test_vnm_report_generated_for_group_option():
    option = SolarOptionCard(
        option="vnm",
        title="VNM",
        status="POTENTIALLY_SUITABLE",
        monthly_saving_inr=500.0,
        plant_kwp=5.0,
        message="Potentially suitable",
        result={
            "proposed_kwp": 5.0,
            "estimated_monthly_generation_kwh": 616.0,
            "estimated_group_monthly_saving_inr": 500.0,
        },
    )
    report = build_solar_intelligence_report(option, _prefill())
    assert report.option == "vnm"
    assert len(report.sections) >= 4
    assert "Virtual Net Metering" in report.headline
