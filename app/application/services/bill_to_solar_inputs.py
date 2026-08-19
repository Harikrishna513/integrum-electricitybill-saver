"""Map a confirmed bill analysis to solar / VNM / GNM inputs."""

from __future__ import annotations

from datetime import date

from app.domain.models.solar_options import BillSolarPrefill
from app.domain.models.validated_bill import BillValidationResult, CanonicalElectricityBill
from app.domain.services.billing_period import (
    normalize_period_consumption,
    parse_billing_period,
)
from app.infrastructure.persistence.repository import StoredBillAnalysis


def suggest_plant_kwp(monthly_units: float, sanctioned_load_kw: float) -> float:
    """Rough rooftop size from consumption (matches solar engine sizing intent)."""
    annual_units = monthly_units * 12.0
    yield_yr = 1500.0  # kWh/kWp/year — bootstrap default from solar rules
    target_frac = 0.85
    raw_kwp = (annual_units * target_frac) / yield_yr if yield_yr > 0 else 0.0
    max_from_load = sanctioned_load_kw * 1.0
    candidate = min(raw_kwp, max_from_load, 10.0)
    candidate = max(candidate, 1.0)
    return round(candidate * 2) / 2  # step 0.5 kWp


def bill_prefill_from_stored(stored: StoredBillAnalysis) -> BillSolarPrefill:
    validation = BillValidationResult.model_validate(stored.validation)
    bill = validation.bill
    period_units = _num(bill.units_consumed) or stored.units_consumed or 0.0
    billing_period_label = bill.billing_period.value or stored.billing_period
    extraction_notes = None
    if hasattr(bill, "extraction_notes"):
        notes_field = getattr(bill, "extraction_notes", None)
        if notes_field and hasattr(notes_field, "value"):
            extraction_notes = notes_field.value

    period_info = parse_billing_period(
        billing_period_label,
        extraction_notes=extraction_notes,
    )
    monthly_equiv, period_note = normalize_period_consumption(
        float(period_units), period_info
    )

    sanctioned_load = _num(bill.sanctioned_load) or stored.sanctioned_load or 3.0
    as_of = bill.bill_date.value or stored.bill_date or date.today()
    connection_id = (
        bill.rr_number.value
        or bill.account_id.value
        or stored.rr_number
        or stored.account_id
        or stored.id[:8]
    )
    return BillSolarPrefill(
        analysis_id=stored.id,
        connection_id=str(connection_id),
        consumer_name=bill.consumer_name.value,
        address=bill.address.value,
        period_units_kwh=float(period_units),
        monthly_units=float(monthly_equiv),
        sanctioned_load_kw=float(sanctioned_load),
        current_monthly_bill_inr=_num(bill.total_amount) or stored.total_amount,
        tariff_code=bill.tariff_code.value or stored.tariff_code or "LT-1",
        discom=(bill.discom.value or bill.utility.value or stored.discom or "BESCOM").upper(),
        category=(stored.category or "DOMESTIC").upper(),
        as_of=as_of,
        suggested_plant_kwp=suggest_plant_kwp(float(monthly_equiv), float(sanctioned_load)),
        bill_date=as_of.isoformat() if as_of else None,
        billing_period=billing_period_label,
        billing_period_days=period_info.period_days,
        billing_period_months=period_info.approximate_months,
        is_multi_month_period=period_info.is_multi_month,
        period_consumption_note=period_note,
    )


def _num(field) -> float | None:
    if field is None:
        return None
    if hasattr(field, "value"):
        val = field.value
    else:
        val = field
    if val is None:
        return None
    return float(val)
