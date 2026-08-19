from __future__ import annotations

from app.domain.models.bill_analysis import BillCalculationView
from app.domain.models.consistency import BillConsistencyResult
from app.domain.models.validated_bill import CanonicalElectricityBill, ParseStatus
from app.domain.services.billing_period import (
    normalize_period_consumption,
    parse_billing_period,
)


class BillCalculator:
    def calculate(
        self,
        bill: CanonicalElectricityBill,
        *,
        consistency: BillConsistencyResult | None = None,
    ) -> BillCalculationView:
        notes: list[str] = []
        units = bill.units_consumed.value
        total = bill.total_amount.value

        cost_per_unit = None
        if units and units > 0 and total is not None:
            cost_per_unit = round(total / units, 4)
            notes.append("Cost per unit = total_amount ÷ units_consumed.")

        charge_lines_sum = _sum_charge_lines(bill)
        charge_total_delta = None
        if charge_lines_sum is not None and total is not None:
            charge_total_delta = round(total - charge_lines_sum, 2)
            if abs(charge_total_delta) > 1.0:
                notes.append(
                    "Charge lines do not fully reconcile with total_amount. "
                    "Verify highlighted fields against the printed bill."
                )

        annualized_units = None
        annualized_amount = None
        monthly_equiv = units
        period_months = 1.0
        is_multi_month = False
        if units is not None:
            period_info = parse_billing_period(bill.billing_period.value)
            monthly_equiv, period_note = normalize_period_consumption(float(units), period_info)
            period_months = period_info.approximate_months
            is_multi_month = period_info.is_multi_month
            if is_multi_month and period_months > 1.0:
                annualized_units = round(monthly_equiv * 12, 2)
                notes.append(
                    f"Bill covers ~{period_months:g} months — {units:g} kWh is the period total, "
                    f"not single-month consumption (~{monthly_equiv:g} kWh/month average)."
                )
                if period_note:
                    notes.append(period_note)
            else:
                annualized_units = round(units * 12, 2)
                notes.append(
                    "Annualized estimate assumes this bill represents one typical month."
                )
        if total is not None:
            if is_multi_month and period_months > 1.0:
                annualized_amount = round((total / period_months) * 12, 2)
            else:
                annualized_amount = round(total * 12, 2)

        if consistency and consistency.has_discrepancy:
            notes.append(
                "Some extracted values do not appear consistent. "
                "Please verify them against the original bill."
            )

        return BillCalculationView(
            units_consumed=units,
            total_amount=total,
            cost_per_unit=cost_per_unit,
            charge_lines_sum=charge_lines_sum,
            charge_total_delta=charge_total_delta,
            annualized_units_estimate=annualized_units,
            annualized_amount_estimate=annualized_amount,
            monthly_units_equivalent=monthly_equiv if units is not None else None,
            billing_period_months=period_months,
            is_multi_month_period=is_multi_month,
            notes=notes,
        )


def _sum_charge_lines(bill: CanonicalElectricityBill) -> float | None:
    fields = (
        bill.energy_charge,
        bill.fixed_charge,
        bill.electricity_tax,
        bill.fppca,
        bill.other_charges,
        bill.arrears,
        bill.late_payment_charge,
    )
    values: list[float] = []
    for field in fields:
        if field.parse_status == ParseStatus.OK and field.value is not None:
            values.append(float(field.value))
    subsidy = bill.subsidy
    if subsidy.parse_status == ParseStatus.OK and subsidy.value is not None:
        values.append(-abs(float(subsidy.value)))
    if not values:
        return None
    return round(sum(values), 2)
