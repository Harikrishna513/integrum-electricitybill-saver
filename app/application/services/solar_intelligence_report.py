"""Build demo-ready Solar Intelligence Reports from engine outputs."""

from __future__ import annotations

import re
from typing import Any

from app.domain.models.solar_options import BillSolarPrefill, SolarOptionCard
from app.domain.models.solar_intelligence_report import (
    ReportMetric,
    ReportSection,
    SolarIntelligenceReport,
)
from app.domain.models.vnm_comparison import VNMComparisonView
from app.infrastructure.rules.solar_rules import get_default_solar_rooftop_rule

# Planning assumptions — documented in report disclaimer.
_TARIFF_ESCALATION = 0.03
_SYSTEM_LIFE_YEARS = 25
_GRID_EMISSION_KG_PER_KWH = 0.71
_CARBON_PRICE_LOW_INR_PER_TONNE = 800.0
_CARBON_PRICE_HIGH_INR_PER_TONNE = 2400.0
_INSTALL_COST_RANGE_FACTOR = 0.20  # ±20% market band around rule capex


def build_solar_intelligence_report(
    option: SolarOptionCard,
    prefill: BillSolarPrefill,
    *,
    address: str | None = None,
    vnm_comparison: VNMComparisonView | None = None,
) -> SolarIntelligenceReport:
    pincode = _extract_pincode(address or prefill.address)
    location_line = _location_line(pincode)
    property_type = "Residential" if prefill.category.upper() == "DOMESTIC" else prefill.category.title()

    if option.option == "vnm" and vnm_comparison is not None:
        return _vnm_integrum_report(vnm_comparison, location_line, property_type)
    if option.option == "individual_solar":
        return _individual_report(option, prefill, location_line, property_type)
    if option.option == "vnm":
        return _group_report(option, prefill, location_line, property_type, title="Virtual Net Metering")
    return _group_report(option, prefill, location_line, property_type, title="Group Net Metering")


def _vnm_integrum_report(
    comparison: VNMComparisonView,
    location_line: str,
    property_type: str,
) -> SolarIntelligenceReport:
    current = comparison.current_bill
    vnm = comparison.vnm_bill
    method = comparison.methodology

    diff_label = (
        "Estimated monthly saving"
        if comparison.is_vnm_cheaper
        else "Estimated monthly increase"
    )
    diff_value = (
        f"Rs {_fmt_inr(comparison.monthly_saving_inr)}/mo"
        if comparison.is_vnm_cheaper
        else f"Rs {_fmt_inr(comparison.monthly_increase_inr)}/mo"
    )

    metrics = [
        ReportMetric(
            label="Average monthly consumption",
            value=f"{comparison.monthly_units:g} kWh",
            detail=comparison.period_consumption_note or comparison.billing_period,
        ),
        ReportMetric(
            label="Illustrative plant size",
            value=(
                f"{comparison.illustrative_plant_kwp:g} kWp "
                f"(~{comparison.monthly_kwh_per_kwp:g} units/kWp)"
            ),
            detail=comparison.scenario_label,
        ),
        ReportMetric(
            label="Illustrative VNM rate",
            value=f"Rs {comparison.illustrative_rate_inr_per_kwh:g}/kWh + {comparison.gst_percent:g}% GST",
            detail="Configurable commercial assumption — not an official tariff",
        ),
        ReportMetric(
            label="Current BESCOM (monthly)",
            value=f"Rs {_fmt_inr(current.total)}",
            detail=None,
        ),
        ReportMetric(
            label="VNM estimate (monthly)",
            value=f"Rs {_fmt_inr(vnm.total)}",
            detail=f"Via {comparison.provider}",
        ),
        ReportMetric(
            label=diff_label,
            value=diff_value,
            detail=f"Rs {_fmt_inr(comparison.annual_saving_inr if comparison.is_vnm_cheaper else comparison.annual_increase_inr)}/yr (seasonal model)",
        ),
    ]
    if comparison.has_gruha_jyothi and comparison.gruha_jyothi_note:
        metrics.insert(
            0,
            ReportMetric(
                label="Gruha Jyothi",
                value="Limited additional savings likely",
                detail=comparison.gruha_jyothi_note,
            ),
        )

    steps = method.steps if method else []
    if steps:
        metrics.append(
            ReportMetric(
                label="How we estimated",
                value=f"{len(steps)} steps",
                detail=" · ".join(steps),
            )
        )

    headline = (
        f"Illustrative VNM saving · {location_line}"
        if comparison.is_vnm_cheaper
        else f"Limited VNM benefit · {location_line}"
    )

    return SolarIntelligenceReport(
        option="vnm",
        title="How we estimated your savings",
        status="ready",
        headline=headline,
        location_line=location_line,
        property_type=property_type,
        sections=[
            ReportSection(
                id="methodology",
                title="How we estimated your savings",
                metrics=metrics,
            )
        ],
        disclaimer=comparison.disclaimer,
        actions=[comparison.cta_primary, comparison.cta_secondary],
        raw={"vnm_comparison": comparison.model_dump(mode="json")},
    )


def _individual_report(
    option: SolarOptionCard,
    prefill: BillSolarPrefill,
    location_line: str,
    property_type: str,
) -> SolarIntelligenceReport:
    raw = option.result
    sizing = raw.get("sizing") or {}
    generation = raw.get("generation") or {}
    economics = raw.get("economics") or {}

    plant_kwp = option.plant_kwp or sizing.get("analyzed_kwp") or prefill.suggested_plant_kwp or 0.0
    annual_gen = float(generation.get("estimated_annual_generation_kwh") or 0)
    monthly_units = prefill.monthly_units
    annual_consumption = monthly_units * 12.0
    offset_kwh = float(raw.get("estimated_monthly_units_offset") or 0) * 12.0
    coverage = _pct(offset_kwh, annual_consumption) if annual_consumption > 0 else None

    rule = get_default_solar_rooftop_rule()
    yield_yr = float(generation.get("specific_yield_kwh_per_kwp_year") or rule.generation["specific_yield_kwh_per_kwp_year"])
    peak_sun_hrs = round(yield_yr / 365.0, 1)

    gross_capex = float(economics.get("gross_capex_inr") or plant_kwp * float(rule.economics["capital_cost_inr_per_kwp"]))
    cfa = float(economics.get("estimated_cfa_inr") or 0)
    net_capex = float(economics.get("net_capex_inr") or max(0.0, gross_capex - cfa))
    annual_saving = float(economics.get("estimated_annual_saving_inr") or (option.monthly_saving_inr or 0) * 12)

    install_low, install_high = _range(gross_capex, _INSTALL_COST_RANGE_FACTOR)
    net_low, net_high = _range(net_capex, _INSTALL_COST_RANGE_FACTOR)
    payback_low, payback_high = _payback_range(net_low, net_high, annual_saving)
    savings_25yr = _escalated_savings(annual_saving, _TARIFF_ESCALATION, _SYSTEM_LIFE_YEARS)
    carbon = _carbon_metrics(annual_gen)

    roi_pct = _roi_percent(net_capex, annual_saving, savings_25yr, carbon["carbon_income_25yr"])
    combined_25yr = savings_25yr + carbon["carbon_income_25yr"]

    status = "ready" if option.status == "ESTIMATED" else "preliminary"
    headline = (
        f"Report generated for {location_line} · {property_type} property"
        if status == "ready"
        else "Preliminary report — more inputs may be needed for a full estimate"
    )

    sections = [
        ReportSection(
            id="system",
            title="System Recommendation",
            metrics=[
                ReportMetric(
                    label="Optimal System Size",
                    value=f"{_fmt_kwp(plant_kwp)} kW",
                    detail=f"Covers {coverage}% of your current consumption" if coverage is not None else None,
                ),
                ReportMetric(
                    label="Annual Generation",
                    value=f"{_fmt_int(annual_gen)} kWh",
                    detail=f"Based on {peak_sun_hrs} peak sun hrs/day in Karnataka",
                ),
            ],
        ),
        ReportSection(
            id="financial",
            title="Financial Analysis",
            metrics=[
                ReportMetric(
                    label="Installation Cost",
                    value=f"Rs {_fmt_inr(install_low)} to Rs {_fmt_inr(install_high)}",
                    detail="Market range from installer network",
                ),
                ReportMetric(
                    label="PM Surya Ghar Subsidy",
                    value=f"Rs {_fmt_inr(cfa)}",
                    detail="Applicable for systems up to 10 kW",
                ),
                ReportMetric(
                    label="Net Cost After Subsidy",
                    value=f"Rs {_fmt_inr(net_low)} to Rs {_fmt_inr(net_high)}",
                    detail="Your actual out-of-pocket investment",
                ),
            ],
        ),
        ReportSection(
            id="returns",
            title="Returns & Payback",
            metrics=[
                ReportMetric(
                    label="Annual Electricity Savings",
                    value=f"Rs {_fmt_inr(annual_saving)}/yr",
                    detail=f"At {prefill.discom} retail tariff for your bill",
                ),
                ReportMetric(
                    label="Payback Period",
                    value=_payback_label(payback_low, payback_high),
                    detail="Post-subsidy, before carbon income",
                ),
                ReportMetric(
                    label="25-Year Savings",
                    value=f"Rs {_fmt_inr(savings_25yr)}",
                    detail=f"Includes {_pct(_TARIFF_ESCALATION * 100, 100, decimals=0)}% annual tariff increase",
                ),
            ],
        ),
        ReportSection(
            id="carbon",
            title="Carbon Credits (Suryaion Exclusive)",
            metrics=[
                ReportMetric(
                    label="Annual CO₂ Offset",
                    value=f"{carbon['annual_tonnes']:.1f} T CO₂e",
                    detail=f"Grid emission factor: {_GRID_EMISSION_KG_PER_KWH} kgCO₂/kWh (BEE)",
                ),
                ReportMetric(
                    label="Estimated Credit Value",
                    value=f"Rs {_fmt_inr(carbon['annual_low'])} to Rs {_fmt_inr(carbon['annual_high'])}/yr",
                    detail=(
                        f"Voluntary market rates Rs {_fmt_inr(_CARBON_PRICE_LOW_INR_PER_TONNE)} "
                        f"to Rs {_fmt_inr(_CARBON_PRICE_HIGH_INR_PER_TONNE)}/tonne"
                    ),
                ),
                ReportMetric(
                    label="25-Year Carbon Income",
                    value=f"Rs {_fmt_inr(carbon['carbon_income_25yr'])}+",
                    detail="Additional to your electricity savings",
                ),
            ],
        ),
        ReportSection(
            id="total",
            title="Total 25-Year Value",
            metrics=[
                ReportMetric(
                    label="Combined 25-Year Value",
                    value=f"Rs {_fmt_inr(combined_25yr)}",
                    detail="Electricity savings plus carbon credit income",
                ),
                ReportMetric(
                    label="Return on Investment",
                    value=f"{roi_pct}% p.a.",
                    detail="Average annual return over 25 years",
                ),
            ],
        ),
    ]

    return SolarIntelligenceReport(
        option="individual_solar",
        title="Solar Intelligence Report",
        status=status,
        headline=headline,
        location_line=location_line,
        property_type=property_type,
        sections=sections,
        disclaimer=_DISCLAIMER,
        raw={"option_result": raw, "prefill": prefill.model_dump(mode="json")},
    )


def _group_report(
    option: SolarOptionCard,
    prefill: BillSolarPrefill,
    location_line: str,
    property_type: str,
    *,
    title: str,
) -> SolarIntelligenceReport:
    raw = option.result
    rule = get_default_solar_rooftop_rule()
    plant_kwp = option.plant_kwp or raw.get("proposed_kwp") or prefill.suggested_plant_kwp or 0.0
    monthly_gen = float(raw.get("estimated_monthly_generation_kwh") or 0)
    if monthly_gen <= 0 and plant_kwp > 0:
        yield_yr = float(rule.generation["specific_yield_kwh_per_kwp_year"])
        monthly_gen = plant_kwp * yield_yr / 12.0
    annual_gen = monthly_gen * 12.0
    annual_consumption = prefill.monthly_units * 12.0
    coverage = _pct(min(annual_gen, annual_consumption), annual_consumption) if annual_consumption > 0 else None
    peak_sun_hrs = round(float(rule.generation["specific_yield_kwh_per_kwp_year"]) / 365.0, 1)

    gross_capex = plant_kwp * float(rule.economics["capital_cost_inr_per_kwp"])
    cfa = _estimate_cfa(plant_kwp, rule.cfa_pm_surya_ghar)
    net_capex = max(0.0, gross_capex - cfa)
    annual_saving = (option.monthly_saving_inr or raw.get("estimated_group_monthly_saving_inr") or 0) * 12

    install_low, install_high = _range(gross_capex, _INSTALL_COST_RANGE_FACTOR)
    net_low, net_high = _range(net_capex, _INSTALL_COST_RANGE_FACTOR)
    payback_low, payback_high = _payback_range(net_low, net_high, annual_saving)
    savings_25yr = _escalated_savings(annual_saving, _TARIFF_ESCALATION, _SYSTEM_LIFE_YEARS)
    carbon = _carbon_metrics(annual_gen)
    roi_pct = _roi_percent(net_capex, annual_saving, savings_25yr, carbon["carbon_income_25yr"])
    combined_25yr = savings_25yr + carbon["carbon_income_25yr"]

    suitable = option.status in {"POTENTIALLY_SUITABLE", "ESTIMATED"}
    status = "ready" if suitable and annual_saving > 0 else "preliminary"
    headline = (
        f"{title} report for {location_line} · {property_type} property"
        if status == "ready"
        else f"Preliminary {title} report — confirm participant details with BESCOM"
    )

    sections = [
        ReportSection(
            id="system",
            title="System Recommendation",
            metrics=[
                ReportMetric(
                    label="Shared Plant Size",
                    value=f"{_fmt_kwp(plant_kwp)} kW",
                    detail=f"Covers ~{coverage}% of group consumption" if coverage is not None else None,
                ),
                ReportMetric(
                    label="Annual Generation",
                    value=f"{_fmt_int(annual_gen)} kWh",
                    detail=f"Based on {peak_sun_hrs} peak sun hrs/day in Karnataka",
                ),
            ],
        ),
        ReportSection(
            id="financial",
            title="Financial Analysis",
            metrics=[
                ReportMetric(
                    label="Indicative Installation Cost",
                    value=f"Rs {_fmt_inr(install_low)} to Rs {_fmt_inr(install_high)}",
                    detail="Shared plant — actual split depends on community agreement",
                ),
                ReportMetric(
                    label="PM Surya Ghar Subsidy (est.)",
                    value=f"Rs {_fmt_inr(cfa)}",
                    detail="Subject to host eligibility and portal approval",
                ),
                ReportMetric(
                    label="Net Cost After Subsidy (est.)",
                    value=f"Rs {_fmt_inr(net_low)} to Rs {_fmt_inr(net_high)}",
                    detail="Your share may differ under VNM/GNM procurement rules",
                ),
            ],
        ),
        ReportSection(
            id="returns",
            title="Returns & Payback",
            metrics=[
                ReportMetric(
                    label="Annual Group Savings",
                    value=f"Rs {_fmt_inr(annual_saving)}/yr",
                    detail=f"Preliminary estimate across all {title} participants",
                ),
                ReportMetric(
                    label="Payback Period",
                    value=_payback_label(payback_low, payback_high),
                    detail="Post-subsidy, before carbon income",
                ),
                ReportMetric(
                    label="25-Year Savings",
                    value=f"Rs {_fmt_inr(savings_25yr)}",
                    detail=f"Includes {_pct(_TARIFF_ESCALATION * 100, 100, decimals=0)}% annual tariff increase",
                ),
            ],
        ),
        ReportSection(
            id="carbon",
            title="Carbon Credits",
            metrics=[
                ReportMetric(
                    label="Annual CO₂ Offset",
                    value=f"{carbon['annual_tonnes']:.1f} T CO₂e",
                    detail=f"Grid emission factor: {_GRID_EMISSION_KG_PER_KWH} kgCO₂/kWh (BEE)",
                ),
                ReportMetric(
                    label="Estimated Credit Value",
                    value=f"Rs {_fmt_inr(carbon['annual_low'])} to Rs {_fmt_inr(carbon['annual_high'])}/yr",
                    detail="Voluntary market rates — allocation per participant not modeled",
                ),
            ],
        ),
        ReportSection(
            id="total",
            title="Total 25-Year Value",
            metrics=[
                ReportMetric(
                    label="Combined 25-Year Value",
                    value=f"Rs {_fmt_inr(combined_25yr)}",
                    detail="Group-level electricity savings plus carbon income",
                ),
                ReportMetric(
                    label="Return on Investment",
                    value=f"{roi_pct}% p.a.",
                    detail="Group-level average over 25 years",
                ),
            ],
        ),
    ]

    return SolarIntelligenceReport(
        option=option.option,
        title="Solar Intelligence Report",
        status=status,
        headline=headline,
        location_line=location_line,
        property_type=property_type,
        sections=sections,
        disclaimer=_DISCLAIMER,
        raw={"option_result": raw, "prefill": prefill.model_dump(mode="json")},
    )


_DISCLAIMER = (
    "Figures are calculated using MNRE irradiance data, DISCOM published tariffs, "
    "and BEE carbon intensity factors for Karnataka. Installation costs are indicative "
    "ranges from the Suryaion installer network. Carbon credit values reflect current "
    "voluntary market rates and are subject to market conditions. Actual results may vary. "
    "This report is for informational purposes and does not constitute financial advice."
)


def _extract_pincode(address: str | None) -> str | None:
    if not address:
        return None
    match = re.search(r"\b(\d{6})\b", address)
    return match.group(1) if match else None


def _location_line(pincode: str | None) -> str:
    if pincode:
        return f"Karnataka · {pincode}"
    return "Karnataka"


def _fmt_inr(value: float) -> str:
    return f"{round(value):,}"


def _fmt_int(value: float) -> str:
    return f"{round(value):,}"


def _fmt_kwp(kwp: float) -> str:
    if abs(kwp - round(kwp)) < 0.05:
        return str(int(round(kwp)))
    return f"{kwp:.1f}"


def _pct(part: float, whole: float, *, decimals: int = 0) -> str:
    if whole <= 0:
        return "0"
    return f"{round(part / whole * 100, decimals):g}"


def _range(mid: float, factor: float) -> tuple[float, float]:
    return max(0.0, mid * (1 - factor)), mid * (1 + factor)


def _payback_range(net_low: float, net_high: float, annual_saving: float) -> tuple[float | None, float | None]:
    if annual_saving <= 0:
        return None, None
    return net_low / annual_saving, net_high / annual_saving


def _payback_label(low: float | None, high: float | None) -> str:
    if low is None or high is None:
        return "N/A"
    return f"{low:.1f} to {high:.1f} yrs"


def _escalated_savings(annual_year1: float, escalation: float, years: int) -> float:
    total = 0.0
    for year in range(years):
        total += annual_year1 * ((1 + escalation) ** year)
    return round(total)


def _carbon_metrics(annual_gen_kwh: float) -> dict[str, float]:
    annual_tonnes = annual_gen_kwh * _GRID_EMISSION_KG_PER_KWH / 1000.0
    annual_low = annual_tonnes * _CARBON_PRICE_LOW_INR_PER_TONNE
    annual_high = annual_tonnes * _CARBON_PRICE_HIGH_INR_PER_TONNE
    carbon_25yr = sum(
        annual_low + (annual_high - annual_low) * 0.5 for _ in range(_SYSTEM_LIFE_YEARS)
    )
    return {
        "annual_tonnes": annual_tonnes,
        "annual_low": annual_low,
        "annual_high": annual_high,
        "carbon_income_25yr": round(carbon_25yr),
    }


def _roi_percent(
    net_capex: float,
    annual_saving: float,
    savings_25yr: float,
    carbon_25yr: float,
) -> int:
    if net_capex <= 0:
        return 0
    total_return = savings_25yr + carbon_25yr - net_capex
    avg_annual = total_return / _SYSTEM_LIFE_YEARS
    return round(avg_annual / net_capex * 100)


def _estimate_cfa(kwp: float, cfa_cfg: dict[str, Any]) -> float:
    slabs = sorted(cfa_cfg.get("slabs", []), key=lambda s: float(s["up_to_kwp"]))
    max_cfa_kwp = float(cfa_cfg.get("max_cfa_kwp", slabs[-1]["up_to_kwp"] if slabs else 0))
    remaining = min(kwp, max_cfa_kwp)
    prev = 0.0
    total = 0.0
    for slab in slabs:
        up_to = float(slab["up_to_kwp"])
        rate = float(slab["inr_per_kwp"])
        band = max(0.0, min(remaining, up_to) - prev)
        total += band * rate
        prev = up_to
        if remaining <= up_to:
            break
    return round(total, 2)
