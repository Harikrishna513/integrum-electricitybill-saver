"""
NetMeteringEngine — Milestone 15.

CONCEPT
  monthly consumption C + solar generation G
        │
        ▼
  estimate import/export registers (coincidence model)
        │
        ▼
  NET:  retail TariffEngine(max(0, C-G)) − export_credit(max(0, G-C)*PPA rate)
  GROSS: retail TariffEngine(C) − sale(G * solar tariff)
        │
        ▼
  estimated net cost / saving vs baseline retail bill

VNM / GNM: concept catalog only (Milestones 16 / 17).

Never claim official BESCOM settlement or PPA approval.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.domain.engines.tariff import TariffEngine
from app.domain.models.metering import (
    MeteringArrangement,
    MeteringCompareResult,
    MeteringConcept,
    MeteringSettlementResult,
    MeteringSettlementStatus,
    MeterRegisters,
)
from app.domain.models.tariff import TariffCalculationStatus
from app.infrastructure.rules.metering_rules import (
    MeteringArrangementsRule,
    get_default_metering_arrangements_rule,
)


_OK_TARIFF = {
    TariffCalculationStatus.CALCULATED,
    TariffCalculationStatus.REQUIRES_VERIFICATION,
}


class NetMeteringEngine:
    def __init__(
        self,
        rule: MeteringArrangementsRule | None = None,
        tariff_engine: TariffEngine | None = None,
    ) -> None:
        self._rule = rule or get_default_metering_arrangements_rule()
        self._tariff = tariff_engine or TariffEngine()

    @property
    def rule(self) -> MeteringArrangementsRule:
        return self._rule

    def list_concepts(self) -> list[MeteringConcept]:
        out: list[MeteringConcept] = []
        for key, payload in self._rule.concepts.items():
            out.append(
                MeteringConcept(
                    arrangement=MeteringArrangement(key),
                    label=str(payload.get("label", key)),
                    summary=str(payload.get("summary", "")).strip(),
                    scope=str(payload.get("scope", "")),
                    implementation_status=str(
                        payload.get("implementation_status", "UNKNOWN")
                    ),
                    diagram=str(payload.get("diagram", "")).strip(),
                )
            )
        return out

    def derive_registers(
        self,
        *,
        consumption_kwh: float,
        generation_kwh: float,
        coincidence_fraction: float | None = None,
    ) -> MeterRegisters:
        rule = self._rule
        f = (
            float(rule.settlement.get("default_coincidence_fraction", 1.0))
            if coincidence_fraction is None
            else float(coincidence_fraction)
        )
        f = min(1.0, max(0.0, f))
        self_consumed = min(consumption_kwh, generation_kwh) * f
        import_kwh = consumption_kwh - self_consumed
        export_kwh = generation_kwh - self_consumed
        return MeterRegisters(
            consumption_kwh=round(consumption_kwh, 4),
            generation_kwh=round(generation_kwh, 4),
            coincidence_fraction=f,
            self_consumed_kwh=round(self_consumed, 4),
            import_kwh=round(import_kwh, 4),
            export_kwh=round(export_kwh, 4),
            net_import_kwh=round(import_kwh - export_kwh, 4),
        )

    def settle(
        self,
        *,
        arrangement: MeteringArrangement,
        consumption_kwh: float,
        generation_kwh: float,
        as_of: date,
        sanctioned_load_kw: float = 3.0,
        coincidence_fraction: float | None = None,
        availed_cfa: bool = False,
        discom: str = "BESCOM",
        category: str = "DOMESTIC",
        tariff_code: str | None = "LT-1",
    ) -> MeteringSettlementResult:
        rule = self._rule
        warnings = [
            rule.user_messages.get(
                "estimate_only",
                "Estimated metering settlement only.",
            )
        ]
        steps: list[str] = []

        if consumption_kwh < 0 or generation_kwh < 0 or sanctioned_load_kw < 0:
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.INVALID_INPUT,
                arrangement=arrangement,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message="consumption_kwh, generation_kwh, sanctioned_load_kw must be ≥ 0.",
            )

        if category.upper() != "DOMESTIC":
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.UNSUPPORTED_CATEGORY,
                arrangement=arrangement,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message="v1 metering settlement supports DOMESTIC only.",
            )

        if arrangement == MeteringArrangement.VIRTUAL_NET_METERING:
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.CONCEPT_ONLY,
                arrangement=arrangement,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message=rule.user_messages.get(
                    "vnm_later",
                    "VNM analysis is Milestone 16.",
                ),
                assumptions={"concept": rule.concepts.get("VIRTUAL_NET_METERING")},
            )

        if arrangement == MeteringArrangement.GROUP_NET_METERING:
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.CONCEPT_ONLY,
                arrangement=arrangement,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message=rule.user_messages.get(
                    "gnm_later",
                    "GNM analysis is Milestone 17.",
                ),
                assumptions={"concept": rule.concepts.get("GROUP_NET_METERING")},
            )

        if not rule.applies_on(as_of):
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.INVALID_INPUT,
                arrangement=arrangement,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                warnings=warnings,
                message=f"No active metering rule for {as_of.isoformat()}.",
            )

        registers = self.derive_registers(
            consumption_kwh=consumption_kwh,
            generation_kwh=generation_kwh,
            coincidence_fraction=coincidence_fraction,
        )
        steps.append(
            f"Registers (est.): import={registers.import_kwh:g} kWh, "
            f"export={registers.export_kwh:g} kWh, "
            f"net_import={registers.net_import_kwh:g} kWh "
            f"(coincidence={registers.coincidence_fraction:g})."
        )
        steps.append(
            "Identity check: import − export = consumption − generation "
            f"→ {registers.net_import_kwh:g}."
        )

        export_rate = self._export_rate(availed_cfa=availed_cfa)
        steps.append(
            f"Export/sale tariff assumption: ₹{export_rate:g}/kWh "
            f"(availed_cfa={availed_cfa})."
        )
        warnings.append(
            "Export tariff is bootstrap REQUIRES_VERIFICATION — confirm against PPA."
        )
        warnings.append(
            rule.user_messages.get(
                "fixed_charges_remain",
                "Fixed charges may still apply at zero net import.",
            )
        )
        if rule.verification_status != "VERIFIED":
            warnings.append(
                f"Metering rule verification_status={rule.verification_status}."
            )

        baseline = self._tariff.calculate(
            discom=discom,
            category=category,
            as_of=as_of,
            units=consumption_kwh,
            sanctioned_load_kw=sanctioned_load_kw,
            tariff_code=tariff_code,
        )
        if baseline.status not in _OK_TARIFF or baseline.estimated_total is None:
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.TARIFF_UNAVAILABLE,
                arrangement=arrangement,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                registers=registers,
                export_tariff_inr_per_kwh=export_rate,
                availed_cfa_for_export_tariff=availed_cfa,
                explanation_steps=steps,
                warnings=warnings + baseline.warnings,
                message="Baseline retail tariff calculation failed.",
            )

        if arrangement == MeteringArrangement.NET_METERING:
            return self._settle_net(
                registers=registers,
                baseline_total=float(baseline.estimated_total),
                export_rate=export_rate,
                availed_cfa=availed_cfa,
                as_of=as_of,
                sanctioned_load_kw=sanctioned_load_kw,
                discom=discom,
                category=category,
                tariff_code=tariff_code,
                steps=steps,
                warnings=warnings,
                baseline=baseline,
            )

        if arrangement == MeteringArrangement.GROSS_METERING:
            return self._settle_gross(
                registers=registers,
                baseline_total=float(baseline.estimated_total),
                export_rate=export_rate,
                availed_cfa=availed_cfa,
                as_of=as_of,
                steps=steps,
                warnings=warnings,
                baseline=baseline,
            )

        return MeteringSettlementResult(
            status=MeteringSettlementStatus.INVALID_INPUT,
            arrangement=arrangement,
            as_of=as_of,
            message=f"Unsupported arrangement: {arrangement}",
            warnings=warnings,
        )

    def compare(
        self,
        *,
        consumption_kwh: float,
        generation_kwh: float,
        as_of: date,
        sanctioned_load_kw: float = 3.0,
        coincidence_fraction: float | None = None,
        availed_cfa: bool = False,
        discom: str = "BESCOM",
        category: str = "DOMESTIC",
        tariff_code: str | None = "LT-1",
    ) -> MeteringCompareResult:
        common = dict(
            consumption_kwh=consumption_kwh,
            generation_kwh=generation_kwh,
            as_of=as_of,
            sanctioned_load_kw=sanctioned_load_kw,
            coincidence_fraction=coincidence_fraction,
            availed_cfa=availed_cfa,
            discom=discom,
            category=category,
            tariff_code=tariff_code,
        )
        net = self.settle(arrangement=MeteringArrangement.NET_METERING, **common)
        gross = self.settle(arrangement=MeteringArrangement.GROSS_METERING, **common)

        if (
            net.status != MeteringSettlementStatus.ESTIMATED
            or gross.status != MeteringSettlementStatus.ESTIMATED
        ):
            status = "INVALID_INPUT"
            if (
                net.status == MeteringSettlementStatus.TARIFF_UNAVAILABLE
                or gross.status == MeteringSettlementStatus.TARIFF_UNAVAILABLE
            ):
                status = "TARIFF_UNAVAILABLE"
            return MeteringCompareResult(
                status=status,  # type: ignore[arg-type]
                as_of=as_of,
                net=net,
                gross=gross,
                preferred_hint="Could not compare — see individual settlement statuses.",
                message="Net vs Gross comparison incomplete.",
            )

        net_cost = net.estimated_net_cost_inr or 0
        gross_cost = gross.estimated_net_cost_inr or 0
        if net_cost < gross_cost:
            hint = (
                f"Under these assumptions, NET looks cheaper "
                f"(₹{net_cost:,.0f} vs GROSS ₹{gross_cost:,.0f} net monthly cost)."
            )
        elif gross_cost < net_cost:
            hint = (
                f"Under these assumptions, GROSS looks cheaper "
                f"(₹{gross_cost:,.0f} vs NET ₹{net_cost:,.0f} net monthly cost)."
            )
        else:
            hint = "Under these assumptions, NET and GROSS net monthly cost are similar."

        return MeteringCompareResult(
            status="ESTIMATED",
            as_of=as_of,
            net=net,
            gross=gross,
            preferred_hint=hint,
            message="Estimated Net vs Gross comparison (not a BESCOM recommendation).",
        )

    def _settle_net(
        self,
        *,
        registers: MeterRegisters,
        baseline_total: float,
        export_rate: float,
        availed_cfa: bool,
        as_of: date,
        sanctioned_load_kw: float,
        discom: str,
        category: str,
        tariff_code: str | None,
        steps: list[str],
        warnings: list[str],
        baseline: Any,
    ) -> MeteringSettlementResult:
        rule = self._rule
        net_import = registers.net_import_kwh
        retail_units = max(0.0, net_import)
        steps.append(
            f"NET settlement: retail units billed = max(0, net_import) = {retail_units:g} kWh."
        )

        retail = self._tariff.calculate(
            discom=discom,
            category=category,
            as_of=as_of,
            units=retail_units,
            sanctioned_load_kw=sanctioned_load_kw,
            tariff_code=tariff_code,
        )
        if retail.status not in _OK_TARIFF or retail.estimated_total is None:
            return MeteringSettlementResult(
                status=MeteringSettlementStatus.TARIFF_UNAVAILABLE,
                arrangement=MeteringArrangement.NET_METERING,
                as_of=as_of,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                registers=registers,
                export_tariff_inr_per_kwh=export_rate,
                availed_cfa_for_export_tariff=availed_cfa,
                explanation_steps=steps,
                warnings=warnings + retail.warnings,
                message="Net-metering retail bill calculation failed.",
            )

        if baseline.status == TariffCalculationStatus.REQUIRES_VERIFICATION:
            warnings.extend(baseline.warnings)

        net_export = max(0.0, -net_import)
        export_credit = round(net_export * export_rate, 2)
        if net_export > 0:
            steps.append(
                f"Net export {net_export:g} kWh × ₹{export_rate:g} = ₹{export_credit:.2f} credit."
            )
        else:
            steps.append("No net export — export credit = ₹0.")

        retail_total = float(retail.estimated_total)
        net_cost = round(retail_total - export_credit, 2)
        saving = round(baseline_total - net_cost, 2)
        steps.append(
            f"Net monthly cost ≈ retail ₹{retail_total:.2f} − credit ₹{export_credit:.2f} "
            f"= ₹{net_cost:.2f}."
        )
        steps.append(
            f"Saving vs baseline retail ₹{baseline_total:.2f} → ₹{saving:.2f}/month."
        )

        return MeteringSettlementResult(
            status=MeteringSettlementStatus.ESTIMATED,
            arrangement=MeteringArrangement.NET_METERING,
            as_of=as_of,
            rule_version=rule.rule_version,
            verification_status=rule.verification_status,
            source=rule.source,
            registers=registers,
            export_tariff_inr_per_kwh=export_rate,
            availed_cfa_for_export_tariff=availed_cfa,
            baseline_retail_bill_inr=round(baseline_total, 2),
            retail_bill_after_arrangement_inr=round(retail_total, 2),
            export_credit_or_sale_inr=export_credit,
            estimated_net_cost_inr=net_cost,
            estimated_monthly_saving_inr=saving,
            tariff_rule_version=retail.rule_version,
            tariff_verification_status=retail.verification_status,
            explanation_steps=steps,
            warnings=warnings,
            assumptions=self._assumptions(availed_cfa=availed_cfa, export_rate=export_rate),
            message=(
                f"Estimated NET metering: ~₹{saving:,.0f}/month vs full retail "
                f"(net cost ~₹{net_cost:,.0f})."
            ),
        )

    def _settle_gross(
        self,
        *,
        registers: MeterRegisters,
        baseline_total: float,
        export_rate: float,
        availed_cfa: bool,
        as_of: date,
        steps: list[str],
        warnings: list[str],
        baseline: Any,
    ) -> MeteringSettlementResult:
        rule = self._rule
        sale = round(registers.generation_kwh * export_rate, 2)
        steps.append(
            f"GROSS: sell all generation {registers.generation_kwh:g} kWh × "
            f"₹{export_rate:g} = ₹{sale:.2f}."
        )
        steps.append(
            f"GROSS: pay full retail for consumption → ₹{baseline_total:.2f}."
        )
        if baseline.status == TariffCalculationStatus.REQUIRES_VERIFICATION:
            warnings.extend(baseline.warnings)

        net_cost = round(baseline_total - sale, 2)
        saving = round(baseline_total - net_cost, 2)  # equals sale under this model
        steps.append(
            f"Net monthly cost ≈ retail ₹{baseline_total:.2f} − sale ₹{sale:.2f} "
            f"= ₹{net_cost:.2f}."
        )

        return MeteringSettlementResult(
            status=MeteringSettlementStatus.ESTIMATED,
            arrangement=MeteringArrangement.GROSS_METERING,
            as_of=as_of,
            rule_version=rule.rule_version,
            verification_status=rule.verification_status,
            source=rule.source,
            registers=registers,
            export_tariff_inr_per_kwh=export_rate,
            availed_cfa_for_export_tariff=availed_cfa,
            baseline_retail_bill_inr=round(baseline_total, 2),
            retail_bill_after_arrangement_inr=round(baseline_total, 2),
            export_credit_or_sale_inr=sale,
            estimated_net_cost_inr=net_cost,
            estimated_monthly_saving_inr=saving,
            tariff_rule_version=baseline.rule_version,
            tariff_verification_status=baseline.verification_status,
            explanation_steps=steps,
            warnings=warnings,
            assumptions=self._assumptions(availed_cfa=availed_cfa, export_rate=export_rate),
            message=(
                f"Estimated GROSS metering: generation sale ~₹{sale:,.0f}/month; "
                f"net cost ~₹{net_cost:,.0f}."
            ),
        )

    def _export_rate(self, *, availed_cfa: bool) -> float:
        block = self._rule.export_tariffs_inr_per_kwh.get(
            "domestic_1_to_10_kwp", {}
        )
        key = "with_cfa" if availed_cfa else "without_cfa"
        return float(block.get(key, 0.0))

    def _assumptions(self, *, availed_cfa: bool, export_rate: float) -> dict[str, Any]:
        return {
            "rule_version": self._rule.rule_version,
            "verification_status": self._rule.verification_status,
            "settlement": self._rule.settlement,
            "availed_cfa": availed_cfa,
            "export_tariff_inr_per_kwh": export_rate,
            "export_tariff_block": self._rule.export_tariffs_inr_per_kwh.get(
                "domestic_1_to_10_kwp"
            ),
        }
