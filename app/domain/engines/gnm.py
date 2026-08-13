"""
GNMAnalysisEngine — Milestone 17.

CONCEPT
  same-name consumer RRs + host plant + priority order
        │
        ▼
  SOP checks (count, same name/category, plant min/max, unique priorities)
        │
        ▼
  reserve 20% for host (unused → LAPSED); waterfall remaining by priority
        │
        ▼
  per-RR residual retail via TariffEngine + surplus @ 75% generic
        │
        ▼
  POTENTIALLY_SUITABLE | UNSUITABLE | INSUFFICIENT | TECHNICAL_VERIFICATION_REQUIRED

Never: "You are approved for GNM."
Never: clear technical feasibility.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.tariff import TariffEngine
from app.domain.models.gnm import (
    GNMAnalysisResult,
    GNMConditionCheck,
    GNMInstallationEstimate,
    GNMInstallationInput,
    GNMPlantInput,
    GNMStatus,
)
from app.domain.models.tariff import TariffCalculationStatus
from app.infrastructure.rules.gnm_rules import GNMRule, get_default_gnm_rule

_OK_TARIFF = {
    TariffCalculationStatus.CALCULATED,
    TariffCalculationStatus.REQUIRES_VERIFICATION,
}


class GNMAnalysisEngine:
    def __init__(
        self,
        rule: GNMRule | None = None,
        tariff_engine: TariffEngine | None = None,
    ) -> None:
        self._rule = rule or get_default_gnm_rule()
        self._tariff = tariff_engine or TariffEngine()

    @property
    def rule(self) -> GNMRule:
        return self._rule

    def analyze(
        self,
        *,
        installations: list[GNMInstallationInput],
        plant: GNMPlantInput,
        as_of: date,
        discom: str = "BESCOM",
        tariff_code: str | None = "LT-1",
    ) -> GNMAnalysisResult:
        rule = self._rule
        warnings = [
            rule.user_messages.get(
                "never_approval",
                "Preliminary GNM analysis only — not BESCOM approval.",
            )
        ]
        steps: list[str] = []
        conditions: list[GNMConditionCheck] = []
        missing: list[str] = []

        if not rule.applies_on(as_of):
            return GNMAnalysisResult(
                status=GNMStatus.INSUFFICIENT_INFORMATION,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                source_url=rule.source_url,
                as_of=as_of,
                warnings=warnings,
                message=f"No active GNM rule for {as_of.isoformat()} under {rule.rule_version}.",
            )

        if rule.verification_status != "VERIFIED":
            warnings.append(
                f"GNM rule verification_status={rule.verification_status}; "
                "re-check latest SOP/KERC order."
            )

        min_n = int(rule.eligibility.get("min_participating_installations", 2))
        n_ok = len(installations) >= min_n
        conditions.append(
            GNMConditionCheck(
                code="MIN_INSTALLATIONS",
                passed=n_ok,
                detail=(
                    f"{len(installations)} installation(s); SOP requires ≥ {min_n}."
                ),
            )
        )
        steps.append(conditions[-1].detail)
        if not n_ok:
            missing.append("at_least_two_installations")

        hosts = [i for i in installations if i.is_host]
        host_ok = len(hosts) == 1
        conditions.append(
            GNMConditionCheck(
                code="SINGLE_HOST",
                passed=host_ok,
                detail=(
                    f"Host flags found: {len(hosts)} (exactly one required — "
                    "plant location RR)."
                ),
            )
        )
        steps.append(conditions[-1].detail)
        if not host_ok:
            missing.append("exactly_one_host_installation")

        categories = {i.category.upper() for i in installations}
        same_cat = len(categories) == 1
        if rule.eligibility.get("require_same_category", True):
            conditions.append(
                GNMConditionCheck(
                    code="SAME_CATEGORY",
                    passed=same_cat if installations else False,
                    detail=(
                        f"Categories present: {sorted(categories) or 'none'}. "
                        "SOP requires same tariff category."
                    ),
                )
            )
            steps.append(conditions[-1].detail)

        if plant.same_consumer_name is None and rule.eligibility.get(
            "require_same_consumer_name", True
        ):
            missing.append("same_consumer_name")
            conditions.append(
                GNMConditionCheck(
                    code="SAME_CONSUMER_NAME",
                    passed=None,
                    detail="Caller did not declare whether all RRs share the same consumer name.",
                )
            )
        else:
            name_ok = bool(plant.same_consumer_name)
            conditions.append(
                GNMConditionCheck(
                    code="SAME_CONSUMER_NAME",
                    passed=name_ok,
                    detail=(
                        "Same consumer name declared across installations."
                        if name_ok
                        else "Installations not declared under the same consumer name."
                    ),
                )
            )
        steps.append(conditions[-1].detail)

        if plant.same_discom_area is None and rule.eligibility.get(
            "require_same_discom_area_declared", True
        ):
            missing.append("same_discom_area")
            conditions.append(
                GNMConditionCheck(
                    code="SAME_DISCOM_AREA",
                    passed=None,
                    detail="Caller did not declare same distribution licensee area.",
                )
            )
        else:
            area_ok = bool(plant.same_discom_area)
            conditions.append(
                GNMConditionCheck(
                    code="SAME_DISCOM_AREA",
                    passed=area_ok,
                    detail=(
                        "Same distribution licensee area declared."
                        if area_ok
                        else "Not declared in same licensee area."
                    ),
                )
            )
        steps.append(conditions[-1].detail)

        priorities = [i.priority for i in installations]
        unique_ok = len(priorities) == len(set(priorities))
        conditions.append(
            GNMConditionCheck(
                code="UNIQUE_PRIORITIES",
                passed=unique_ok if installations else False,
                detail=f"Priorities={sorted(priorities)}; must be unique.",
            )
        )
        steps.append(conditions[-1].detail)
        steps.append(str(rule.priority.get("change_note", "")).strip())

        combined_load = sum(i.sanctioned_load_kw for i in installations)
        min_kwp = float(rule.plant.get("min_kwp", 5.0))
        max_kwp = (
            combined_load
            if rule.plant.get("max_equals_combined_sanctioned_load", True)
            else None
        )
        plant_min_ok = plant.proposed_kwp + 1e-9 >= min_kwp
        conditions.append(
            GNMConditionCheck(
                code="PLANT_MIN_KWP",
                passed=plant_min_ok,
                detail=f"Proposed {plant.proposed_kwp:g} kWp; SOP minimum is {min_kwp:g} kWp.",
            )
        )
        steps.append(conditions[-1].detail)

        if max_kwp is None:
            plant_max_ok = None
            conditions.append(
                GNMConditionCheck(
                    code="PLANT_MAX_VS_COMBINED_LOAD",
                    passed=None,
                    detail="Max plant vs combined load rule not configured.",
                )
            )
        else:
            plant_max_ok = plant.proposed_kwp <= max_kwp + 1e-9
            conditions.append(
                GNMConditionCheck(
                    code="PLANT_MAX_VS_COMBINED_LOAD",
                    passed=plant_max_ok,
                    detail=(
                        f"Proposed {plant.proposed_kwp:g} kWp vs combined sanctioned load "
                        f"{combined_load:g} kW."
                    ),
                )
            )
        steps.append(conditions[-1].detail)

        conditions.append(
            GNMConditionCheck(
                code="TECHNICAL_FEASIBILITY",
                passed=None,
                detail=str(rule.settlement.get("technical_feasibility_note", "")).strip(),
            )
        )
        warnings.append(conditions[-1].detail)
        if plant.grid_topology_hint:
            steps.append(f"Grid topology hint (informational): {plant.grid_topology_hint}.")
            warnings.append(str(rule.settlement.get("open_access_note", "")).strip())

        failed = [c for c in conditions if c.passed is False]

        if missing and not failed:
            return GNMAnalysisResult(
                status=GNMStatus.INSUFFICIENT_INFORMATION,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                source_url=rule.source_url,
                as_of=as_of,
                proposed_kwp=plant.proposed_kwp,
                combined_sanctioned_load_kw=round(combined_load, 4),
                max_plant_kwp=None if max_kwp is None else round(max_kwp, 4),
                conditions=conditions,
                missing_inputs=missing,
                explanation_steps=steps,
                warnings=warnings,
                assumptions=self._assumptions(),
                message=rule.user_messages.get(
                    "insufficient",
                    "Missing inputs prevent a complete GNM pre-screen.",
                ),
            )

        if failed:
            return GNMAnalysisResult(
                status=GNMStatus.POTENTIALLY_UNSUITABLE,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                source_url=rule.source_url,
                as_of=as_of,
                proposed_kwp=plant.proposed_kwp,
                combined_sanctioned_load_kw=round(combined_load, 4),
                max_plant_kwp=None if max_kwp is None else round(max_kwp, 4),
                conditions=conditions,
                missing_inputs=missing,
                explanation_steps=steps,
                warnings=warnings,
                assumptions=self._assumptions(),
                message=rule.user_messages.get(
                    "potentially_unsuitable",
                    "One or more GNM pre-screen checks failed.",
                ),
            )

        yield_yr = float(
            rule.generation_defaults.get("specific_yield_kwh_per_kwp_year", 1480)
        )
        if plant.estimated_monthly_generation_kwh is not None:
            monthly_gen = float(plant.estimated_monthly_generation_kwh)
        else:
            monthly_gen = plant.proposed_kwp * yield_yr / 12.0
        steps.append(f"Estimated monthly plant generation: {monthly_gen:.2f} kWh.")

        host_frac = float(
            rule.host_rule.get("min_host_consumption_fraction_of_generation", 0.20)
        )
        reserved = monthly_gen * host_frac
        host = hosts[0]
        host_from_reserved = min(host.monthly_units, reserved)
        lapsed = reserved - host_from_reserved
        pool = monthly_gen - reserved
        steps.append(
            f"Host reserved band: {host_frac:.0%} × {monthly_gen:.2f} = {reserved:.2f} kWh; "
            f"host takes {host_from_reserved:.2f}; lapsed {lapsed:.2f}."
        )
        warnings.append(str(rule.host_rule.get("host_rule_note", "")).strip())

        credits: dict[str, float] = {i.connection_id: 0.0 for i in installations}
        credits[host.connection_id] = host_from_reserved

        # Waterfall remaining pool by priority (host included for unmet demand)
        ordered = sorted(installations, key=lambda x: x.priority)
        for inst in ordered:
            need = max(0.0, inst.monthly_units - credits[inst.connection_id])
            take = min(need, pool)
            credits[inst.connection_id] += take
            pool -= take
            if take > 0:
                steps.append(
                    f"Priority {inst.priority} ({inst.connection_id}): +{take:.2f} kWh "
                    f"(pool left {pool:.2f})."
                )

        unallocated = pool
        if unallocated > 1e-9:
            steps.append(
                f"Unallocated generation after credits/lapse: {unallocated:.2f} kWh "
                "(treated as group surplus export)."
            )

        generic = float(
            rule.settlement.get("generic_tariff_ground_or_dspv_inr_per_kwh", 0)
        )
        frac = float(rule.settlement.get("excess_purchase_fraction_of_generic", 0.75))
        excess_rate = round(generic * frac, 4)
        warnings.append(
            f"Excess purchase rate assumption: {frac:.0%} × ₹{generic:g} = ₹{excess_rate:g}/kWh."
        )

        estimates: list[GNMInstallationEstimate] = []
        group_saving = 0.0
        tariff_ok = True

        # Attribute leftover unallocated surplus to host for export-credit estimate
        export_extra = {i.connection_id: 0.0 for i in installations}
        if unallocated > 0:
            export_extra[host.connection_id] += unallocated

        for inst in ordered:
            allocated = credits[inst.connection_id]
            residual = max(0.0, inst.monthly_units - allocated)
            surplus = max(0.0, allocated - inst.monthly_units) + export_extra[
                inst.connection_id
            ]

            baseline_total = new_total = surplus_inr = net_cost = saving = None
            if inst.category.upper() == "DOMESTIC":
                baseline = self._tariff.calculate(
                    discom=discom,
                    category="DOMESTIC",
                    as_of=as_of,
                    units=inst.monthly_units,
                    sanctioned_load_kw=inst.sanctioned_load_kw,
                    tariff_code=tariff_code,
                )
                new = self._tariff.calculate(
                    discom=discom,
                    category="DOMESTIC",
                    as_of=as_of,
                    units=residual,
                    sanctioned_load_kw=inst.sanctioned_load_kw,
                    tariff_code=tariff_code,
                )
                if (
                    baseline.status not in _OK_TARIFF
                    or new.status not in _OK_TARIFF
                    or baseline.estimated_total is None
                    or new.estimated_total is None
                ):
                    tariff_ok = False
                else:
                    if baseline.status == TariffCalculationStatus.REQUIRES_VERIFICATION:
                        warnings.extend(baseline.warnings)
                    baseline_total = float(baseline.estimated_total)
                    new_total = float(new.estimated_total)
                    surplus_inr = round(surplus * excess_rate, 2)
                    net_cost = round(new_total - surplus_inr, 2)
                    saving = round(baseline_total - net_cost, 2)
                    group_saving += saving
            else:
                tariff_ok = False
                warnings.append(
                    f"{inst.connection_id}: category {inst.category.upper()} — "
                    "₹ estimate skipped (v1 TariffEngine is DOMESTIC-only)."
                )

            estimates.append(
                GNMInstallationEstimate(
                    connection_id=inst.connection_id,
                    category=inst.category.upper(),
                    sanctioned_load_kw=inst.sanctioned_load_kw,
                    monthly_units=inst.monthly_units,
                    priority=inst.priority,
                    is_host=inst.is_host,
                    allocated_generation_kwh=round(allocated, 4),
                    residual_retail_units=round(residual, 4),
                    surplus_export_kwh=round(surplus, 4),
                    baseline_retail_bill_inr=None
                    if baseline_total is None
                    else round(baseline_total, 2),
                    estimated_retail_bill_after_credit_inr=None
                    if new_total is None
                    else round(new_total, 2),
                    estimated_surplus_credit_inr=surplus_inr,
                    estimated_net_cost_inr=net_cost,
                    estimated_monthly_saving_inr=saving,
                )
            )

        risky_topology = (plant.grid_topology_hint or "").lower() in {
            "multi_substation",
            "different_feeder",
            "cross_feeder",
        }
        if risky_topology or any(
            c.code in {"SAME_DISCOM_AREA", "SAME_CONSUMER_NAME"} and c.passed is None
            for c in conditions
        ):
            status = GNMStatus.TECHNICAL_VERIFICATION_REQUIRED
            message = rule.user_messages.get(
                "technical_verification",
                "Pre-screen needs official technical verification.",
            )
        else:
            status = GNMStatus.POTENTIALLY_SUITABLE
            message = rule.user_messages.get(
                "potentially_suitable",
                "Inputs appear consistent with published GNM pre-screen checks.",
            )
            warnings.append(
                rule.user_messages.get(
                    "technical_verification",
                    "Technical feasibility / metering / PPA still require BESCOM.",
                )
            )

        if not tariff_ok:
            warnings.append(
                "Some ₹ estimates unavailable; eligibility checks still returned."
            )

        return GNMAnalysisResult(
            status=status,
            rule_version=rule.rule_version,
            verification_status=rule.verification_status,
            source=rule.source,
            source_url=rule.source_url,
            as_of=as_of,
            proposed_kwp=plant.proposed_kwp,
            combined_sanctioned_load_kw=round(combined_load, 4),
            max_plant_kwp=None if max_kwp is None else round(max_kwp, 4),
            estimated_monthly_generation_kwh=round(monthly_gen, 2),
            host_reserved_kwh=round(reserved, 4),
            lapsed_kwh=round(lapsed, 4),
            unallocated_generation_kwh=round(unallocated, 4),
            excess_purchase_rate_inr_per_kwh=excess_rate,
            installations=estimates,
            conditions=conditions,
            missing_inputs=missing,
            explanation_steps=steps,
            warnings=warnings,
            assumptions=self._assumptions(),
            estimated_group_monthly_saving_inr=round(group_saving, 2)
            if tariff_ok
            else None,
            message=message,
        )

    def _assumptions(self) -> dict:
        rule = self._rule
        return {
            "rule_version": rule.rule_version,
            "verification_status": rule.verification_status,
            "eligibility": rule.eligibility,
            "plant": rule.plant,
            "host_rule": {
                k: v for k, v in rule.host_rule.items() if k != "host_rule_note"
            },
            "generation_defaults": rule.generation_defaults,
            "settlement": {
                k: v
                for k, v in rule.settlement.items()
                if k
                not in {
                    "open_access_note",
                    "technical_feasibility_note",
                    "generic_tariff_note",
                }
            },
        }
