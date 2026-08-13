"""
ApplianceAnalysisEngine — Milestone 13.

CONCEPT
  User questionnaire
        │
        ▼
  Default watts/hours (YAML) + overrides
        │
        ▼
  Estimated kWh/month per appliance + shares
        │
        ▼
  (optional) tailored SavingsEngine recommendations

Never claim shares are measured end-use percentages.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain.engines.savings import SavingsEngine
from app.domain.models.appliance import (
    ApplianceAnalysisResult,
    ApplianceEstimate,
    EvType,
    HouseholdApplianceProfile,
)
from app.domain.models.savings import SavingsEstimate
from app.infrastructure.rules.appliance_defaults import (
    ApplianceDefaultsCatalog,
    get_default_appliance_defaults,
)


class ApplianceAnalysisEngine:
    def __init__(
        self,
        defaults: ApplianceDefaultsCatalog | None = None,
        savings_engine: SavingsEngine | None = None,
    ) -> None:
        self._defaults = defaults or get_default_appliance_defaults()
        self._savings = savings_engine or SavingsEngine()

    def analyze(
        self,
        profile: HouseholdApplianceProfile,
        *,
        bill_units: float | None = None,
    ) -> ApplianceAnalysisResult:
        warnings = [
            "Estimated / approximate only — based on your assumptions and default wattage tables.",
            "Not actual measured appliance-level consumption.",
        ]
        steps: list[str] = []
        rows: list[tuple[str, str, float, dict]] = []

        days = float(self._defaults.defaults.get("days_per_month", 30))
        apps = self._defaults.appliances

        def add_power(
            appliance_id: str,
            label: str,
            count: int,
            watts: float,
            hours: float,
        ) -> None:
            if count <= 0 or watts <= 0 or hours <= 0:
                return
            kwh = count * (watts / 1000.0) * hours * days
            assumptions = {
                "count": count,
                "watts": watts,
                "hours_per_day": hours,
                "days_per_month": days,
                "formula": "count * (watts/1000) * hours_per_day * days_per_month",
            }
            steps.append(
                f"{label}: {count} × {watts:g} W × {hours:g} h × {days:g} d "
                f"= {kwh:.2f} kWh (estimated)"
            )
            rows.append((appliance_id, label, round(kwh, 4), assumptions))

        # AC
        if profile.ac_count > 0:
            ac_cfg = apps.get("ac", {})
            add_power(
                "ac",
                "Air conditioner(s)",
                profile.ac_count,
                float(profile.ac_watts or ac_cfg.get("default_watts", 1500)),
                float(
                    profile.ac_hours_per_day
                    if profile.ac_hours_per_day is not None
                    else ac_cfg.get("default_hours_per_day", 6)
                ),
            )

        # Geyser
        if profile.geyser:
            g_cfg = apps.get("geyser", {})
            add_power(
                "geyser",
                "Geyser / water heater",
                1,
                float(profile.geyser_watts or g_cfg.get("default_watts", 2000)),
                float(
                    profile.geyser_hours_per_day
                    if profile.geyser_hours_per_day is not None
                    else g_cfg.get("default_hours_per_day", 1)
                ),
            )

        # Refrigerator
        if profile.refrigerator:
            r_cfg = apps.get("refrigerator", {})
            add_power(
                "refrigerator",
                "Refrigerator",
                1,
                float(r_cfg.get("default_watts", 150)),
                float(r_cfg.get("default_hours_per_day", 8)),
            )

        # Washing machine
        if profile.washing_machine:
            w_cfg = apps.get("washing_machine", {})
            add_power(
                "washing_machine",
                "Washing machine",
                1,
                float(w_cfg.get("default_watts", 500)),
                float(w_cfg.get("default_hours_per_day", 0.5)),
            )

        # Fans
        if profile.fan_count > 0:
            f_cfg = apps.get("fan", {})
            add_power(
                "fan",
                "Fans",
                profile.fan_count,
                float(f_cfg.get("default_watts", 75)),
                float(
                    profile.fan_hours_per_day
                    if profile.fan_hours_per_day is not None
                    else f_cfg.get("default_hours_per_day", 10)
                ),
            )

        # Water pump
        if profile.water_pump:
            p_cfg = apps.get("water_pump", {})
            add_power(
                "water_pump",
                "Water pump",
                1,
                float(p_cfg.get("default_watts", 750)),
                float(p_cfg.get("default_hours_per_day", 0.5)),
            )

        # Induction
        if profile.induction:
            i_cfg = apps.get("induction", {})
            add_power(
                "induction",
                "Induction cooktop",
                1,
                float(i_cfg.get("default_watts", 2000)),
                float(i_cfg.get("default_hours_per_day", 1)),
            )

        # EV
        if profile.ev_type in {EvType.TWO_WHEELER, EvType.BOTH}:
            kwh_day = float(apps.get("ev_2w", {}).get("default_kwh_per_day", 1.5))
            kwh = kwh_day * days
            steps.append(f"EV 2W charging: {kwh_day:g} kWh/day × {days:g} = {kwh:.2f} (estimated)")
            rows.append(
                (
                    "ev_2w",
                    "EV 2-wheeler home charging",
                    round(kwh, 4),
                    {"kwh_per_day": kwh_day, "days_per_month": days},
                )
            )
        if profile.ev_type in {EvType.FOUR_WHEELER, EvType.BOTH}:
            kwh_day = float(apps.get("ev_4w", {}).get("default_kwh_per_day", 6.0))
            kwh = kwh_day * days
            steps.append(f"EV 4W charging: {kwh_day:g} kWh/day × {days:g} = {kwh:.2f} (estimated)")
            rows.append(
                (
                    "ev_4w",
                    "EV 4-wheeler home charging",
                    round(kwh, 4),
                    {"kwh_per_day": kwh_day, "days_per_month": days},
                )
            )

        # People / lighting misc
        lighting = float(self._defaults.defaults.get("lighting_and_misc_kwh", 25))
        per_person = float(self._defaults.defaults.get("people_misc_kwh_per_person", 8))
        people_kwh = lighting + profile.people_count * per_person
        steps.append(
            f"Lighting/misc + people factor: {lighting:g} + "
            f"{profile.people_count}×{per_person:g} = {people_kwh:.2f} (estimated)"
        )
        rows.append(
            (
                "other",
                "Lighting / misc / people factor",
                round(people_kwh, 4),
                {
                    "people_count": profile.people_count,
                    "lighting_and_misc_kwh": lighting,
                    "people_misc_kwh_per_person": per_person,
                },
            )
        )

        estimated_total = round(sum(r[2] for r in rows), 4)
        if estimated_total <= 0:
            return ApplianceAnalysisResult(
                status="INVALID_INPUT",
                profile=profile,
                bill_units=bill_units,
                estimated_total_kwh=0,
                message="No appliances produced a positive estimate. Check inputs.",
                warnings=warnings,
            )

        bill_coverage = None
        if bill_units is not None and bill_units > 0:
            bill_coverage = round(estimated_total / bill_units, 4)
            steps.append(
                f"Estimated model total {estimated_total:g} kWh vs bill units {bill_units:g} "
                f"(coverage ratio {bill_coverage:g})."
            )
            if bill_coverage < 0.5 or bill_coverage > 1.8:
                warnings.append(
                    "Estimated appliance total differs a lot from bill units — "
                    "assumptions may need adjustment."
                )

        appliances: list[ApplianceEstimate] = []
        for appliance_id, label, kwh, assumptions in rows:
            share_est = round(100.0 * kwh / estimated_total, 2)
            share_bill = (
                round(100.0 * kwh / bill_units, 2)
                if bill_units is not None and bill_units > 0
                else None
            )
            appliances.append(
                ApplianceEstimate(
                    appliance_id=appliance_id,
                    label=label,
                    estimated_kwh_month=kwh,
                    share_of_estimated_total_percent=share_est,
                    share_of_bill_units_percent=share_bill,
                    assumptions=assumptions,
                )
            )

        appliances.sort(key=lambda a: a.estimated_kwh_month, reverse=True)
        top_loads = [a.appliance_id for a in appliances[:3]]

        return ApplianceAnalysisResult(
            status="ESTIMATED",
            profile=profile,
            bill_units=bill_units,
            estimated_total_kwh=estimated_total,
            bill_coverage_ratio=bill_coverage,
            appliances=appliances,
            top_loads=top_loads,
            explanation_steps=steps,
            warnings=warnings,
            message=(
                f"Estimated household model total ≈ {estimated_total:.1f} kWh/month "
                f"from stated assumptions. Top loads: {', '.join(top_loads)}."
            ),
        )

    def tailored_savings(
        self,
        profile: HouseholdApplianceProfile,
        *,
        bill_units: float,
        as_of: date,
        sanctioned_load_kw: float = 2.0,
    ) -> tuple[ApplianceAnalysisResult, list[SavingsEstimate]]:
        analysis = self.analyze(profile, bill_units=bill_units)
        if analysis.status != "ESTIMATED":
            return analysis, []

        estimates: list[SavingsEstimate] = []
        top = set(analysis.top_loads)

        # Map top loads → catalog recommendations with profile-based overrides
        if "ac" in top and profile.ac_count > 0:
            ac = next(a for a in analysis.appliances if a.appliance_id == "ac")
            estimates.append(
                self._savings.estimate_recommendation(
                    recommendation_id="ac_raise_temperature",
                    current_units=bill_units,
                    as_of=as_of,
                    sanctioned_load_kw=sanctioned_load_kw,
                    assumption_overrides={
                        "power_kw": (profile.ac_watts or 1500) / 1000.0 * profile.ac_count,
                        "hours_per_day": profile.ac_hours_per_day
                        or ac.assumptions.get("hours_per_day", 6),
                        "days_per_month": 30,
                        "reduction_fraction": 0.2,
                    },
                )
            )

        if "geyser" in top and profile.geyser:
            geyser = next(a for a in analysis.appliances if a.appliance_id == "geyser")
            estimates.append(
                self._savings.estimate_recommendation(
                    recommendation_id="geyser_reduce_runtime",
                    current_units=bill_units,
                    as_of=as_of,
                    sanctioned_load_kw=sanctioned_load_kw,
                    assumption_overrides={
                        "power_kw": (profile.geyser_watts or 2000) / 1000.0,
                        "hours_per_day": profile.geyser_hours_per_day
                        or geyser.assumptions.get("hours_per_day", 1),
                        "days_per_month": 30,
                        "reduction_fraction": 0.5,
                    },
                )
            )

        if "fan" in top and profile.fan_count > 0:
            estimates.append(
                self._savings.estimate_recommendation(
                    recommendation_id="replace_fans_bldc",
                    current_units=bill_units,
                    as_of=as_of,
                    sanctioned_load_kw=sanctioned_load_kw,
                    assumption_overrides={
                        "fan_count": profile.fan_count,
                        "old_watts": 75,
                        "new_watts": 35,
                        "hours_per_day": profile.fan_hours_per_day or 10,
                        "days_per_month": 30,
                    },
                )
            )

        if "refrigerator" in top and profile.refrigerator:
            estimates.append(
                self._savings.estimate_recommendation(
                    recommendation_id="fridge_efficient_use",
                    current_units=bill_units,
                    as_of=as_of,
                    sanctioned_load_kw=sanctioned_load_kw,
                )
            )

        # If nothing matched tops, fall back to full catalog ranking
        if not estimates:
            estimates = self._savings.recommend_all(
                current_units=bill_units,
                as_of=as_of,
                sanctioned_load_kw=sanctioned_load_kw,
            )

        estimates.sort(key=lambda e: e.estimated_monthly_saving or 0, reverse=True)
        return analysis, estimates
