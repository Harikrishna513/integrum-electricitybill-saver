"""VNM bill comparison — individual consumer sales estimate (no society assumptions)."""

from __future__ import annotations

import math

from app.domain.models.solar_options import BillSolarPrefill
from app.domain.models.validated_bill import BillValidationResult, CanonicalElectricityBill, ParseStatus
from app.domain.models.vnm_comparison import (
    BillLineItem,
    BillScenario,
    MonthlyBillEstimate,
    VNMComparisonView,
    VNMMethodology,
)
from app.infrastructure.persistence.repository import StoredBillAnalysis
from app.infrastructure.rules.integrum_vnm_rules import IntegrumVNMRule, get_default_integrum_vnm_rule

_VARIABLE_CHARGE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("energy_charge", "ENERGY", "Energy charges"),
    ("fppca", "FPPCA", "FPPCA"),
    ("other_charges", "OTHER", "P & G / other charges"),
)

_MONTH_NAMES = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def build_vnm_comparison(
    stored: StoredBillAnalysis,
    prefill: BillSolarPrefill,
    *,
    illustrative_plant_kwp: float | None = None,
    illustrative_coverage_fraction: float | None = None,
    expected_vnm_solar_credit_kwh: float | None = None,
    provider_rule: IntegrumVNMRule | None = None,
) -> VNMComparisonView:
    """
    Sales-focused VNM estimate from a confirmed bill.

    - Monthly baseline = period units ÷ billing months (multi-month BMD safe).
    - Default = plant sized for ~100% offset (1 kWp ≈ N kWh/month from config).
    - Optional advanced quote kWh overrides the plant explorer.
    """
    rule = provider_rule or get_default_integrum_vnm_rule()

    validation = BillValidationResult.model_validate(stored.validation)
    bill = validation.bill

    period_units = float(prefill.period_units_kwh)
    period_months = max(1.0, float(prefill.billing_period_months or 1.0))
    monthly_baseline = float(prefill.monthly_units)
    sanctioned = float(prefill.sanctioned_load_kw)

    scenario = rule.individual_scenario
    kwh_per_kwp = float(scenario.get("illustrative_monthly_kwh_per_kwp", 120))
    min_kwp = float(scenario.get("min_plant_kwp", 0.5))
    max_kwp = float(scenario.get("max_plant_kwp", 10.0))
    step_kwp = float(scenario.get("plant_step_kwp", 0.5))
    default_kwp = _default_plant_kwp(
        monthly_baseline, kwh_per_kwp, min_kwp, max_kwp, step_kwp
    )

    using_quote = expected_vnm_solar_credit_kwh is not None
    plant_kwp = default_kwp
    estimated_generation = 0.0

    if using_quote:
        period_credit = min(period_units, max(0.0, float(expected_vnm_solar_credit_kwh)))
        solar_monthly = round(period_credit / period_months, 2)
        estimated_generation = solar_monthly
        plant_kwp = (
            round(solar_monthly / kwh_per_kwp, 2) if kwh_per_kwp > 0 else default_kwp
        )
        scenario_label = (
            f"Advanced — provider quote ≈ {solar_monthly:g} kWh/month "
            f"(from {period_credit:g} kWh for the billing period)"
        )
        coverage_source = "provider_quote"
    elif illustrative_plant_kwp is not None:
        plant_kwp = _clamp_plant(float(illustrative_plant_kwp), min_kwp, max_kwp, step_kwp)
        estimated_generation = round(plant_kwp * kwh_per_kwp, 2)
        solar_monthly = round(min(monthly_baseline, estimated_generation), 2)
        scenario_label = (
            f"Illustrative plant {plant_kwp:g} kWp → ~{estimated_generation:g} units/month "
            f"({kwh_per_kwp:g} units per kWp)"
        )
        coverage_source = "illustrative_plant"
    elif illustrative_coverage_fraction is not None:
        coverage = max(0.0, min(1.0, float(illustrative_coverage_fraction)))
        solar_monthly = round(monthly_baseline * coverage, 2)
        estimated_generation = solar_monthly
        plant_kwp = (
            _clamp_plant(solar_monthly / kwh_per_kwp, min_kwp, max_kwp, step_kwp)
            if kwh_per_kwp > 0
            else default_kwp
        )
        scenario_label = (
            f"Illustrative plant {plant_kwp:g} kWp → {solar_monthly:g} kWh/month "
            f"(legacy coverage {coverage * 100:.0f}%)"
        )
        coverage_source = "illustrative_plant"
    else:
        plant_kwp = default_kwp
        estimated_generation = round(plant_kwp * kwh_per_kwp, 2)
        solar_monthly = round(min(monthly_baseline, estimated_generation), 2)
        scenario_label = (
            f"Illustrative plant {plant_kwp:g} kWp → ~{estimated_generation:g} units/month "
            f"(sized for ~100% of your {monthly_baseline:g} kWh consumption)"
        )
        coverage_source = "illustrative_plant"

    coverage = (
        round(solar_monthly / monthly_baseline, 4) if monthly_baseline > 0 else 0.0
    )
    residual_monthly = round(max(0.0, monthly_baseline - solar_monthly), 2)
    surplus_kwh = round(max(0.0, estimated_generation - monthly_baseline), 2)
    surplus_note = None
    if surplus_kwh > 0:
        surplus_note = (
            f"Extra solar this month: {surplus_kwh:g} kWh. "
            "Surplus units bank month-to-month; financial settlement is yearly "
            "(as per the provider proposal — not credited as cash on this bill)."
        )
    rate = _illustrative_rate(rule)
    gst_pct = float(rule.subscription.get("gst_percent", 18.0))

    current = _current_bill_scenario(bill, prefill, period_units, monthly_baseline)
    period_bill_total = current.total
    monthly_current = round(period_bill_total / period_months, 2)
    if period_months > 1.01:
        current = _monthlyize_scenario(current, period_months, monthly_baseline)

    vnm_month = _vnm_month_estimate(
        bill=bill,
        monthly_baseline=monthly_baseline,
        residual_monthly=residual_monthly,
        solar_monthly=solar_monthly,
        estimated_generation=estimated_generation,
        surplus_kwh=surplus_kwh,
        rate=rate,
        gst_pct=gst_pct,
        provider_name=rule.provider_name,
        current_total=period_bill_total,
    )

    monthly_diff = round(monthly_current - vnm_month["total"], 2)
    is_cheaper = monthly_diff > 0
    monthly_saving = round(max(0.0, monthly_diff), 2)
    monthly_increase = round(max(0.0, -monthly_diff), 2)

    start_month = _start_month(prefill)
    chart = _seasonal_chart(
        rule=rule,
        bill=bill,
        monthly_baseline=monthly_baseline,
        plant_kwp=plant_kwp,
        kwh_per_kwp=kwh_per_kwp,
        solar_monthly_fixed=solar_monthly if using_quote else None,
        rate=rate,
        gst_pct=gst_pct,
        provider_name=rule.provider_name,
        current_total=period_bill_total,
        start_month=start_month,
        anchor_bescom_inr=monthly_current,
        anchor_vnm_inr=vnm_month["total"],
    )
    annual_bescom = round(sum(m.estimated_bescom_bill_inr for m in chart), 2)
    annual_vnm = round(sum(m.estimated_vnm_bill_inr for m in chart), 2)
    annual_diff = round(annual_bescom - annual_vnm, 2)
    annual_saving = round(max(0.0, annual_diff), 2)
    annual_increase = round(max(0.0, -annual_diff), 2)

    subsidy = _subsidy_amount(bill)
    has_gj = subsidy > 0 or _looks_gruha_jyothi(bill, monthly_current, monthly_baseline)
    gj_note = rule.user_messages.get("gruha_jyothi_note") if has_gj else None

    residual_bundle = vnm_month["residual_bescom"]
    vnm_service = vnm_month["vnm_service_total"]
    vnm_lines = vnm_month["lines"]
    detail_lines = vnm_month["detail_lines"]

    vnm_scenario = BillScenario(
        title="With VNM Solar — Estimated",
        subtitle=(
            f"{monthly_baseline:g} kWh/mo baseline · {plant_kwp:g} kWp · "
            f"~{estimated_generation:g} kWh gen · {solar_monthly:g} kWh offset"
            + (f" · {surplus_kwh:g} kWh surplus" if surplus_kwh > 0 else "")
            + f" · {residual_monthly:g} kWh remaining grid · {sanctioned:g} kW load"
        ),
        lines=vnm_lines,
        total=vnm_month["total"],
        units_kwh=monthly_baseline,
        notes=[
            scenario_label + ".",
            f"Rule of thumb: 1 kWp ≈ {kwh_per_kwp:g} units/month (illustrative).",
            *( [surplus_note] if surplus_note else [] ),
            "Illustrative commercial rate — not an official provider tariff.",
            "Fixed / non-energy BESCOM charges kept from your confirmed bill where applicable.",
        ],
    )

    methodology = VNMMethodology(
        monthly_baseline_kwh=monthly_baseline,
        coverage_fraction=round(coverage, 4),
        coverage_label=scenario_label,
        coverage_source=coverage_source,
        illustrative_plant_kwp=plant_kwp,
        monthly_kwh_per_kwp=kwh_per_kwp,
        illustrative_rate_inr_per_kwh=rate,
        gst_percent=gst_pct,
        seasonal_model_label=str(
            (rule.seasonal_model or {}).get(
                "label", "Illustrative seasonal consumption factors"
            )
        ),
        steps=[
            f"Monthly baseline from confirmed bill: {monthly_baseline:g} kWh/month"
            + (
                f" ({period_units:g} kWh ÷ {period_months:g} months)"
                if period_months > 1.01
                else ""
            ),
            f"Illustrative plant {plant_kwp:g} kWp × {kwh_per_kwp:g} units/kWp "
            f"→ {estimated_generation:g} kWh estimated generation",
            f"Offset applied to your bill: {solar_monthly:g} kWh"
            + (
                f"; surplus {surplus_kwh:g} kWh not charged in this month's VNM estimate"
                if surplus_kwh > 0
                else ""
            ),
            f"Illustrative VNM energy rate ₹{rate}/kWh (pre-GST) + {gst_pct:g}% GST "
            f"(charged on offset units only in this estimate)",
            "Remaining BESCOM charges use your bill's fixed charge and scale variable "
            "lines for residual grid kWh",
            "Annual chart uses illustrative seasonal factors on the monthly baseline "
            "(not historical meter data)",
        ],
    )

    assumptions = [
        rule.user_messages.get("individual_banner", ""),
        scenario_label + ".",
        f"1 kWp ≈ {kwh_per_kwp:g} units/month (illustrative planning yield).",
        f"Illustrative commercial rate: ₹{rate}/kWh + {gst_pct:g}% GST "
        f"(config — not an official {rule.provider_name} tariff).",
        f"Average monthly consumption: {monthly_baseline:g} kWh.",
        rule.user_messages.get("no_subsidy", ""),
    ]
    if surplus_note:
        assumptions.insert(1, surplus_note)
    if prefill.period_consumption_note:
        assumptions.insert(1, prefill.period_consumption_note)
    if gj_note:
        assumptions.insert(1, gj_note)
    assumptions = [a for a in assumptions if a and str(a).strip()]

    disclaimer = rule.user_messages.get(
        "disclaimer_short",
        "Estimate only. Actual VNM savings depend on the provider's commercial rate, "
        "project generation, customer allocation and applicable BESCOM/KERC charges.",
    )

    return VNMComparisonView(
        provider=rule.provider_name,
        provider_website=rule.provider_website,
        sanctioned_load_kw=sanctioned,
        billing_period=prefill.billing_period,
        period_units_kwh=period_units,
        monthly_units=monthly_baseline,
        billing_period_months=period_months,
        is_multi_month_period=prefill.is_multi_month_period,
        period_consumption_note=prefill.period_consumption_note,
        current_bill_total_inr=monthly_current,
        expected_vnm_solar_credit_kwh=(
            round(solar_monthly * period_months, 2) if using_quote else None
        ),
        needs_expected_credit=False,
        credit_input_prompt=rule.user_messages.get("credit_input_prompt"),
        scenario_label=scenario_label,
        solar_kwh_credited=solar_monthly,
        residual_grid_kwh=residual_monthly,
        estimated_generation_kwh=estimated_generation,
        surplus_kwh=surplus_kwh,
        illustrative_coverage_fraction=round(coverage, 4),
        coverage_source=coverage_source,
        illustrative_plant_kwp=plant_kwp,
        monthly_kwh_per_kwp=kwh_per_kwp,
        plant_slider_min_kwp=min_kwp,
        plant_slider_max_kwp=max_kwp,
        plant_slider_step_kwp=step_kwp,
        default_plant_kwp=default_kwp,
        surplus_note=surplus_note,
        illustrative_rate_inr_per_kwh=rate,
        gst_percent=gst_pct,
        vnm_energy_cost_inr=vnm_month["vnm_energy"],
        vnm_gst_inr=vnm_month["vnm_gst"],
        vnm_service_total_inr=vnm_service,
        residual_bescom_charges_inr=residual_bundle,
        has_gruha_jyothi=has_gj,
        gruha_jyothi_note=gj_note,
        period_difference_inr=monthly_diff,
        monthly_difference_inr=monthly_diff,
        annual_difference_inr=annual_diff,
        is_vnm_cheaper=is_cheaper,
        period_saving_inr=monthly_saving,
        period_increase_inr=monthly_increase,
        monthly_saving_inr=monthly_saving,
        monthly_increase_inr=monthly_increase,
        annual_saving_inr=annual_saving,
        annual_increase_inr=annual_increase,
        current_bill=current,
        vnm_bill=vnm_scenario,
        calculation_detail_lines=detail_lines,
        monthly_chart=chart,
        methodology=methodology,
        cta_primary=rule.user_messages.get("cta_primary", "Get your VNM proposal"),
        cta_secondary=rule.user_messages.get("cta_secondary", "Talk to Integrum"),
        cta_url=(
            rule.user_messages.get("cta_url")
            or getattr(rule, "provider_contact_url", None)
            or "https://integrumenergy.in/contact/"
        ),
        assumptions=assumptions,
        disclaimer=disclaimer,
    )


def _default_plant_kwp(
    monthly_baseline: float,
    kwh_per_kwp: float,
    min_kwp: float,
    max_kwp: float,
    step_kwp: float,
) -> float:
    """Size plant upward to cover ~100% of monthly consumption."""
    if monthly_baseline <= 0 or kwh_per_kwp <= 0:
        return min_kwp
    raw = monthly_baseline / kwh_per_kwp
    return _clamp_plant(raw, min_kwp, max_kwp, step_kwp, round_up=True)


def _clamp_plant(
    value: float,
    min_kwp: float,
    max_kwp: float,
    step_kwp: float,
    *,
    round_up: bool = False,
) -> float:
    step = step_kwp if step_kwp > 0 else 0.5
    if round_up:
        steps = math.ceil(value / step - 1e-9)
    else:
        steps = round(value / step)
    snapped = max(min_kwp, min(max_kwp, steps * step))
    # Avoid float noise (1.0000000002)
    return round(snapped, 2)


def _illustrative_rate(rule: IntegrumVNMRule) -> float:
    scenario = rule.individual_scenario
    if scenario.get("integrum_inr_per_kwh") is not None:
        return float(scenario["integrum_inr_per_kwh"])
    return float(rule.subscription.get("inr_per_kwh", 3.0))


def _start_month(prefill: BillSolarPrefill) -> int:
    if prefill.as_of:
        return int(prefill.as_of.month)
    return 1


def _field_amount(bill: CanonicalElectricityBill, attr: str) -> float | None:
    field = getattr(bill, attr)
    if field.parse_status == ParseStatus.OK and field.value is not None:
        return float(field.value)
    return None


def _subsidy_amount(bill: CanonicalElectricityBill) -> float:
    subsidy = bill.subsidy
    if subsidy.parse_status == ParseStatus.OK and subsidy.value:
        return abs(float(subsidy.value))
    return 0.0


def _looks_gruha_jyothi(
    bill: CanonicalElectricityBill, total: float, units: float
) -> bool:
    if _subsidy_amount(bill) > 0:
        return True
    # Heavily subsidised domestic bills often land near zero payable.
    return units > 0 and total >= 0 and total < 150


def _qty_rate_detail(units: float, amount: float) -> str | None:
    if units <= 0:
        return None
    return f"{units:g} × ₹{amount / units:.2f}/kWh"


def _monthlyize_scenario(
    scenario: BillScenario, period_months: float, monthly_baseline: float
) -> BillScenario:
    """Convert a multi-month period bill into monthly-average display amounts."""
    months = max(1.0, period_months)
    lines: list[BillLineItem] = []
    for line in scenario.lines:
        if line.code == "CONSUMPTION":
            lines.append(
                BillLineItem(
                    code=line.code,
                    label=line.label,
                    amount=0,
                    detail=f"Average monthly consumption: {monthly_baseline:g} kWh",
                )
            )
            continue
        lines.append(
            BillLineItem(
                code=line.code,
                label=line.label,
                amount=round(line.amount / months, 2),
                detail=(
                    f"{line.detail} · monthly avg" if line.detail else "Monthly average"
                ),
            )
        )
    notes = list(scenario.notes)
    notes.append(
        f"Amounts shown as monthly averages from a {months:g}-month billing period."
    )
    return BillScenario(
        title=scenario.title,
        subtitle=(
            f"Average monthly · {monthly_baseline:g} kWh/month · "
            f"from {months:g}-month bill"
        ),
        lines=lines,
        total=round(scenario.total / months, 2),
        units_kwh=monthly_baseline,
        notes=notes,
    )


def _current_bill_scenario(
    bill: CanonicalElectricityBill,
    prefill: BillSolarPrefill,
    period_units: float,
    monthly_baseline: float,
) -> BillScenario:
    lines: list[BillLineItem] = [
        BillLineItem(
            code="CONSUMPTION",
            label="Your consumption",
            amount=0,
            detail=(
                f"{period_units:g} kWh for billing period "
                f"(~{monthly_baseline:g} kWh/month average)"
                if prefill.is_multi_month_period
                else f"{monthly_baseline:g} kWh"
            ),
        )
    ]
    energy = _field_amount(bill, "energy_charge")
    fixed = _field_amount(bill, "fixed_charge")
    fppca = _field_amount(bill, "fppca")
    other = _field_amount(bill, "other_charges")
    tax = _field_amount(bill, "electricity_tax")
    subsidy = _subsidy_amount(bill)

    if energy is not None:
        lines.append(
            BillLineItem(
                code="ENERGY",
                label="Energy charges",
                amount=energy,
                detail=_qty_rate_detail(period_units, energy),
            )
        )
    if fixed is not None:
        lines.append(
            BillLineItem(
                code="FIXED",
                label="Fixed charges",
                amount=fixed,
                detail=f"{prefill.sanctioned_load_kw:g} kW sanctioned load (from bill)",
            )
        )
    if fppca:
        lines.append(
            BillLineItem(
                code="FPPCA",
                label="FPPCA",
                amount=fppca,
                detail=_qty_rate_detail(period_units, fppca),
            )
        )
    if other:
        lines.append(
            BillLineItem(
                code="OTHER",
                label="P & G / other charges",
                amount=other,
                detail=None,
            )
        )
    if tax:
        lines.append(
            BillLineItem(
                code="TAX",
                label="Electricity tax",
                amount=tax,
                detail=None,
            )
        )
    if subsidy:
        lines.append(
            BillLineItem(
                code="SUBSIDY",
                label="Gruha Jyothi / subsidy",
                amount=-subsidy,
                detail="Reduction on your printed bill",
            )
        )

    total = (
        float(bill.total_amount.value)
        if bill.total_amount.value is not None
        else round(sum(l.amount for l in lines if l.code != "CONSUMPTION"), 2)
    )

    notes = ["Charge breakdown from your confirmed uploaded bill."]
    if prefill.period_consumption_note:
        notes.append(prefill.period_consumption_note)
    if prefill.is_multi_month_period:
        notes.append(
            f"Average monthly consumption: {monthly_baseline:g} kWh "
            f"(used as the VNM sales baseline)."
        )

    return BillScenario(
        title="My Current BESCOM Bill",
        subtitle=(
            f"{monthly_baseline:g} kWh/month average · {prefill.sanctioned_load_kw:g} kW "
            f"sanctioned load · Period: {prefill.billing_period or '—'}"
        ),
        lines=lines,
        total=round(total, 2),
        units_kwh=monthly_baseline,
        notes=notes,
    )


def _scale_residual_bescom_with_period(
    bill: CanonicalElectricityBill,
    *,
    period_units: float,
    monthly_baseline: float,
    residual_monthly: float,
) -> tuple[list[BillLineItem], float, list[BillLineItem]]:
    fixed = _field_amount(bill, "fixed_charge") or 0.0
    detail_lines: list[BillLineItem] = []
    lines: list[BillLineItem] = []

    lines.append(
        BillLineItem(
            code="BESCOM_FIXED",
            label="Fixed charges",
            amount=round(fixed, 2),
            detail=f"Same as your bill — {monthly_baseline:g} kWh baseline does not change load",
        )
    )
    detail_lines.append(lines[-1])

    if period_units <= 0:
        return lines, round(fixed, 2), detail_lines

    residual_period_equiv = residual_monthly  # charge at monthly residual using period rates
    # Rate from period bill: amount/period_units; apply to residual_monthly kWh.
    variable_total = 0.0
    for attr, code, label in _VARIABLE_CHARGE_FIELDS:
        amount = _field_amount(bill, attr)
        if amount is None or amount == 0:
            continue
        rate = amount / period_units
        scaled = round(rate * residual_monthly, 2)
        variable_total += scaled
        item = BillLineItem(
            code=f"BESCOM_{code}",
            label=label,
            amount=scaled,
            detail=_qty_rate_detail(residual_monthly, scaled)
            or f"{residual_monthly:g} × ₹{rate:.2f}/kWh",
        )
        detail_lines.append(item)

    tax = _field_amount(bill, "electricity_tax")
    energy = _field_amount(bill, "energy_charge") or 0.0
    pre_tax_period = energy + fixed
    for attr, _, _ in _VARIABLE_CHARGE_FIELDS[1:]:
        a = _field_amount(bill, attr)
        if a:
            pre_tax_period += a
    scaled_tax = 0.0
    if tax and pre_tax_period > 0:
        # Always keep tax attributable to fixed charges (load-based, not wiped by solar).
        tax_fixed = round(tax * (fixed / pre_tax_period), 2) if fixed > 0 else 0.0
        # Variable portion of tax scales with residual grid kWh.
        tax_variable_full = round(tax - tax_fixed, 2)
        tax_variable_residual = 0.0
        if residual_monthly > 0 and period_units > 0:
            tax_variable_residual = round(
                tax_variable_full * (residual_monthly / period_units), 2
            )
        scaled_tax = round(tax_fixed + tax_variable_residual, 2)
        detail_parts = [f"fixed share ₹{tax_fixed:g}"]
        if tax_variable_residual > 0:
            detail_parts.append(f"residual grid ₹{tax_variable_residual:g}")
        detail_lines.append(
            BillLineItem(
                code="BESCOM_TAX",
                label="Electricity tax",
                amount=scaled_tax,
                detail=" + ".join(detail_parts),
            )
        )
        variable_total += scaled_tax

    residual_total = round(fixed + variable_total, 2)
    lines.append(
        BillLineItem(
            code="RESIDUAL_BESCOM",
            label="Remaining BESCOM charges",
            amount=residual_total,
            detail="Fixed + applicable residual grid charges (see calculation)",
        )
    )
    return lines, residual_total, detail_lines


def _vnm_month_estimate(
    *,
    bill: CanonicalElectricityBill,
    monthly_baseline: float,
    residual_monthly: float,
    solar_monthly: float,
    estimated_generation: float,
    surplus_kwh: float,
    rate: float,
    gst_pct: float,
    provider_name: str,
    current_total: float,
) -> dict:
    # Recover period_units from bill units field
    period_units = (
        float(bill.units_consumed.value)
        if bill.units_consumed.value is not None
        else monthly_baseline
    )
    if period_units <= 0:
        period_units = monthly_baseline if monthly_baseline > 0 else 1.0

    _, residual_bescom, detail_lines = _scale_residual_bescom_with_period(
        bill,
        period_units=period_units,
        monthly_baseline=monthly_baseline,
        residual_monthly=residual_monthly,
    )

    # Sales monthly model: current_total is the confirmed bill total for the period.
    # Convert BESCOM residual to a monthly figure when period spans multiple months.
    months = period_units / monthly_baseline if monthly_baseline > 0 else 1.0
    months = max(1.0, months)
    # Fixed on bill is often for the period; for monthly sales compare, use
    # current_total as the "month" when months≈1; when multi-month, baseline
    # monthly BESCOM ≈ current_total / months.
    #
    # Residual_bescom computed with period rates * residual_monthly already yields
    # a monthly-ish variable + full-period fixed. Split fixed to monthly:
    fixed = _field_amount(bill, "fixed_charge") or 0.0
    fixed_monthly = round(fixed / months, 2)
    # Rebuild residual monthly = fixed_monthly + variable (already monthly from rates)
    variable_only = round(residual_bescom - fixed, 2)
    residual_monthly_inr = round(fixed_monthly + max(0.0, variable_only), 2)

    vnm_energy = round(solar_monthly * rate, 2)
    vnm_gst = round(vnm_energy * gst_pct / 100.0, 2)
    vnm_service = round(vnm_energy + vnm_gst, 2)
    total = round(residual_monthly_inr + vnm_service, 2)

    lines = [
        BillLineItem(
            code="SOLAR_GEN",
            label="Estimated solar generation",
            amount=0,
            detail=f"{estimated_generation:g} kWh/month (plant size × units/kWp)",
        ),
        BillLineItem(
            code="SOLAR_CREDIT",
            label="Offset applied to your bill",
            amount=0,
            detail=f"{solar_monthly:g} kWh (min of generation and your consumption)",
        ),
        BillLineItem(
            code="SURPLUS",
            label="Extra solar (surplus)",
            amount=0,
            detail=(
                f"{surplus_kwh:g} kWh — banks monthly; yearly settlement only"
                if surplus_kwh > 0
                else "None this month"
            ),
        ),
        BillLineItem(
            code="GRID_UNITS",
            label="Remaining grid usage",
            amount=0,
            detail=f"{residual_monthly:g} kWh",
        ),
        BillLineItem(
            code="INTEGRUM_SUB",
            label="VNM solar service",
            amount=vnm_service,
            detail=(
                f"{solar_monthly:g} × ₹{rate}/kWh + {gst_pct:g}% GST "
                f"= ₹{vnm_energy:g} + ₹{vnm_gst:g} (charged on offset only)"
            ),
        ),
        BillLineItem(
            code="BESCOM_FIXED",
            label="Fixed charges",
            amount=fixed_monthly,
            detail=f"Same as your bill (monthly share) — load unchanged",
        ),
    ]
    # Add residual variable BESCOM lines (energy/FPPCA/other/tax) for side-by-side compare
    for d in detail_lines:
        if d.code == "BESCOM_FIXED":
            continue
        if d.amount == 0:
            continue
        lines.append(d)

    # Detail expansion: show formulas
    detail = [
        BillLineItem(
            code="D_SOLAR",
            label="Solar energy",
            amount=vnm_energy,
            detail=f"{solar_monthly:g} × ₹{rate} = ₹{vnm_energy:g}",
        ),
        BillLineItem(
            code="D_GST",
            label=f"GST {gst_pct:g}%",
            amount=vnm_gst,
            detail=f"₹{vnm_gst:g}",
        ),
        BillLineItem(
            code="D_SERVICE",
            label="VNM solar service",
            amount=vnm_service,
            detail=f"₹{vnm_service:g}",
        ),
        BillLineItem(
            code="D_FIXED",
            label="Fixed charges (monthly share)",
            amount=fixed_monthly,
            detail=f"₹{fixed:g} on bill ÷ {months:g} ≈ ₹{fixed_monthly:g}",
        ),
        *[d for d in detail_lines if d.code != "BESCOM_FIXED"],
        BillLineItem(
            code="D_RESIDUAL",
            label="Remaining BESCOM total",
            amount=residual_monthly_inr,
            detail=f"₹{residual_monthly_inr:g}",
        ),
    ]

    return {
        "total": total,
        "residual_bescom": residual_monthly_inr,
        "vnm_energy": vnm_energy,
        "vnm_gst": vnm_gst,
        "vnm_service_total": vnm_service,
        "lines": lines,
        "detail_lines": detail,
        "fixed_monthly": fixed_monthly,
        "variable_only": variable_only,
        "months": months,
    }


def _seasonal_chart(
    *,
    rule: IntegrumVNMRule,
    bill: CanonicalElectricityBill,
    monthly_baseline: float,
    plant_kwp: float,
    kwh_per_kwp: float,
    solar_monthly_fixed: float | None,
    rate: float,
    gst_pct: float,
    provider_name: str,
    current_total: float,
    start_month: int,
    anchor_bescom_inr: float,
    anchor_vnm_inr: float,
) -> list[MonthlyBillEstimate]:
    """
    12-month estimate starting at the bill month.

    Seasonal YAML factors are normalised so the bill month is always 1.0
    (the uploaded bill already is that month's consumption). Month 1 of the
    chart is pinned to the same BESCOM/VNM totals as the comparison table.
    """
    raw = rule.seasonal_model or {}
    factors = raw.get("factors_by_month") or {}
    factor_map = {int(k): float(v) for k, v in factors.items()}
    bill_month_factor = float(factor_map.get(start_month, 1.0)) or 1.0

    period_units = (
        float(bill.units_consumed.value)
        if bill.units_consumed.value is not None
        else monthly_baseline
    )
    months_span = period_units / monthly_baseline if monthly_baseline > 0 else 1.0
    months_span = max(1.0, months_span)
    monthly_bescom_base = round(float(anchor_bescom_inr), 2)
    plant_monthly_gen = round(plant_kwp * kwh_per_kwp, 2)

    # Fixed + tax-on-fixed style residual floor from the detailed VNM month total:
    # when residual grid is 0, VNM total = fixed-like BESCOM remainder + VNM service.
    # Derive a stable "non-energy residual" from the anchor for other months.
    fixed = _field_amount(bill, "fixed_charge") or 0.0
    fixed_m = round(fixed / months_span, 2)

    chart: list[MonthlyBillEstimate] = []
    for i in range(12):
        month = ((start_month - 1 + i) % 12) + 1
        calendar_factor = float(factor_map.get(month, 1.0))
        # Relative to bill month so uploaded month stays at baseline (1.0).
        relative_factor = calendar_factor / bill_month_factor

        if i == 0:
            # Exact match with the side-by-side comparison totals.
            chart.append(
                MonthlyBillEstimate(
                    month_index=1,
                    month_label=f"{_MONTH_NAMES[month]}",
                    calendar_month=month,
                    seasonal_factor=1.0,
                    estimated_units_kwh=monthly_baseline,
                    estimated_bescom_bill_inr=round(anchor_bescom_inr, 2),
                    estimated_vnm_bill_inr=round(anchor_vnm_inr, 2),
                    estimated_saving_inr=round(anchor_bescom_inr - anchor_vnm_inr, 2),
                )
            )
            continue

        est_units = round(monthly_baseline * relative_factor, 2)
        if monthly_baseline > 0:
            variable_share = max(0.0, monthly_bescom_base - fixed_m)
            bescom_est = round(
                fixed_m + variable_share * (est_units / monthly_baseline), 2
            )
        else:
            bescom_est = monthly_bescom_base

        if solar_monthly_fixed is not None:
            solar = round(min(est_units, solar_monthly_fixed), 2)
        else:
            solar = round(min(est_units, plant_monthly_gen), 2)
        residual = round(max(0.0, est_units - solar), 2)

        vnm_energy = round(solar * rate, 2)
        vnm_gst = round(vnm_energy * gst_pct / 100.0, 2)
        vnm_service = vnm_energy + vnm_gst

        if monthly_baseline > 0:
            variable_share = max(0.0, monthly_bescom_base - fixed_m)
            residual_var = round(variable_share * (residual / monthly_baseline), 2)
        else:
            residual_var = 0.0
        # Keep fixed charges; approximate tax-on-fixed from anchor when fully offset.
        tax_fixed_approx = 0.0
        if plant_monthly_gen >= monthly_baseline - 1e-6 or (
            solar_monthly_fixed is not None and solar_monthly_fixed >= monthly_baseline
        ):
            bill_service = monthly_baseline * rate * (1 + gst_pct / 100.0)
            tax_fixed_approx = round(max(0.0, anchor_vnm_inr - fixed_m - bill_service), 2)
        residual_bescom = round(fixed_m + tax_fixed_approx + residual_var, 2)
        vnm_est = round(residual_bescom + vnm_service, 2)

        chart.append(
            MonthlyBillEstimate(
                month_index=i + 1,
                month_label=f"{_MONTH_NAMES[month]}",
                calendar_month=month,
                seasonal_factor=round(relative_factor, 4),
                estimated_units_kwh=est_units,
                estimated_bescom_bill_inr=bescom_est,
                estimated_vnm_bill_inr=vnm_est,
                estimated_saving_inr=round(bescom_est - vnm_est, 2),
            )
        )
    return chart
