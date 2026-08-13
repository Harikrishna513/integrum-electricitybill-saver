"""
GruhaJyothiEngine — Milestone 11.

Separate from TariffEngine on purpose.

Inputs may include:
  - category
  - baseline FY 2022-23 average units (required for entitlement math)
  - current month units (optional)
  - subsidy line seen on bill / user says enrolled (optional signals)

Never:
  - invent baseline from a single recent bill
  - say "approved"
"""

from __future__ import annotations

from datetime import date

from app.domain.models.gruha_jyothi import (
    ConditionCheck,
    GruhaJyothiAssessment,
    GruhaJyothiStatus,
)
from app.infrastructure.rules.scheme_rules import (
    GruhaJyothiRule,
    get_default_gruha_jyothi_rule,
)


class GruhaJyothiEngine:
    def __init__(self, rule: GruhaJyothiRule | None = None) -> None:
        self._rule = rule or get_default_gruha_jyothi_rule()

    def assess(
        self,
        *,
        category: str,
        as_of: date | None = None,
        baseline_fy_2022_23_avg_units: float | None = None,
        current_units: float | None = None,
        subsidy_line_seen_on_bill: bool | None = None,
        consumer_declares_enrolled: bool | None = None,
    ) -> GruhaJyothiAssessment:
        as_of = as_of or date.today()
        rule = self._rule
        steps: list[str] = []
        warnings: list[str] = [
            rule.user_messages.get(
                "never_approval",
                "Preliminary check only — not an official approval.",
            )
        ]
        conditions: list[ConditionCheck] = []
        missing: list[str] = []

        if not rule.applies_on(as_of):
            return GruhaJyothiAssessment(
                status=GruhaJyothiStatus.NOT_APPLICABLE,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                as_of=as_of,
                category=category.upper(),
                user_message=(
                    f"No active Gruha Jyothi rule for {as_of.isoformat()} "
                    f"under {rule.rule_version}."
                ),
                warnings=warnings,
            )

        category_u = category.upper()
        is_domestic = category_u in {c.upper() for c in rule.eligible_categories}
        conditions.append(
            ConditionCheck(
                code="DOMESTIC_CATEGORY",
                passed=is_domestic,
                detail=(
                    f"Category {category_u} is domestic-eligible."
                    if is_domestic
                    else f"Category {category_u} is not in {rule.eligible_categories}."
                ),
            )
        )
        steps.append(conditions[-1].detail)

        if not is_domestic:
            return GruhaJyothiAssessment(
                status=GruhaJyothiStatus.NOT_APPLICABLE,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                as_of=as_of,
                category=category_u,
                conditions=conditions,
                explanation_steps=steps,
                warnings=warnings,
                user_message=rule.user_messages.get(
                    "not_domestic",
                    "Gruha Jyothi is for domestic/residential connections.",
                ),
            )

        if baseline_fy_2022_23_avg_units is None:
            missing.append("baseline_fy_2022_23_avg_units")
            conditions.append(
                ConditionCheck(
                    code="BASELINE_FY_2022_23",
                    passed=None,
                    detail="FY 2022-23 average monthly units not provided.",
                )
            )
            steps.append(conditions[-1].detail)
            return GruhaJyothiAssessment(
                status=GruhaJyothiStatus.INSUFFICIENT_INFORMATION,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                as_of=as_of,
                category=category_u,
                current_units=current_units,
                subsidy_line_seen_on_bill=subsidy_line_seen_on_bill,
                consumer_declares_enrolled=consumer_declares_enrolled,
                hard_cap_units=rule.entitlement.hard_cap_units,
                conditions=conditions,
                missing_inputs=missing,
                explanation_steps=steps,
                warnings=warnings,
                user_message=rule.user_messages.get(
                    "insufficient_baseline",
                    "Need FY 2022-23 baseline to estimate entitlement.",
                ),
            )

        if baseline_fy_2022_23_avg_units < 0:
            return GruhaJyothiAssessment(
                status=GruhaJyothiStatus.CONDITIONS_NOT_MET,
                rule_version=rule.rule_version,
                verification_status=rule.verification_status,
                source=rule.source,
                as_of=as_of,
                category=category_u,
                baseline_fy_2022_23_avg_units=baseline_fy_2022_23_avg_units,
                user_message="Baseline units cannot be negative.",
                warnings=warnings,
            )

        entitlement = self._compute_entitlement(baseline_fy_2022_23_avg_units, steps)
        conditions.append(
            ConditionCheck(
                code="BASELINE_PROVIDED",
                passed=True,
                detail=(
                    f"Baseline FY 2022-23 average = {baseline_fy_2022_23_avg_units:g} units/month."
                ),
            )
        )
        conditions.append(
            ConditionCheck(
                code="ENTITLEMENT_COMPUTED",
                passed=True,
                detail=(
                    f"Computed entitlement = {entitlement:g} units "
                    f"(cap {rule.entitlement.hard_cap_units:g})."
                ),
            )
        )

        units_within = units_beyond = covered = None
        if current_units is not None:
            units_within = min(current_units, entitlement)
            units_beyond = max(0.0, current_units - entitlement)
            covered = current_units <= entitlement + 1e-9
            steps.append(
                f"Current units {current_units:g}: within entitlement {units_within:g}, "
                f"beyond entitlement {units_beyond:g}."
            )
            conditions.append(
                ConditionCheck(
                    code="CURRENT_WITHIN_ENTITLEMENT",
                    passed=covered,
                    detail=(
                        "Current consumption appears within computed free-unit entitlement."
                        if covered
                        else "Current consumption appears above computed free-unit entitlement."
                    ),
                )
            )
        else:
            missing.append("current_units")
            steps.append("Current month units not provided — entitlement computed only.")

        if subsidy_line_seen_on_bill:
            steps.append(
                "Bill extraction shows a subsidy/benefit line — possible existing enrollment signal."
            )
            warnings.append(
                "Subsidy line on bill is a signal only; it is not independent proof of ongoing eligibility."
            )
        if consumer_declares_enrolled:
            steps.append("Consumer declared they are enrolled (self-reported).")

        # Even with complete math, official enrollment/verification remains required.
        status = GruhaJyothiStatus.REQUIRES_OFFICIAL_VERIFICATION
        if entitlement <= 0:
            status = GruhaJyothiStatus.CONDITIONS_NOT_MET
            user_message = (
                "Computed entitlement is zero/non-positive under the configured rule. "
                "Verify baseline and official entitlement on BESCOM/Seva Sindhu."
            )
        else:
            user_message = (
                f"Based on provided inputs, computed Gruha Jyothi entitlement is "
                f"approximately {entitlement:g} units/month. "
                "This appears to meet documented domestic + baseline conditions for an estimate only. "
                + rule.user_messages.get("never_approval", "")
            )
            # Soft label: conditions appear met for estimation path
            if is_domestic and baseline_fy_2022_23_avg_units is not None:
                # Keep REQUIRES_OFFICIAL_VERIFICATION as primary status;
                # expose appearance via conditions + message.
                pass

        if rule.verification_status != "VERIFIED":
            warnings.append(
                f"Scheme rule verification_status={rule.verification_status}. "
                "Re-check latest official FAQ/order before relying on this estimate."
            )

        return GruhaJyothiAssessment(
            status=status,
            rule_version=rule.rule_version,
            verification_status=rule.verification_status,
            source=rule.source,
            as_of=as_of,
            category=category_u,
            baseline_fy_2022_23_avg_units=baseline_fy_2022_23_avg_units,
            computed_entitlement_units=entitlement,
            hard_cap_units=rule.entitlement.hard_cap_units,
            current_units=current_units,
            units_within_entitlement=units_within,
            units_beyond_entitlement=units_beyond,
            appears_fully_covered_this_month=covered,
            subsidy_line_seen_on_bill=subsidy_line_seen_on_bill,
            consumer_declares_enrolled=consumer_declares_enrolled,
            conditions=conditions,
            missing_inputs=missing,
            explanation_steps=steps,
            warnings=warnings,
            user_message=user_message.strip(),
        )

    def _compute_entitlement(self, baseline: float, steps: list[str]) -> float:
        rule = self._rule.entitlement
        uplift = rule.low_baseline_flat_uplift
        if (
            uplift.enabled
            and baseline < uplift.baseline_below_units
        ):
            raw = baseline + uplift.flat_extra_units
            steps.append(
                f"Low-baseline uplift enabled: {baseline:g} + {uplift.flat_extra_units:g} "
                f"= {raw:g} (then cap)."
            )
        else:
            raw = baseline * (1.0 + rule.percent_uplift / 100.0)
            steps.append(
                f"Entitlement before cap: {baseline:g} × "
                f"(1 + {rule.percent_uplift:g}/100) = {raw:g}"
            )

        capped = min(raw, rule.hard_cap_units)
        # FAQ wording often says "less than 200" / under 200 — keep hard cap inclusive
        # but document assumption.
        steps.append(
            f"Apply hard cap {rule.hard_cap_units:g} → entitlement {capped:g} units."
        )
        return round(capped, 4)
