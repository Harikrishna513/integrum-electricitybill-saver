from __future__ import annotations

from datetime import date

from app.domain.engines.tariff import TariffEngine
from app.domain.models.tariff import TariffCalculationStatus
from app.domain.models.vnm import (
    VNMAnalysisResult,
    VNMConditionCheck,
    VNMParticipantEstimate,
    VNMParticipantInput,
    VNMPlantInput,
    VNMStatus,
)
from app.infrastructure.rules.vnm_rules import VNMRule, get_default_vnm_rule

_OK_TARIFF = {
    TariffCalculationStatus.CALCULATED,
    TariffCalculationStatus.REQUIRES_VERIFICATION,
}


class VNMAnalysisEngine:
    def __init__(
        self,
        rule: VNMRule | None = None,
        tariff_engine: TariffEngine | None = None,
    ) -> None:
        self._rule = rule or get_default_vnm_rule()
        self._tariff = tariff_engine or TariffEngine()

    @property
    def rule(self) -> VNMRule:
        return self._rule

    def analyze(
        self,
        *,
        participants: list[VNMParticipantInput],
        plant: VNMPlantInput,
        as_of: date,
        discom: str = "BESCOM",
        tariff_code: str | None = "LT-1",
    ) -> VNMAnalysisResult:
        rule = self._rule
        warnings = [
            rule.user_messages.get(
                "never_approval",
                "Preliminary VNM analysis only — not BESCOM approval.",
            )
        ]
        steps: list[str] = []
        conditions: list[VNMConditionCheck] = []
        missing: list[str] = []

        if not rule.applies_on(as_of):
            return VNMAnalysisResult(
                status=VNMStatus.INSUFFICIENT_INFORMATION,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                source_url=rule.source_url,
                as_of=as_of,
                warnings=warnings,
                message=f"No active VNM rule for {as_of.isoformat()} under {rule.rule_version}.",
            )

        if rule.verification_status != "VERIFIED":
            warnings.append(
                f"VNM rule verification_status={rule.verification_status}; "
                "re-check latest SOP/KERC order."
            )

        min_n = int(rule.eligibility.get("min_participating_consumers", 2))
        n_ok = len(participants) >= min_n
        conditions.append(
            VNMConditionCheck(
                code="MIN_PARTICIPANTS",
                passed=n_ok,
                detail=(
                    f"{len(participants)} participating connection(s); "
                    f"SOP requires ≥ {min_n}."
                ),
            )
        )
        steps.append(conditions[-1].detail)
        if not n_ok:
            missing.append("at_least_two_participating_consumers")

        categories = {p.category.upper() for p in participants}
        same_cat = len(categories) == 1
        if rule.eligibility.get("require_same_category", True):
            conditions.append(
                VNMConditionCheck(
                    code="SAME_CATEGORY",
                    passed=same_cat if participants else False,
                    detail=(
                        f"Categories present: {sorted(categories) or 'none'}. "
                        "SOP requires same consumer category."
                    ),
                )
            )
            steps.append(conditions[-1].detail)

        eligible = {c.upper() for c in rule.eligibility.get("eligible_categories", [])}
        category_ok = same_cat and next(iter(categories), "").upper() in eligible
        conditions.append(
            VNMConditionCheck(
                code="ELIGIBLE_CATEGORY",
                passed=category_ok if participants else False,
                detail=(
                    f"Category {next(iter(categories), 'UNKNOWN')} "
                    f"{'is' if category_ok else 'is not'} in eligible set {sorted(eligible)}."
                ),
            )
        )
        steps.append(conditions[-1].detail)

        if plant.same_discom_area is None and rule.eligibility.get(
            "require_same_discom_area_declared", True
        ):
            missing.append("same_discom_area")
            conditions.append(
                VNMConditionCheck(
                    code="SAME_DISCOM_AREA",
                    passed=None,
                    detail="Caller did not declare whether plant + participants share licensee area.",
                )
            )
        else:
            area_ok = bool(plant.same_discom_area)
            conditions.append(
                VNMConditionCheck(
                    code="SAME_DISCOM_AREA",
                    passed=area_ok,
                    detail=(
                        "Same distribution licensee area declared."
                        if area_ok
                        else "Plant/participants not declared in same licensee area."
                    ),
                )
            )
        steps.append(conditions[-1].detail)

        share_target = float(rule.procurement.get("shares_must_sum_to_percent", 100))
        share_tol = float(rule.procurement.get("sum_tolerance_percent", 0.5))
        share_sum = sum(p.procurement_share_percent for p in participants)
        shares_ok = abs(share_sum - share_target) <= share_tol
        conditions.append(
            VNMConditionCheck(
                code="PROCUREMENT_SHARES_SUM",
                passed=shares_ok if participants else False,
                detail=(
                    f"Procurement shares sum to {share_sum:.2f}% "
                    f"(target {share_target:g}% ± {share_tol:g})."
                ),
            )
        )
        steps.append(conditions[-1].detail)
        steps.append(str(rule.procurement.get("share_change_note", "")).strip())

        combined_load = sum(p.sanctioned_load_kw for p in participants)
        min_kwp = float(rule.plant.get("min_kwp", 5.0))
        max_kwp = combined_load if rule.plant.get("max_equals_combined_sanctioned_load", True) else None
        plant_min_ok = plant.proposed_kwp + 1e-9 >= min_kwp
        conditions.append(
            VNMConditionCheck(
                code="PLANT_MIN_KWP",
                passed=plant_min_ok,
                detail=f"Proposed {plant.proposed_kwp:g} kWp; SOP minimum is {min_kwp:g} kWp.",
            )
        )
        steps.append(conditions[-1].detail)

        plant_max_ok: bool | None
        if max_kwp is None:
            plant_max_ok = None
            conditions.append(
                VNMConditionCheck(
                    code="PLANT_MAX_VS_COMBINED_LOAD",
                    passed=None,
                    detail="Max plant vs combined load rule not configured.",
                )
            )
        else:
            plant_max_ok = plant.proposed_kwp <= max_kwp + 1e-9
            conditions.append(
                VNMConditionCheck(
                    code="PLANT_MAX_VS_COMBINED_LOAD",
                    passed=plant_max_ok,
                    detail=(
                        f"Proposed {plant.proposed_kwp:g} kWp vs combined sanctioned load "
                        f"{combined_load:g} kW (max allowed under SOP gist)."
                    ),
                )
            )
        steps.append(conditions[-1].detail)

        # Technical feasibility always unknown here
        conditions.append(
            VNMConditionCheck(
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
            status = VNMStatus.INSUFFICIENT_INFORMATION
            message = rule.user_messages.get(
                "insufficient",
                "Missing inputs prevent a complete VNM pre-screen.",
            )
            return VNMAnalysisResult(
                status=status,
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
                message=message,
            )

        if failed:
            return VNMAnalysisResult(
                status=VNMStatus.POTENTIALLY_UNSUITABLE,
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
                    "One or more VNM pre-screen checks failed.",
                ),
            )

        # Generation estimate
        yield_yr = float(rule.generation_defaults.get("specific_yield_kwh_per_kwp_year", 1480))
        if plant.estimated_monthly_generation_kwh is not None:
            monthly_gen = float(plant.estimated_monthly_generation_kwh)
        else:
            monthly_gen = plant.proposed_kwp * yield_yr / 12.0
        steps.append(
            f"Estimated monthly plant generation: {monthly_gen:.2f} kWh "
            f"(from {'caller' if plant.estimated_monthly_generation_kwh is not None else f'yield {yield_yr:g} kWh/kWp/year'})."
        )

        generic = float(rule.settlement.get("generic_tariff_ground_or_dspv_inr_per_kwh", 0))
        frac = float(rule.settlement.get("excess_purchase_fraction_of_generic", 0.75))
        excess_rate = round(generic * frac, 4)
        warnings.append(
            f"Excess purchase rate assumption: {frac:.0%} × ₹{generic:g} = ₹{excess_rate:g}/kWh "
            f"({rule.settlement.get('generic_tariff_verification_status', 'UNVERIFIED')})."
        )
        steps.append(
            f"Surplus after credit valued at ₹{excess_rate:g}/kWh (75% of bootstrap generic)."
        )

        estimates: list[VNMParticipantEstimate] = []
        group_saving = 0.0
        tariff_ok = True

        for p in participants:
            allocated = monthly_gen * (p.procurement_share_percent / 100.0)
            residual = max(0.0, p.monthly_units - allocated)
            surplus = max(0.0, allocated - p.monthly_units)
            steps.append(
                f"{p.connection_id}: share {p.procurement_share_percent:g}% → "
                f"credit {allocated:.2f} kWh; residual retail {residual:.2f}; "
                f"surplus {surplus:.2f}."
            )

            baseline = new = None
            baseline_total = new_total = surplus_inr = net_cost = saving = None

            if p.category.upper() == "DOMESTIC":
                baseline = self._tariff.calculate(
                    discom=discom,
                    category="DOMESTIC",
                    as_of=as_of,
                    units=p.monthly_units,
                    sanctioned_load_kw=p.sanctioned_load_kw,
                    tariff_code=tariff_code,
                )
                new = self._tariff.calculate(
                    discom=discom,
                    category="DOMESTIC",
                    as_of=as_of,
                    units=residual,
                    sanctioned_load_kw=p.sanctioned_load_kw,
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
                    f"{p.connection_id}: category {p.category.upper()} — "
                    "₹ estimate skipped (v1 TariffEngine is DOMESTIC-only)."
                )

            estimates.append(
                VNMParticipantEstimate(
                    connection_id=p.connection_id,
                    category=p.category.upper(),
                    sanctioned_load_kw=p.sanctioned_load_kw,
                    monthly_units=p.monthly_units,
                    procurement_share_percent=p.procurement_share_percent,
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

        # Hard pre-screen passed. Feasibility is never cleared here.
        # Prefer POTENTIALLY_SUITABLE for clean numeric pre-screens; escalate to
        # TECHNICAL_VERIFICATION_REQUIRED when topology suggests OA / multi-substation risk.
        risky_topology = (plant.grid_topology_hint or "").lower() in {
            "multi_substation",
            "different_feeder",
            "cross_feeder",
        }
        if risky_topology or any(
            c.code == "SAME_DISCOM_AREA" and c.passed is None for c in conditions
        ):
            status = VNMStatus.TECHNICAL_VERIFICATION_REQUIRED
            message = rule.user_messages.get(
                "technical_verification",
                "Pre-screen needs official technical verification.",
            )
        else:
            status = VNMStatus.POTENTIALLY_SUITABLE
            message = rule.user_messages.get(
                "potentially_suitable",
                "Inputs appear consistent with published VNM pre-screen checks.",
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

        return VNMAnalysisResult(
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
            excess_purchase_rate_inr_per_kwh=excess_rate,
            participants=estimates,
            conditions=conditions,
            missing_inputs=missing,
            explanation_steps=steps,
            warnings=warnings,
            assumptions=self._assumptions(),
            estimated_group_monthly_saving_inr=round(group_saving, 2) if tariff_ok else None,
            message=message,
        )

    def _assumptions(self) -> dict:
        rule = self._rule
        return {
            "rule_version": rule.rule_version,
            "verification_status": rule.verification_status,
            "eligibility": rule.eligibility,
            "plant": rule.plant,
            "procurement": rule.procurement,
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
