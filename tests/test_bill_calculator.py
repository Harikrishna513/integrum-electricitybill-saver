from __future__ import annotations

from app.domain.models.consistency import BillConsistencyResult, ConsistencyStatus
from app.domain.models.validated_bill import (
    CanonicalElectricityBill,
    ParseStatus,
    ValidatedNumber,
    ValidatedString,
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


def test_multi_month_bill_annualizes_from_monthly_average():
    bill = CanonicalElectricityBill(
        billing_period=ValidatedString(
            value="01/06/2026 - 01/08/2026",
            parse_status=ParseStatus.OK,
            confidence=1.0,
        ),
        units_consumed=ValidatedNumber(value=94.0, parse_status=ParseStatus.OK, confidence=1.0),
        total_amount=ValidatedNumber(value=482.0, parse_status=ParseStatus.OK, confidence=1.0),
    )
    calc = BillCalculator().calculate(bill)
    assert calc.is_multi_month_period is True
    assert calc.monthly_units_equivalent == 47.0
    assert calc.annualized_units_estimate == 564.0
    assert any("period total" in n.lower() for n in calc.notes)
