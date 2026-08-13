"""
SavingsEngine — Milestone 12.

CONCEPT
  units_saved (from explicit assumptions)
        │
        ▼
  TariffEngine.calculate(current_units)
  TariffEngine.calculate(current_units - units_saved)
        │
        ▼
  estimated_monthly_saving = old_total - new_total

Gemini may later explain this JSON — it must not invent the ₹ number.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain.engines.tariff import TariffEngine
from app.domain.models.savings import (
    AssumptionSet,
    RecommendationTemplate,
    SavingsConfidence,
    SavingsEstimate,
    SavingsStatus,
)
from app.domain.models.tariff import TariffCalculationStatus
from app.infrastructure.rules.savings_catalog import (
    SavingsCatalog,
    get_default_savings_catalog,
)


class SavingsEngine:
    def __init__(
        self,
        tariff_engine: TariffEngine | None = None,
        catalog: SavingsCatalog | None = None,
    ) -> None:
        self._tariff = tariff_engine or TariffEngine()
        self._catalog = catalog or get_default_savings_catalog()

    @property
    def catalog(self) -> SavingsCatalog:
        return self._catalog

    def estimate_from_units_saved(
        self,
        *,
        title: str,
        current_units: float,
        units_saved: float,
        as_of: date,
        sanctioned_load_kw: float = 1.0,
        discom: str = "BESCOM",
        category: str = "DOMESTIC",
        tariff_code: str | None = "LT-1",
        assumptions: AssumptionSet | None = None,
        recommendation_id: str | None = None,
        confidence: SavingsConfidence = SavingsConfidence.MEDIUM,
    ) -> SavingsEstimate:
        warnings: list[str] = [
            "This is an ESTIMATE based on stated assumptions — not a measured smart-meter result.",
            "Tariff bootstrap rules may be UNVERIFIED; ₹ figures inherit that caveat.",
        ]
        steps: list[str] = []

        if current_units < 0 or units_saved < 0:
            return SavingsEstimate(
                status=SavingsStatus.INVALID_INPUT,
                recommendation_id=recommendation_id,
                title=title,
                assumptions=assumptions
                or AssumptionSet(description="invalid", values={}),
                current_units=current_units,
                estimated_new_units=current_units,
                units_saved=units_saved,
                confidence=confidence,
                message="current_units and units_saved must be non-negative.",
                warnings=warnings,
            )

        if units_saved > current_units:
            warnings.append(
                "units_saved > current_units; clamping new usage to 0 for this estimate."
            )
            units_saved = current_units

        new_units = round(current_units - units_saved, 4)
        steps.append(
            f"Usage change: {current_units:g} → {new_units:g} units "
            f"(saved {units_saved:g} kWh)."
        )

        old_bill = self._tariff.calculate(
            discom=discom,
            category=category,
            as_of=as_of,
            units=current_units,
            sanctioned_load_kw=sanctioned_load_kw,
            tariff_code=tariff_code,
        )
        new_bill = self._tariff.calculate(
            discom=discom,
            category=category,
            as_of=as_of,
            units=new_units,
            sanctioned_load_kw=sanctioned_load_kw,
            tariff_code=tariff_code,
        )

        if old_bill.estimated_total is None or new_bill.estimated_total is None:
            return SavingsEstimate(
                status=SavingsStatus.TARIFF_UNAVAILABLE,
                recommendation_id=recommendation_id,
                title=title,
                assumptions=assumptions
                or AssumptionSet(description="tariff unavailable", values={}),
                current_units=current_units,
                estimated_new_units=new_units,
                units_saved=units_saved,
                tariff_rule_version=old_bill.rule_version,
                tariff_verification_status=old_bill.verification_status,
                as_of=as_of,
                confidence=confidence,
                explanation_steps=steps + old_bill.explanation_steps,
                warnings=warnings + old_bill.warnings,
                message=old_bill.message or "Tariff engine could not estimate bills.",
            )

        monthly = round(old_bill.estimated_total - new_bill.estimated_total, 2)
        annual = round(monthly * 12.0, 2)
        steps.append(
            f"Old bill estimate ₹{old_bill.estimated_total:.2f} "
            f"(rule {old_bill.rule_version})."
        )
        steps.append(
            f"New bill estimate ₹{new_bill.estimated_total:.2f} "
            f"after reducing {units_saved:g} units."
        )
        steps.append(
            f"Estimated monthly saving = "
            f"{old_bill.estimated_total:.2f} - {new_bill.estimated_total:.2f} "
            f"= ₹{monthly:.2f}"
        )
        steps.append(f"Estimated annual saving ≈ ₹{monthly:.2f} × 12 = ₹{annual:.2f}")

        if old_bill.status == TariffCalculationStatus.REQUIRES_VERIFICATION:
            warnings.extend(old_bill.warnings)

        return SavingsEstimate(
            status=SavingsStatus.ESTIMATED,
            recommendation_id=recommendation_id,
            title=title,
            assumptions=assumptions
            or AssumptionSet(
                description="Direct units_saved input",
                values={"units_saved": units_saved},
            ),
            current_units=current_units,
            estimated_new_units=new_units,
            units_saved=units_saved,
            current_bill_estimate=old_bill.estimated_total,
            new_bill_estimate=new_bill.estimated_total,
            estimated_monthly_saving=monthly,
            estimated_annual_saving=annual,
            tariff_rule_version=old_bill.rule_version,
            tariff_verification_status=old_bill.verification_status,
            as_of=as_of,
            confidence=confidence,
            explanation_steps=steps,
            warnings=warnings,
            message=(
                f"Estimated saving ≈ ₹{monthly:.2f}/month (₹{annual:.2f}/year) "
                f"under stated assumptions and tariff rule {old_bill.rule_version}."
            ),
        )

    def estimate_recommendation(
        self,
        *,
        recommendation_id: str,
        current_units: float,
        as_of: date,
        sanctioned_load_kw: float = 1.0,
        discom: str = "BESCOM",
        category: str = "DOMESTIC",
        tariff_code: str | None = "LT-1",
        assumption_overrides: dict[str, Any] | None = None,
    ) -> SavingsEstimate:
        template = self._catalog.get(recommendation_id)
        if template is None:
            return SavingsEstimate(
                status=SavingsStatus.INVALID_INPUT,
                recommendation_id=recommendation_id,
                title=recommendation_id,
                assumptions=AssumptionSet(description="unknown recommendation", values={}),
                current_units=current_units,
                estimated_new_units=current_units,
                units_saved=0,
                message=f"Unknown recommendation_id: {recommendation_id}",
            )

        merged = dict(template.default_assumptions)
        if assumption_overrides:
            merged.update(assumption_overrides)

        units_saved, detail = self._kwh_from_template(template, merged)
        confidence = (
            SavingsConfidence.HIGH
            if assumption_overrides
            else SavingsConfidence.MEDIUM
        )
        assumptions = AssumptionSet(
            description=f"{template.title} ({template.formula})",
            values={**merged, "computed_units_saved": units_saved, "detail": detail},
        )
        return self.estimate_from_units_saved(
            title=template.title,
            current_units=current_units,
            units_saved=units_saved,
            as_of=as_of,
            sanctioned_load_kw=sanctioned_load_kw,
            discom=discom,
            category=category,
            tariff_code=tariff_code,
            assumptions=assumptions,
            recommendation_id=template.id,
            confidence=confidence,
        )

    def recommend_all(
        self,
        *,
        current_units: float,
        as_of: date,
        sanctioned_load_kw: float = 1.0,
        discom: str = "BESCOM",
        category: str = "DOMESTIC",
        tariff_code: str | None = "LT-1",
    ) -> list[SavingsEstimate]:
        estimates = [
            self.estimate_recommendation(
                recommendation_id=item.id,
                current_units=current_units,
                as_of=as_of,
                sanctioned_load_kw=sanctioned_load_kw,
                discom=discom,
                category=category,
                tariff_code=tariff_code,
            )
            for item in self._catalog.recommendations
        ]
        estimates.sort(
            key=lambda e: e.estimated_monthly_saving or 0.0,
            reverse=True,
        )
        return estimates

    def _kwh_from_template(
        self,
        template: RecommendationTemplate,
        assumptions: dict[str, Any],
    ) -> tuple[float, str]:
        if template.id in {"geyser_reduce_runtime", "ac_raise_temperature"}:
            power_kw = float(assumptions["power_kw"])
            hours = float(assumptions["hours_per_day"])
            days = float(assumptions["days_per_month"])
            frac = float(assumptions["reduction_fraction"])
            kwh = power_kw * hours * days * frac
            detail = (
                f"{power_kw:g} kW × {hours:g} h/day × {days:g} days × "
                f"{frac:g} reduction"
            )
            return round(kwh, 4), detail

        if template.id == "replace_fans_bldc":
            count = float(assumptions["fan_count"])
            old_w = float(assumptions["old_watts"])
            new_w = float(assumptions["new_watts"])
            hours = float(assumptions["hours_per_day"])
            days = float(assumptions["days_per_month"])
            kwh = count * ((old_w - new_w) / 1000.0) * hours * days
            detail = (
                f"{count:g} fans × ({old_w:g}-{new_w:g}) W / 1000 × "
                f"{hours:g} h × {days:g} days"
            )
            return round(kwh, 4), detail

        if template.id == "fridge_efficient_use":
            base = float(assumptions["monthly_fridge_kwh"])
            frac = float(assumptions["reduction_fraction"])
            kwh = base * frac
            detail = f"{base:g} kWh/month × {frac:g} reduction"
            return round(kwh, 4), detail

        # Generic fallback if catalog adds unknown formulas later
        if "units_saved" in assumptions:
            return float(assumptions["units_saved"]), "units_saved override"
        return 0.0, "no_formula_match"
