"""
TariffEngine — Milestone 10.

CONCEPT
  Inputs: discom, category, as_of date, units, load
        │
        ▼
  TariffRuleRepository.get_rule(...)
        │
        ▼
  Deterministic Python charge calculation
        │
        ▼
  TariffCalculationResult (with rule_version + verification_status)

Gemini must never compute these amounts.
"""

from __future__ import annotations

from datetime import date

from app.domain.models.tariff import (
    ChargeLine,
    TariffCalculationResult,
    TariffCalculationStatus,
    TariffRule,
)
from app.infrastructure.rules.tariff_rules import (
    TariffRuleRepository,
    get_default_tariff_repository,
)


class TariffEngine:
    def __init__(self, repository: TariffRuleRepository | None = None) -> None:
        self._repository = repository or get_default_tariff_repository()

    def calculate(
        self,
        *,
        discom: str = "BESCOM",
        category: str,
        as_of: date,
        units: float,
        sanctioned_load_kw: float = 1.0,
        tariff_code: str | None = None,
    ) -> TariffCalculationResult:
        if units < 0 or sanctioned_load_kw < 0:
            return TariffCalculationResult(
                status=TariffCalculationStatus.INVALID_INPUT,
                discom=discom.upper(),
                category=category.upper(),
                as_of=as_of,
                units=units,
                sanctioned_load_kw=sanctioned_load_kw,
                message="Units and sanctioned load must be non-negative.",
            )

        if category.upper() != "DOMESTIC":
            return TariffCalculationResult(
                status=TariffCalculationStatus.UNSUPPORTED_CATEGORY,
                discom=discom.upper(),
                category=category.upper(),
                as_of=as_of,
                units=units,
                sanctioned_load_kw=sanctioned_load_kw,
                message=(
                    f"Category {category.upper()} is not supported by the v1 tariff engine. "
                    "Domestic only for now."
                ),
            )

        rule = self._repository.get_rule(
            discom=discom,
            category=category,
            as_of=as_of,
            tariff_code=tariff_code,
        )
        if rule is None:
            return TariffCalculationResult(
                status=TariffCalculationStatus.RULE_NOT_FOUND,
                discom=discom.upper(),
                category=category.upper(),
                as_of=as_of,
                units=units,
                sanctioned_load_kw=sanctioned_load_kw,
                message=(
                    f"No tariff rule found for {discom}/{category} on {as_of.isoformat()}. "
                    "Add a versioned YAML rule or verify the bill date."
                ),
            )

        return self._calculate_with_rule(
            rule=rule,
            units=units,
            sanctioned_load_kw=sanctioned_load_kw,
            as_of=as_of,
        )

    def _calculate_with_rule(
        self,
        *,
        rule: TariffRule,
        units: float,
        sanctioned_load_kw: float,
        as_of: date,
    ) -> TariffCalculationResult:
        steps: list[str] = []
        lines: list[ChargeLine] = []
        warnings: list[str] = []

        if rule.verification_status != "VERIFIED":
            warnings.append(
                f"Rule {rule.rule_version} has verification_status="
                f"{rule.verification_status}. Treat amounts as illustrative until "
                "confirmed against the official KERC/BESCOM tariff order."
            )

        energy, energy_detail = self._energy_charge(rule, units, steps)
        lines.append(
            ChargeLine(
                code="ENERGY",
                description="Energy charges",
                amount=round(energy, 2),
                detail=energy_detail,
            )
        )

        fixed, fixed_detail = self._fixed_charge(rule, sanctioned_load_kw, steps)
        lines.append(
            ChargeLine(
                code="FIXED",
                description="Fixed charges",
                amount=round(fixed, 2),
                detail=fixed_detail,
            )
        )

        surcharge_total = 0.0
        for surcharge in rule.surcharges:
            amount, detail = self._surcharge(surcharge.model_dump(), units, steps)
            surcharge_total += amount
            lines.append(
                ChargeLine(
                    code=surcharge.code,
                    description=surcharge.description or surcharge.code,
                    amount=round(amount, 2),
                    detail=detail,
                )
            )

        tax, tax_detail = self._tax(rule, energy, fixed, steps)
        lines.append(
            ChargeLine(
                code="ELECTRICITY_TAX",
                description="Electricity tax",
                amount=round(tax, 2),
                detail=tax_detail,
            )
        )

        total = round(energy + fixed + surcharge_total + tax, 2)
        steps.append(
            f"Estimated total = energy {energy:.2f} + fixed {fixed:.2f} "
            f"+ surcharges {surcharge_total:.2f} + tax {tax:.2f} = {total:.2f}"
        )

        status = TariffCalculationStatus.CALCULATED
        message = (
            f"Calculated with rule {rule.rule_version} for {as_of.isoformat()}. "
            f"verification_status={rule.verification_status}."
        )
        if rule.verification_status != "VERIFIED":
            # Still return numbers for learning, but mark clearly.
            status = TariffCalculationStatus.REQUIRES_VERIFICATION
            message = (
                "Calculation completed using an UNVERIFIED bootstrap rule. "
                "Do not treat this as an official BESCOM bill recomputation until "
                "the rule is verified against KERC/BESCOM documents."
            )

        return TariffCalculationResult(
            status=status,
            discom=rule.discom,
            category=rule.category,
            as_of=as_of,
            units=units,
            sanctioned_load_kw=sanctioned_load_kw,
            rule_version=rule.rule_version,
            verification_status=rule.verification_status,
            source=rule.source,
            energy_charge=round(energy, 2),
            fixed_charge=round(fixed, 2),
            electricity_tax=round(tax, 2),
            surcharge_total=round(surcharge_total, 2),
            estimated_total=total,
            lines=lines,
            explanation_steps=steps,
            warnings=warnings,
            message=message,
        )

    def _energy_charge(
        self,
        rule: TariffRule,
        units: float,
        steps: list[str],
    ) -> tuple[float, str]:
        energy = rule.energy
        if energy.model == "flat":
            rate = float(energy.rate_per_kwh or 0.0)
            amount = units * rate
            detail = f"{units:g} × ₹{rate:g}/kWh"
            steps.append(f"Energy (flat): {detail} = ₹{amount:.2f}")
            return amount, detail

        if energy.model != "telescopic_slabs":
            steps.append(f"Unsupported energy model: {energy.model}; treating as 0.")
            return 0.0, "unsupported_energy_model"

        remaining = units
        previous_cap = 0.0
        amount = 0.0
        parts: list[str] = []
        for slab in energy.slabs:
            if remaining <= 0:
                break
            if slab.up_to is None:
                slab_units = remaining
            else:
                slab_width = max(0.0, float(slab.up_to) - previous_cap)
                slab_units = min(remaining, slab_width)
                previous_cap = float(slab.up_to)
            if slab_units <= 0:
                continue
            slab_amount = slab_units * float(slab.rate_per_kwh)
            amount += slab_amount
            parts.append(f"{slab_units:g}×{slab.rate_per_kwh:g}")
            steps.append(
                f"Energy slab: {slab_units:g} units × ₹{slab.rate_per_kwh:g} = ₹{slab_amount:.2f}"
            )
            remaining -= slab_units

        detail = " + ".join(parts) if parts else "0"
        steps.append(f"Energy total = ₹{amount:.2f}")
        return amount, detail

    def _fixed_charge(
        self,
        rule: TariffRule,
        load_kw: float,
        steps: list[str],
    ) -> tuple[float, str]:
        fixed = rule.fixed_charge
        if fixed.model == "flat":
            amount = float(fixed.flat_amount or 0.0)
            detail = f"flat ₹{amount:g}"
            steps.append(f"Fixed charge (flat): {detail}")
            return amount, detail

        billable_kw = max(float(load_kw), float(fixed.minimum_kw or 1.0))
        rate = float(fixed.rate_per_kw or 0.0)
        amount = billable_kw * rate
        detail = f"{billable_kw:g} kW × ₹{rate:g}/kW"
        steps.append(f"Fixed charge: {detail} = ₹{amount:.2f}")
        return amount, detail

    def _surcharge(
        self,
        surcharge: dict,
        units: float,
        steps: list[str],
    ) -> tuple[float, str]:
        model = surcharge.get("model")
        code = surcharge.get("code", "SURCHARGE")
        if model == "per_kwh":
            rate = float(surcharge.get("rate_per_kwh") or 0.0)
            amount = units * rate
            detail = f"{units:g} × ₹{rate:g}"
            steps.append(f"Surcharge {code}: {detail} = ₹{amount:.2f}")
            return amount, detail
        amount = float(surcharge.get("flat_amount") or 0.0)
        detail = f"flat ₹{amount:g}"
        steps.append(f"Surcharge {code}: {detail}")
        return amount, detail

    def _tax(
        self,
        rule: TariffRule,
        energy: float,
        fixed: float,
        steps: list[str],
    ) -> tuple[float, str]:
        tax = rule.electricity_tax
        if tax.model == "none":
            steps.append("Electricity tax: none")
            return 0.0, "none"
        if tax.model == "percent_of_energy":
            base = energy
        else:
            # default percent_of_energy_plus_fixed
            base = energy + fixed
        amount = base * (float(tax.percent) / 100.0)
        detail = f"{tax.percent:g}% of ₹{base:.2f}"
        steps.append(f"Electricity tax: {detail} = ₹{amount:.2f}")
        return amount, detail
