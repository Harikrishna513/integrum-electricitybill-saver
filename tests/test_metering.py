"""
Tests for Milestone 15 — net / gross metering concepts + settlement.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.metering import NetMeteringEngine
from app.domain.engines.tariff import TariffEngine
from app.domain.models.metering import MeteringArrangement, MeteringSettlementStatus


AS_OF = date(2025, 6, 15)


def test_concepts_include_four_arrangements():
    concepts = NetMeteringEngine().list_concepts()
    ids = {c.arrangement for c in concepts}
    assert MeteringArrangement.NET_METERING in ids
    assert MeteringArrangement.GROSS_METERING in ids
    assert MeteringArrangement.VIRTUAL_NET_METERING in ids
    assert MeteringArrangement.GROUP_NET_METERING in ids
    vnm = next(c for c in concepts if c.arrangement == MeteringArrangement.VIRTUAL_NET_METERING)
    assert "IMPLEMENTED" in vnm.implementation_status or "16" in vnm.implementation_status


def test_register_identity_import_minus_export_equals_c_minus_g():
    regs = NetMeteringEngine().derive_registers(
        consumption_kwh=400,
        generation_kwh=250,
        coincidence_fraction=0.4,
    )
    assert abs((regs.import_kwh - regs.export_kwh) - (400 - 250)) < 1e-6
    assert regs.self_consumed_kwh == 100.0  # min(400,250)*0.4


def test_net_metering_when_consumption_exceeds_generation():
    result = NetMeteringEngine().settle(
        arrangement=MeteringArrangement.NET_METERING,
        consumption_kwh=400,
        generation_kwh=250,
        as_of=AS_OF,
        sanctioned_load_kw=5,
        coincidence_fraction=1.0,
        availed_cfa=False,
    )
    assert result.status == MeteringSettlementStatus.ESTIMATED
    assert result.registers is not None
    assert result.registers.net_import_kwh == 150.0
    assert result.export_credit_or_sale_inr == 0.0

    tariff = TariffEngine()
    baseline = tariff.calculate(
        category="DOMESTIC", as_of=AS_OF, units=400, sanctioned_load_kw=5, tariff_code="LT-1"
    )
    residual = tariff.calculate(
        category="DOMESTIC", as_of=AS_OF, units=150, sanctioned_load_kw=5, tariff_code="LT-1"
    )
    expected_saving = round(
        (baseline.estimated_total or 0) - (residual.estimated_total or 0), 2
    )
    assert result.estimated_monthly_saving_inr == expected_saving


def test_net_metering_export_credit_when_generation_exceeds_consumption():
    result = NetMeteringEngine().settle(
        arrangement=MeteringArrangement.NET_METERING,
        consumption_kwh=200,
        generation_kwh=350,
        as_of=AS_OF,
        sanctioned_load_kw=5,
        coincidence_fraction=1.0,
        availed_cfa=False,
    )
    assert result.status == MeteringSettlementStatus.ESTIMATED
    assert result.registers is not None
    assert result.registers.net_import_kwh == -150.0
    # 150 * 4.50 without CFA
    assert result.export_credit_or_sale_inr == 675.0
    assert result.estimated_net_cost_inr is not None
    # net cost = TariffEngine(0) - 675
    zero_bill = TariffEngine().calculate(
        category="DOMESTIC", as_of=AS_OF, units=0, sanctioned_load_kw=5, tariff_code="LT-1"
    )
    expected_net = round((zero_bill.estimated_total or 0) - 675.0, 2)
    assert result.estimated_net_cost_inr == expected_net


def test_gross_sells_all_generation():
    result = NetMeteringEngine().settle(
        arrangement=MeteringArrangement.GROSS_METERING,
        consumption_kwh=300,
        generation_kwh=100,
        as_of=AS_OF,
        sanctioned_load_kw=3,
        availed_cfa=True,  # 2.97 / kWh
    )
    assert result.status == MeteringSettlementStatus.ESTIMATED
    assert result.export_credit_or_sale_inr == 297.0
    assert result.retail_bill_after_arrangement_inr == result.baseline_retail_bill_inr


def test_vnm_is_concept_only():
    result = NetMeteringEngine().settle(
        arrangement=MeteringArrangement.VIRTUAL_NET_METERING,
        consumption_kwh=200,
        generation_kwh=200,
        as_of=AS_OF,
    )
    assert result.status == MeteringSettlementStatus.CONCEPT_ONLY
    assert "16" in result.message


def test_compare_net_vs_gross():
    cmp = NetMeteringEngine().compare(
        consumption_kwh=400,
        generation_kwh=300,
        as_of=AS_OF,
        sanctioned_load_kw=5,
    )
    assert cmp.status == "ESTIMATED"
    assert cmp.net.status == MeteringSettlementStatus.ESTIMATED
    assert cmp.gross.status == MeteringSettlementStatus.ESTIMATED
    assert cmp.preferred_hint
