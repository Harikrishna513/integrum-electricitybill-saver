"""Tests for deterministic Bill Analysis calculations."""

from __future__ import annotations

from app.domain.models.consistency import BillConsistencyResult, ConsistencyStatus
from app.domain.models.validated_bill import (
    CanonicalElectricityBill,
    ParseStatus,
    ValidatedNumber,
)
from app.domain.services.bill_calculator import BillCalculator


def test_cost_per_unit_and_annualization():
    bill = CanonicalElectricityBill(
        units_consumed=ValidatedNumber(value=42.0, parse_status=ParseStatus.OK, confidence=1.0),
        total_amount=ValidatedNumber(value=272.0, parse_status=ParseStatus.OK, confidence=1.0),
        energy_charge=ValidatedNumber(value=243.6, parse_status=ParseStatus.OK, confidence=1.0),
        fixed_charge=ValidatedNumber(value=145.0, parse_status=ParseStatus.OK, confidence=1.0),
    )
    calc = BillCalculator().calculate(bill)
    assert calc.cost_per_unit == round(272 / 42, 4)
    assert calc.annualized_units_estimate == 504.0
    assert calc.annualized_amount_estimate == 3264.0


def test_charge_reconciliation_note_on_mismatch():
    bill = CanonicalElectricityBill(
        units_consumed=ValidatedNumber(value=100.0, parse_status=ParseStatus.OK, confidence=1.0),
        total_amount=ValidatedNumber(value=500.0, parse_status=ParseStatus.OK, confidence=1.0),
        energy_charge=ValidatedNumber(value=100.0, parse_status=ParseStatus.OK, confidence=1.0),
    )
    consistency = BillConsistencyResult(
        status=ConsistencyStatus.DISCREPANCY_DETECTED,
        summary_message="Discrepancy detected",
    )
    calc = BillCalculator().calculate(bill, consistency=consistency)
    assert any("verify" in n.lower() for n in calc.notes)
