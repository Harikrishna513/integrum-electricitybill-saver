from __future__ import annotations

from typing import Any

from app.domain.engines.tariff import TariffEngine
from app.domain.models.solar import (
    SolarAnalysisResult,
    SolarAnalysisStatus,
    SolarEconomics,
    SolarGenerationEstimate,
    SolarProfile,
    SolarSizing,
)
from app.domain.models.tariff import TariffCalculationStatus
from app.infrastructure.rules.solar_rules import (
    SolarRooftopRule,
    get_default_solar_rooftop_rule,
)


class SolarAnalysisEngine:
    def __init__(
        self,
        rule: SolarRooftopRule | None = None,
        tariff_engine: TariffEngine | None = None,
    ) -> None:
        self._rule = rule or get_default_solar_rooftop_rule()
        self._tariff = tariff_engine or TariffEngine()

    @property
    def rule(self) -> SolarRooftopRule:
        return self._rule

    def analyze(self, profile: SolarProfile) -> SolarAnalysisResult:
        rule = self._rule
        warnings: list[str] = [
            rule.user_messages.get(
                "estimate_only",
                "Estimated / approximate rooftop solar planning only.",
            ),
            rule.user_messages.get(
                "net_metering_later",
                "Simplified offset model — net metering detail is Milestone 15.",
            ),
        ]
        steps: list[str] = []

        if profile.monthly_units < 0 or profile.sanctioned_load_kw < 0:
            return SolarAnalysisResult(
                status=SolarAnalysisStatus.INVALID_INPUT,
                profile=profile,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message="monthly_units and sanctioned_load_kw must be non-negative.",
            )

        if profile.category.upper() != "DOMESTIC":
            return SolarAnalysisResult(
                status=SolarAnalysisStatus.UNSUPPORTED_CATEGORY,
                profile=profile,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message=(
                    f"Category {profile.category.upper()} is not supported by v1 solar "
                    "analysis (DOMESTIC only)."
                ),
            )

        if not rule.applies_on(profile.as_of):
            return SolarAnalysisResult(
                status=SolarAnalysisStatus.INVALID_INPUT,
                profile=profile,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message=(
                    f"No active solar rule for {profile.as_of.isoformat()} "
                    f"under {rule.rule_version}."
                ),
            )

        roof = profile.roof_area_m2
        require_roof = bool(rule.sizing.get("require_roof_for_recommendation", True))
        analyzing_user_kwp = profile.proposed_kwp is not None and profile.proposed_kwp > 0

        if require_roof and (roof is None or roof <= 0) and not analyzing_user_kwp:
            return SolarAnalysisResult(
                status=SolarAnalysisStatus.NO_ROOF,
                profile=profile,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message=rule.user_messages.get(
                    "no_roof",
                    "No usable roof area — individual rooftop not recommended. See VNM later.",
                ),
                assumptions=self._assumption_snapshot(rule),
            )

        yield_yr = float(rule.generation["specific_yield_kwh_per_kwp_year"])
        target_frac = float(rule.sizing.get("target_offset_fraction", 0.85))
        m2_per_kwp = float(rule.sizing.get("roof_m2_per_kwp", 10.0))
        load_ratio = float(rule.sizing.get("max_kwp_vs_sanctioned_load_ratio", 1.0))
        min_kwp = float(rule.sizing.get("min_kwp", 1.0))
        max_kwp = float(rule.sizing.get("max_kwp", 10.0))
        step = float(rule.sizing.get("step_kwp", 0.5))

        annual_units = profile.monthly_units * 12.0
        raw_kwp = 0.0
        if yield_yr > 0:
            raw_kwp = (annual_units * target_frac) / yield_yr
        steps.append(
            f"Raw size for {target_frac:.0%} of annual usage "
            f"({annual_units:g} kWh): {raw_kwp:.2f} kWp "
            f"at {yield_yr:g} kWh/kWp/year."
        )

        capped_by: list[str] = []
        candidate = raw_kwp
        max_from_roof: float | None = None
        max_from_load: float | None = None

        if roof is not None and roof > 0 and m2_per_kwp > 0:
            max_from_roof = roof / m2_per_kwp
            if candidate > max_from_roof:
                candidate = max_from_roof
                capped_by.append("roof_area")
            steps.append(
                f"Roof cap: {roof:g} m² / {m2_per_kwp:g} m²/kWp → {max_from_roof:.2f} kWp."
            )

        if profile.sanctioned_load_kw > 0:
            max_from_load = profile.sanctioned_load_kw * load_ratio
            if candidate > max_from_load:
                candidate = max_from_load
                capped_by.append("sanctioned_load")
            steps.append(
                f"Load cap: {profile.sanctioned_load_kw:g} kW × {load_ratio:g} → "
                f"{max_from_load:.2f} kWp."
            )

        if candidate > max_kwp:
            candidate = max_kwp
            capped_by.append("rule_max_kwp")
        if candidate < min_kwp and raw_kwp > 0:
            # Only bump to min if there was meaningful demand and caps allow it
            allow_min = True
            if max_from_roof is not None and max_from_roof < min_kwp:
                allow_min = False
                capped_by.append("roof_below_min_kwp")
            if max_from_load is not None and max_from_load < min_kwp:
                allow_min = False
                capped_by.append("load_below_min_kwp")
            if allow_min:
                candidate = min_kwp

        recommended = self._round_kwp(candidate, step) if candidate > 0 else 0.0
        if recommended > max_kwp:
            recommended = max_kwp
        if max_from_roof is not None and recommended > max_from_roof + 1e-9:
            recommended = self._round_kwp(max_from_roof, step)
            if recommended > max_from_roof:
                # step rounding went over roof — step down
                recommended = max(0.0, recommended - step)
            if "roof_area" not in capped_by:
                capped_by.append("roof_area")

        if analyzing_user_kwp:
            analyzed = float(profile.proposed_kwp or 0)
            steps.append(f"Using user-proposed capacity: {analyzed:g} kWp.")
        else:
            analyzed = recommended
            steps.append(f"Recommended capacity after caps/rounding: {analyzed:g} kWp.")

        if analyzed <= 0:
            return SolarAnalysisResult(
                status=SolarAnalysisStatus.NO_ROOF
                if (roof is None or roof <= 0)
                else SolarAnalysisStatus.INVALID_INPUT,
                profile=profile,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                sizing=SolarSizing(
                    recommended_kwp=recommended,
                    analyzed_kwp=analyzed,
                    raw_kwp_before_caps=round(raw_kwp, 4),
                    capped_by=capped_by,
                    max_from_roof_kwp=None
                    if max_from_roof is None
                    else round(max_from_roof, 4),
                    max_from_load_kwp=None
                    if max_from_load is None
                    else round(max_from_load, 4),
                ),
                warnings=warnings,
                explanation_steps=steps,
                assumptions=self._assumption_snapshot(rule),
                message="Could not determine a positive rooftop capacity under current caps.",
            )

        annual_gen = analyzed * yield_yr
        monthly_gen = annual_gen / 12.0
        generation = SolarGenerationEstimate(
            specific_yield_kwh_per_kwp_year=yield_yr,
            estimated_annual_generation_kwh=round(annual_gen, 2),
            estimated_monthly_generation_kwh=round(monthly_gen, 2),
        )
        steps.append(
            f"Estimated generation: {monthly_gen:.2f} kWh/month "
            f"({annual_gen:.2f} kWh/year)."
        )

        # Simplified offset (M14): min(generation, consumption)
        offset = min(profile.monthly_units, monthly_gen)
        residual = max(0.0, profile.monthly_units - offset)
        offset_model = str(
            rule.economics.get(
                "bill_offset_model",
                "simple_min_of_generation_and_consumption",
            )
        )
        steps.append(
            f"Simplified offset: billed units {profile.monthly_units:g} → "
            f"{residual:.2f} (offset {offset:.2f} kWh)."
        )

        cost_per_kwp = float(rule.economics.get("capital_cost_inr_per_kwp", 50000))
        gross_capex = analyzed * cost_per_kwp
        cfa = 0.0
        if profile.apply_cfa_estimate and rule.cfa_pm_surya_ghar.get("enabled", False):
            cfa = self._estimate_cfa(analyzed, rule.cfa_pm_surya_ghar)
            warnings.append(
                "CFA estimate uses bootstrap PM Surya Ghar slabs — "
                f"status={rule.cfa_pm_surya_ghar.get('verification_status', 'UNVERIFIED')}. "
                "Not an approval."
            )
            steps.append(f"Estimated CFA (bootstrap slabs): ₹{cfa:,.0f}.")
        net_capex = max(0.0, gross_capex - cfa)
        steps.append(
            f"Capex: gross ₹{gross_capex:,.0f} − CFA ₹{cfa:,.0f} → net ₹{net_capex:,.0f} "
            f"(at ₹{cost_per_kwp:,.0f}/kWp)."
        )

        old_bill = self._tariff.calculate(
            discom=profile.discom,
            category=profile.category,
            as_of=profile.as_of,
            units=profile.monthly_units,
            sanctioned_load_kw=profile.sanctioned_load_kw,
            tariff_code=profile.tariff_code,
        )
        new_bill = self._tariff.calculate(
            discom=profile.discom,
            category=profile.category,
            as_of=profile.as_of,
            units=residual,
            sanctioned_load_kw=profile.sanctioned_load_kw,
            tariff_code=profile.tariff_code,
        )

        ok_statuses = {
            TariffCalculationStatus.CALCULATED,
            TariffCalculationStatus.REQUIRES_VERIFICATION,
        }
        if old_bill.status not in ok_statuses or new_bill.status not in ok_statuses:
            warnings.append(
                f"Tariff engine status old={old_bill.status.value}, new={new_bill.status.value}."
            )
            return SolarAnalysisResult(
                status=SolarAnalysisStatus.TARIFF_UNAVAILABLE,
                profile=profile,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                sizing=SolarSizing(
                    recommended_kwp=round(recommended, 4),
                    analyzed_kwp=round(analyzed, 4),
                    raw_kwp_before_caps=round(raw_kwp, 4),
                    capped_by=capped_by,
                    max_from_roof_kwp=None
                    if max_from_roof is None
                    else round(max_from_roof, 4),
                    max_from_load_kwp=None
                    if max_from_load is None
                    else round(max_from_load, 4),
                ),
                generation=generation,
                monthly_units_before=profile.monthly_units,
                estimated_monthly_units_after_offset=round(residual, 4),
                estimated_monthly_units_offset=round(offset, 4),
                offset_model=offset_model,
                explanation_steps=steps,
                warnings=warnings,
                assumptions=self._assumption_snapshot(rule),
                message="Could not compute ₹ savings because tariff calculation failed.",
            )

        if rule.verification_status != "VERIFIED":
            warnings.append(
                f"Solar rule verification_status={rule.verification_status}; "
                "treat economics as planning estimates only."
            )
        if old_bill.status == TariffCalculationStatus.REQUIRES_VERIFICATION:
            warnings.extend(old_bill.warnings)

        old_total = float(old_bill.estimated_total or 0)
        new_total = float(new_bill.estimated_total or 0)
        monthly_saving = round(old_total - new_total, 2)
        annual_saving = round(monthly_saving * 12, 2)
        payback = None
        if annual_saving > 0:
            payback = round(net_capex / annual_saving, 2)
            steps.append(
                f"Simple payback: ₹{net_capex:,.0f} / ₹{annual_saving:,.0f}/yr → "
                f"{payback} years."
            )
        else:
            warnings.append("Estimated annual saving is not positive; payback not computed.")

        economics = SolarEconomics(
            gross_capex_inr=round(gross_capex, 2),
            estimated_cfa_inr=round(cfa, 2) if profile.apply_cfa_estimate else None,
            net_capex_inr=round(net_capex, 2),
            current_monthly_bill_estimate=round(old_total, 2),
            estimated_monthly_bill_after_solar=round(new_total, 2),
            estimated_monthly_saving_inr=monthly_saving,
            estimated_annual_saving_inr=annual_saving,
            simple_payback_years=payback,
            tariff_rule_version=old_bill.rule_version,
            tariff_verification_status=old_bill.verification_status,
        )

        return SolarAnalysisResult(
            status=SolarAnalysisStatus.ESTIMATED,
            profile=profile,
            rule_version=rule.rule_version,
            verification_status=rule.verification_status,
            source=rule.source,
            sizing=SolarSizing(
                recommended_kwp=round(recommended, 4),
                analyzed_kwp=round(analyzed, 4),
                raw_kwp_before_caps=round(raw_kwp, 4),
                capped_by=capped_by,
                max_from_roof_kwp=None
                if max_from_roof is None
                else round(max_from_roof, 4),
                max_from_load_kwp=None
                if max_from_load is None
                else round(max_from_load, 4),
            ),
            generation=generation,
            economics=economics,
            monthly_units_before=profile.monthly_units,
            estimated_monthly_units_after_offset=round(residual, 4),
            estimated_monthly_units_offset=round(offset, 4),
            offset_model=offset_model,
            explanation_steps=steps,
            warnings=warnings,
            assumptions=self._assumption_snapshot(rule),
            message=(
                f"Estimated rooftop plant ~{analyzed:g} kWp may offset about "
                f"{offset:.0f} kWh/month under the simplified model "
                f"(~₹{monthly_saving:,.0f}/month bill delta)."
            ),
        )

    @staticmethod
    def _round_kwp(value: float, step: float) -> float:
        if step <= 0:
            return round(value, 2)
        return round(round(value / step) * step, 4)

    @staticmethod
    def _estimate_cfa(kwp: float, cfa_cfg: dict[str, Any]) -> float:
        """
        Apply ascending CFA slabs:
          capacity in (prev, up_to] gets that slab's inr_per_kwp.
        """
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

    @staticmethod
    def _assumption_snapshot(rule: SolarRooftopRule) -> dict[str, Any]:
        return {
            "rule_version": rule.rule_version,
            "verification_status": rule.verification_status,
            "generation": rule.generation,
            "sizing": rule.sizing,
            "economics": {
                k: v
                for k, v in rule.economics.items()
                if k != "offset_model_note"
            },
            "cfa_enabled": bool(rule.cfa_pm_surya_ghar.get("enabled", False)),
            "cfa_verification_status": rule.cfa_pm_surya_ghar.get(
                "verification_status"
            ),
        }
