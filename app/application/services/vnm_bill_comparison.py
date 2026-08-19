"""Compare uploaded BESCOM bill vs Integrum VNM — individual consumer only."""

from __future__ import annotations

from app.domain.engines.tariff import TariffEngine
from app.domain.models.solar_options import BillSolarPrefill
from app.domain.models.validated_bill import BillValidationResult, CanonicalElectricityBill, ParseStatus
from app.domain.models.vnm_comparison import (
    BillLineItem,
    BillScenario,
    VNMComparisonView,
)
from app.infrastructure.persistence.repository import StoredBillAnalysis
from app.infrastructure.rules.integrum_vnm_rules import IntegrumVNMRule, get_default_integrum_vnm_rule

# BESCOM line codes scaled by remaining grid kWh; fixed charge stays as on bill.
_VARIABLE_CHARGE_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("energy_charge", "ENERGY", "Energy charges"),
    ("fppca", "FPPCA", "FPPCA"),
    ("other_charges", "OTHER", "P & G / other charges"),
)


_CREDIT_INPUT_PROMPT = (
    "To estimate your VNM bill, enter the expected solar credit provided by your "
    "VNM provider or society for this billing period."
)


def build_vnm_comparison(
    stored: StoredBillAnalysis,
    prefill: BillSolarPrefill,
    *,
    expected_vnm_solar_credit_kwh: float | None = None,
    provider_rule: IntegrumVNMRule | None = None,
    tariff_engine: TariffEngine | None = None,
) -> VNMComparisonView:
    rule = provider_rule or get_default_integrum_vnm_rule()
    tariff = tariff_engine or TariffEngine()
    validation = BillValidationResult.model_validate(stored.validation)
    bill = validation.bill

    period_units = prefill.period_units_kwh
    monthly_equiv = prefill.monthly_units
    period_months = prefill.billing_period_months
    sanctioned_load_kw = prefill.sanctioned_load_kw
    credit_prompt = rule.user_messages.get("credit_input_prompt", _CREDIT_INPUT_PROMPT)

    current = _current_bill_scenario(bill, prefill, tariff)

    if expected_vnm_solar_credit_kwh is None:
        return _comparison_without_credit(
            rule=rule,
            prefill=prefill,
            current=current,
            period_units=period_units,
            monthly_equiv=monthly_equiv,
            period_months=period_months,
            sanctioned_load_kw=sanctioned_load_kw,
            credit_prompt=credit_prompt,
        )

    solar_credit = round(min(period_units, max(0.0, expected_vnm_solar_credit_kwh)), 2)
    residual_units = round(max(0.0, period_units - solar_credit), 2)
    scenario_label = "Expected / scenario VNM solar credit (from provider or society)"

    sub_rate = _integrum_scenario_rate(rule)
    vnm = _vnm_bill_scenario(
        bill=bill,
        prefill=prefill,
        tariff=tariff,
        rule=rule,
        residual_units=residual_units,
        solar_credit=solar_credit,
        period_units=period_units,
        monthly_equiv=monthly_equiv,
        sanctioned_load_kw=sanctioned_load_kw,
        integrum_rate=sub_rate,
    )

    period_difference = round(current.total - vnm.total, 2)
    is_cheaper = period_difference > 0
    period_saving = round(max(0.0, period_difference), 2)
    period_increase = round(max(0.0, -period_difference), 2)
    monthly_factor = 1.0 / period_months if period_months > 0 else 1.0
    monthly_difference = round(period_difference * monthly_factor, 2)
    monthly_saving = round(period_saving * monthly_factor, 2)
    monthly_increase = round(period_increase * monthly_factor, 2)
    annual_factor = 12.0 / period_months if period_months > 0 else 12.0
    annual_difference = round(period_difference * annual_factor, 2)
    annual_saving = round(period_saving * annual_factor, 2)
    annual_increase = round(period_increase * annual_factor, 2)

    gst = float(rule.subscription.get("gst_percent", 18.0))
    market_low = rule.subscription.get("market_low_inr_per_kwh")
    market_high = rule.subscription.get("market_high_inr_per_kwh")
    rate_band = (
        f"₹{market_low}–{market_high}/kWh"
        if market_low and market_high
        else f"₹{sub_rate}/kWh"
    )
    period_label = (
        f"{period_units:g} kWh for this billing period"
        if prefill.is_multi_month_period
        else f"{period_units:g} kWh"
    )
    assumptions = [
        rule.user_messages.get("individual_banner", ""),
        f"Expected VNM solar credit: {solar_credit:g} kWh (user-provided scenario).",
        "BESCOM side: fixed charge stays the same as your bill; energy, FPPCA and P&G scale "
        f"only for remaining grid kWh ({residual_units:g} of {period_label}).",
        f"Integrum VNM service: illustrative ₹{sub_rate}/kWh on expected solar credit "
        f"+ {gst:g}% GST (market band {rate_band} — verify with Integrum).",
        "Gruha Jyothi / bill subsidies on your current bill are not included in the VNM estimate.",
        rule.user_messages.get("no_subsidy", ""),
        f"Source: {rule.source}",
    ]
    if prefill.period_consumption_note:
        assumptions.insert(1, prefill.period_consumption_note)
    assumptions = [a for a in assumptions if a.strip()]

    return VNMComparisonView(
        provider=rule.provider_name,
        provider_website=rule.provider_website,
        sanctioned_load_kw=sanctioned_load_kw,
        billing_period=prefill.billing_period,
        period_units_kwh=period_units,
        monthly_units=monthly_equiv,
        billing_period_months=period_months,
        is_multi_month_period=prefill.is_multi_month_period,
        period_consumption_note=prefill.period_consumption_note,
        current_bill_total_inr=current.total,
        expected_vnm_solar_credit_kwh=solar_credit,
        needs_expected_credit=False,
        credit_input_prompt=None,
        scenario_label=scenario_label,
        solar_kwh_credited=solar_credit,
        residual_grid_kwh=residual_units,
        monthly_difference_inr=monthly_difference,
        annual_difference_inr=annual_difference,
        is_vnm_cheaper=is_cheaper,
        period_difference_inr=period_difference,
        period_saving_inr=period_saving,
        period_increase_inr=period_increase,
        monthly_saving_inr=monthly_saving,
        monthly_increase_inr=monthly_increase,
        annual_saving_inr=annual_saving,
        annual_increase_inr=annual_increase,
        current_bill=current,
        vnm_bill=vnm,
        assumptions=assumptions,
        disclaimer=(
            f"Preliminary individual VNM comparison with {rule.provider_name} service assumptions. "
            f"Expected solar credit is a user-provided scenario — not a guaranteed allocation. "
            f"Not a BESCOM approval. Rule {rule.rule_version} — {rule.verification_status}."
        ),
    )


def _comparison_without_credit(
    *,
    rule: IntegrumVNMRule,
    prefill: BillSolarPrefill,
    current: BillScenario,
    period_units: float,
    monthly_equiv: float,
    period_months: float,
    sanctioned_load_kw: float,
    credit_prompt: str,
) -> VNMComparisonView:
    assumptions = [
        rule.user_messages.get("individual_banner", ""),
        credit_prompt,
    ]
    if prefill.period_consumption_note:
        assumptions.append(prefill.period_consumption_note)
    assumptions = [a for a in assumptions if a.strip()]

    placeholder_vnm = BillScenario(
        title="VNM Scenario",
        subtitle="Enter expected VNM solar credit to estimate",
        lines=[],
        total=0,
        units_kwh=period_units,
        notes=[credit_prompt],
    )

    return VNMComparisonView(
        provider=rule.provider_name,
        provider_website=rule.provider_website,
        sanctioned_load_kw=sanctioned_load_kw,
        billing_period=prefill.billing_period,
        period_units_kwh=period_units,
        monthly_units=monthly_equiv,
        billing_period_months=period_months,
        is_multi_month_period=prefill.is_multi_month_period,
        period_consumption_note=prefill.period_consumption_note,
        current_bill_total_inr=current.total,
        expected_vnm_solar_credit_kwh=None,
        needs_expected_credit=True,
        credit_input_prompt=credit_prompt,
        scenario_label="",
        solar_kwh_credited=0,
        residual_grid_kwh=0,
        monthly_difference_inr=0,
        annual_difference_inr=0,
        is_vnm_cheaper=False,
        period_difference_inr=0,
        period_saving_inr=0,
        period_increase_inr=0,
        monthly_saving_inr=0,
        monthly_increase_inr=0,
        annual_saving_inr=0,
        annual_increase_inr=0,
        current_bill=current,
        vnm_bill=placeholder_vnm,
        assumptions=assumptions,
        disclaimer=(
            f"Enter expected VNM solar credit from your provider to compare with "
            f"{rule.provider_name}. BESCOM bill data is from your confirmed upload."
        ),
    )


def _integrum_scenario_rate(rule: IntegrumVNMRule) -> float:
    scenario = rule.individual_scenario
    if scenario.get("integrum_inr_per_kwh") is not None:
        return float(scenario["integrum_inr_per_kwh"])
    low = rule.subscription.get("market_low_inr_per_kwh")
    if low is not None:
        return float(low)
    return float(rule.subscription.get("inr_per_kwh", 3.0))


def _field_amount(bill: CanonicalElectricityBill, attr: str) -> float | None:
    field = getattr(bill, attr)
    if field.parse_status == ParseStatus.OK and field.value is not None:
        return float(field.value)
    return None


def _units_subtitle(prefill: BillSolarPrefill, period_units: float) -> str:
    period = prefill.billing_period or "—"
    base = (
        f"{period_units:g} kWh for billing period · "
        f"{prefill.sanctioned_load_kw:g} kW sanctioned load · "
        f"Period: {period}"
    )
    if prefill.is_multi_month_period:
        return (
            f"{base} (~{prefill.monthly_units:g} kWh/month average over "
            f"~{prefill.billing_period_months:g} months)"
        )
    return base


def _current_bill_scenario(
    bill: CanonicalElectricityBill,
    prefill: BillSolarPrefill,
    tariff: TariffEngine,
) -> BillScenario:
    lines: list[BillLineItem] = []
    notes: list[str] = []
    period_units = prefill.period_units_kwh

    extracted = _extracted_lines(bill, period_units)
    if extracted:
        lines = extracted
        notes.append("Charge breakdown from your confirmed uploaded bill (amounts you paid).")
        components_total = sum(l.amount for l in lines)
        subsidy_amt = _subsidy_amount(bill)
        printed = _printed_total(bill, components_total, subsidy_amt)
        if subsidy_amt and abs(components_total - printed) > 2.0:
            notes.append(
                f"Net payable on your bill: ₹{printed:,.2f}. "
                f"Gruha Jyothi subsidy (−₹{subsidy_amt:,.2f}) is shown separately. "
                "If line items do not add up, verify Total Amount matches the printed "
                "Net Payable / Current Demand on the bill."
            )
        total = printed
    else:
        calc = tariff.calculate(
            discom=prefill.discom,
            category=prefill.category,
            as_of=prefill.as_of,
            units=period_units,
            sanctioned_load_kw=prefill.sanctioned_load_kw,
            tariff_code=prefill.tariff_code,
        )
        for line in calc.lines:
            lines.append(
                BillLineItem(
                    code=line.code,
                    label=line.description,
                    amount=line.amount,
                    detail=line.detail,
                )
            )
        total = float(calc.estimated_total or 0)
        notes.append("Estimated from BESCOM tariff rules (bill line items not fully extracted).")

    if prefill.period_consumption_note:
        notes.append(prefill.period_consumption_note)

    return BillScenario(
        title="My Current BESCOM Bill",
        subtitle=_units_subtitle(prefill, period_units),
        lines=lines,
        total=round(total, 2),
        units_kwh=period_units,
        notes=notes,
    )


def _subsidy_amount(bill: CanonicalElectricityBill) -> float:
    subsidy = bill.subsidy
    if subsidy.parse_status == ParseStatus.OK and subsidy.value:
        return abs(float(subsidy.value))
    return 0.0


def _printed_total(
    bill: CanonicalElectricityBill,
    components_total: float,
    subsidy_amt: float,
) -> float:
    if bill.total_amount.value is not None:
        return float(bill.total_amount.value)
    return components_total - subsidy_amt


def _extracted_lines(bill: CanonicalElectricityBill, units: float) -> list[BillLineItem]:
    mapping = [
        ("ENERGY", "Energy charges", bill.energy_charge, lambda v: f"{units:g} kWh for period"),
        ("FIXED", "Fixed charges", bill.fixed_charge, None),
        ("FPPCA", "FPPCA", bill.fppca, lambda v: f"{units:g} kWh × ₹{v/units:.2f}/kWh" if units > 0 and v else None),
        ("OTHER", "P & G / other charges", bill.other_charges, None),
        ("TAX", "Electricity tax", bill.electricity_tax, None),
        ("ARREARS", "Arrears", bill.arrears, None),
        ("LATE", "Late payment", bill.late_payment_charge, None),
    ]
    lines: list[BillLineItem] = []
    for code, label, field, detail_fn in mapping:
        if field.parse_status == ParseStatus.OK and field.value is not None:
            val = float(field.value)
            if code in ("ARREARS", "LATE") and val == 0:
                continue
            detail = detail_fn(val) if detail_fn else None
            lines.append(BillLineItem(code=code, label=label, amount=val, detail=detail))

    subsidy = bill.subsidy
    if subsidy.parse_status == ParseStatus.OK and subsidy.value:
        val = abs(float(subsidy.value))
        if val > 0:
            lines.append(
                BillLineItem(
                    code="SUBSIDY",
                    label="Gruha Jyothi / subsidy",
                    amount=-val,
                    detail="Reduction on your printed bill",
                )
            )
    return lines


def _vnm_bescom_from_bill(
    bill: CanonicalElectricityBill,
    *,
    period_units: float,
    residual_units: float,
) -> tuple[list[BillLineItem], float] | None:
    """Scale variable BESCOM charges from the bill; keep fixed charge unchanged."""
    energy = _field_amount(bill, "energy_charge")
    fixed = _field_amount(bill, "fixed_charge")
    if energy is None or fixed is None or period_units <= 0:
        return None

    ratio = residual_units / period_units
    lines: list[BillLineItem] = []

    scaled_energy = round(energy * ratio, 2)
    lines.append(
        BillLineItem(
            code="BESCOM_ENERGY",
            label="Energy charges (grid only)",
            amount=scaled_energy,
            detail=f"{residual_units:g} kWh — scaled from your bill",
        )
    )
    lines.append(
        BillLineItem(
            code="BESCOM_FIXED",
            label="Fixed charges",
            amount=round(fixed, 2),
            detail="Same as your bill — connection fixed charge unchanged",
        )
    )

    variable_pre_tax = energy
    scaled_variable = scaled_energy
    for attr, code, label in _VARIABLE_CHARGE_FIELDS[1:]:
        amount = _field_amount(bill, attr)
        if amount is None or amount == 0:
            continue
        scaled = round(amount * ratio, 2)
        variable_pre_tax += amount
        scaled_variable += scaled
        unit_rate = amount / period_units
        lines.append(
            BillLineItem(
                code=f"BESCOM_{code}",
                label=label,
                amount=scaled,
                detail=f"{residual_units:g} kWh × ₹{unit_rate:.2f}/kWh — from your bill",
            )
        )

    tax = _field_amount(bill, "electricity_tax")
    pre_tax_total = variable_pre_tax + fixed
    if tax and pre_tax_total > 0:
        scaled_pre_tax = scaled_variable + fixed
        scaled_tax = round(tax * (scaled_pre_tax / pre_tax_total), 2)
        lines.append(
            BillLineItem(
                code="BESCOM_TAX",
                label="Electricity tax",
                amount=scaled_tax,
                detail="Scaled from your bill for remaining grid usage",
            )
        )

    total = round(sum(l.amount for l in lines), 2)
    return lines, total


def _vnm_bill_scenario(
    *,
    bill: CanonicalElectricityBill,
    prefill: BillSolarPrefill,
    tariff: TariffEngine,
    rule: IntegrumVNMRule,
    residual_units: float,
    solar_credit: float,
    period_units: float,
    monthly_equiv: float,
    sanctioned_load_kw: float,
    integrum_rate: float,
) -> BillScenario:
    gst = float(rule.subscription.get("gst_percent", 18.0))
    integrum_base = solar_credit * integrum_rate
    integrum_gst = integrum_base * gst / 100.0
    integrum_total = integrum_base + integrum_gst

    consumption_detail = (
        f"{period_units:g} kWh for billing period"
        if prefill.is_multi_month_period
        else f"{period_units:g} kWh"
    )
    if prefill.is_multi_month_period:
        consumption_detail += f" (~{monthly_equiv:g} kWh/month average)"

    lines: list[BillLineItem] = [
        BillLineItem(
            code="CONSUMPTION",
            label="Your consumption",
            amount=0,
            detail=consumption_detail,
        ),
        BillLineItem(
            code="SOLAR_CREDIT",
            label="Expected / scenario VNM solar credit",
            amount=0,
            detail=f"{solar_credit:g} kWh — from your VNM provider or society",
        ),
        BillLineItem(
            code="GRID_UNITS",
            label="Remaining grid consumption",
            amount=0,
            detail=f"{residual_units:g} kWh",
        ),
    ]

    bescom_from_bill = _vnm_bescom_from_bill(
        bill, period_units=period_units, residual_units=residual_units
    )
    if bescom_from_bill:
        bescom_lines, bescom_sub = bescom_from_bill
        lines.extend(bescom_lines)
        bescom_note = "BESCOM lines scaled from your bill: fixed unchanged, variable charges on grid kWh only."
    else:
        bescom = tariff.calculate(
            discom=prefill.discom,
            category=prefill.category,
            as_of=prefill.as_of,
            units=residual_units,
            sanctioned_load_kw=sanctioned_load_kw,
            tariff_code=prefill.tariff_code,
        )
        for line in bescom.lines:
            lines.append(
                BillLineItem(
                    code=f"BESCOM_{line.code}",
                    label=line.description,
                    amount=line.amount,
                    detail=f"{line.detail} (tariff estimate — bill lines unavailable)",
                )
            )
        bescom_sub = float(bescom.estimated_total or 0)
        bescom_note = "BESCOM lines estimated from tariff rules (bill breakdown not available)."

    lines.append(
        BillLineItem(
            code="INTEGRUM_SUB",
            label=f"{rule.provider_name} VNM service charge",
            amount=round(integrum_base, 2),
            detail=f"{solar_credit:g} kWh × ₹{integrum_rate}/kWh (illustrative rate)",
        )
    )
    lines.append(
        BillLineItem(
            code="INTEGRUM_GST",
            label="GST on VNM service",
            amount=round(integrum_gst, 2),
            detail=f"{gst:g}% on Integrum service — not a BESCOM charge",
        )
    )
    total = round(bescom_sub + integrum_total, 2)

    return BillScenario(
        title="My Bill With VNM",
        subtitle=(
            f"{period_units:g} kWh consumption · {solar_credit:g} kWh expected credit · "
            f"{residual_units:g} kWh from grid · {sanctioned_load_kw:g} kW sanctioned load"
        ),
        lines=lines,
        total=total,
        units_kwh=period_units,
        notes=[
            bescom_note,
            "Integrum charge is for expected solar kWh credited — separate from BESCOM FPPCA/P&G.",
            "Gruha Jyothi subsidy is not applied on the VNM estimate.",
            "Expected solar credit is a scenario input — not calculated from your bill.",
        ],
    )
