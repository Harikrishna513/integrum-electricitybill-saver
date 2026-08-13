"""
BillConsistencyValidator — Milestone 6.

CONCEPT
  After per-field validation (M4) and category classification (M5),
  check whether related numbers agree with each other.

CHECKS
  1. current_meter_reading >= previous_meter_reading (when both present)
  2. (current - previous) ~= units_consumed (tolerance)
  3. Optional soft check: sum of printed charge lines ~= total_amount

LANGUAGE RULE
  Never say: "BESCOM overcharged you."
  Say: "The bill contains a value mismatch that should be verified."

SPRING ANALOGY
  Like a domain invariant checker / business rule validator on an aggregate.
"""

from __future__ import annotations

from app.domain.models.consistency import (
    BillConsistencyResult,
    ConsistencyIssue,
    ConsistencySeverity,
    ConsistencyStatus,
)
from app.domain.models.validated_bill import CanonicalElectricityBill, ParseStatus

# Allow tiny float/OCR rounding differences (units are often whole numbers)
DEFAULT_UNITS_TOLERANCE = 1.0
DEFAULT_AMOUNT_TOLERANCE = 2.0  # rupees


class BillConsistencyValidator:
    def __init__(
        self,
        *,
        units_tolerance: float = DEFAULT_UNITS_TOLERANCE,
        amount_tolerance: float = DEFAULT_AMOUNT_TOLERANCE,
    ) -> None:
        self._units_tolerance = units_tolerance
        self._amount_tolerance = amount_tolerance

    def validate(self, bill: CanonicalElectricityBill) -> BillConsistencyResult:
        issues: list[ConsistencyIssue] = []
        checks_performed: list[str] = []
        checks_skipped: list[str] = []

        prev = self._ok_number(bill.previous_meter_reading.value, bill.previous_meter_reading.parse_status)
        curr = self._ok_number(bill.current_meter_reading.value, bill.current_meter_reading.parse_status)
        units = self._ok_number(bill.units_consumed.value, bill.units_consumed.parse_status)

        reading_delta: float | None = None

        # --- Check 1: reading order ---
        if prev is not None and curr is not None:
            checks_performed.append("meter_reading_order")
            if curr < prev:
                issues.append(
                    ConsistencyIssue(
                        code="CURRENT_READING_BEFORE_PREVIOUS",
                        severity=ConsistencySeverity.WARNING,
                        fields=["previous_meter_reading", "current_meter_reading"],
                        expected_value=None,
                        observed_value=curr,
                        difference=curr - prev,
                        message=(
                            f"Current meter reading ({curr}) is less than previous "
                            f"reading ({prev}). This may be a meter rollover, a special "
                            "billing case, or an extraction mistake — please verify "
                            "on the original bill."
                        ),
                    )
                )
            else:
                reading_delta = curr - prev
        else:
            checks_skipped.append("meter_reading_order")

        # --- Check 2: reading delta vs units ---
        if prev is not None and curr is not None and units is not None:
            checks_performed.append("meter_reading_vs_units")
            if curr >= prev:
                expected = curr - prev
                reading_delta = expected
                diff = abs(expected - units)
                if diff > self._units_tolerance:
                    issues.append(
                        ConsistencyIssue(
                            code="POTENTIAL_METER_READING_MISMATCH",
                            severity=ConsistencySeverity.WARNING,
                            fields=[
                                "previous_meter_reading",
                                "current_meter_reading",
                                "units_consumed",
                            ],
                            expected_value=expected,
                            observed_value=units,
                            difference=round(units - expected, 4),
                            message=(
                                f"Meter readings imply {expected:g} units "
                                f"(current {curr:g} − previous {prev:g}), "
                                f"but units_consumed is {units:g} "
                                f"(difference {units - expected:+g}). "
                                "The bill contains a value mismatch that should be verified "
                                "on the original document. "
                                "This is a detected discrepancy, not proof of a utility billing error."
                            ),
                        )
                    )
        else:
            checks_skipped.append("meter_reading_vs_units")

        # --- Check 3: soft charge sum vs total (optional) ---
        charge_sum, present_fields = self._sum_charge_lines(bill)
        total = self._ok_number(bill.total_amount.value, bill.total_amount.parse_status)
        if charge_sum is not None and total is not None and len(present_fields) >= 2:
            checks_performed.append("charge_lines_vs_total")
            diff = abs(charge_sum - total)
            if diff > self._amount_tolerance:
                issues.append(
                    ConsistencyIssue(
                        code="POTENTIAL_CHARGE_TOTAL_MISMATCH",
                        severity=ConsistencySeverity.INFO,
                        fields=[*present_fields, "total_amount"],
                        expected_value=round(charge_sum, 2),
                        observed_value=total,
                        difference=round(total - charge_sum, 2),
                        message=(
                            f"Sum of extracted charge lines is approximately ₹{charge_sum:.2f}, "
                            f"but total_amount is ₹{total:.2f}. "
                            "Missing line items or extraction gaps are common — "
                            "please verify on the original bill. "
                            "This is not proof of a utility billing error."
                        ),
                    )
                )
        else:
            checks_skipped.append("charge_lines_vs_total")

        if not checks_performed:
            status = ConsistencyStatus.INSUFFICIENT_DATA
            summary = (
                "Not enough typed meter/amount fields to run consistency checks. "
                "Confirm readings and units if available on the bill."
            )
        elif issues:
            status = ConsistencyStatus.DISCREPANCY_DETECTED
            summary = (
                "One or more discrepancies were detected in the extracted values. "
                "Please verify them on the original bill. "
                "A discrepancy is not the same as a proven billing error."
            )
        else:
            status = ConsistencyStatus.CONSISTENT
            summary = "Checked fields are consistent within configured tolerances."

        return BillConsistencyResult(
            status=status,
            issues=issues,
            checks_performed=checks_performed,
            checks_skipped=checks_skipped,
            reading_delta=reading_delta,
            units_consumed=units,
            summary_message=summary,
        )

    def _ok_number(self, value: float | None, status: ParseStatus) -> float | None:
        if status != ParseStatus.OK or value is None:
            return None
        return float(value)

    def _sum_charge_lines(
        self,
        bill: CanonicalElectricityBill,
    ) -> tuple[float | None, list[str]]:
        """
        Sum available printed charge components.
        Subsidy is subtracted when present (as a benefit line).
        """
        components: list[tuple[str, float | None, ParseStatus, float]] = [
            ("energy_charge", bill.energy_charge.value, bill.energy_charge.parse_status, 1.0),
            ("fixed_charge", bill.fixed_charge.value, bill.fixed_charge.parse_status, 1.0),
            ("electricity_tax", bill.electricity_tax.value, bill.electricity_tax.parse_status, 1.0),
            ("fppca", bill.fppca.value, bill.fppca.parse_status, 1.0),
            ("other_charges", bill.other_charges.value, bill.other_charges.parse_status, 1.0),
            ("arrears", bill.arrears.value, bill.arrears.parse_status, 1.0),
            (
                "late_payment_charge",
                bill.late_payment_charge.value,
                bill.late_payment_charge.parse_status,
                1.0,
            ),
            # subsidy reduces payable amount; value may already be negative from extraction
            ("subsidy", bill.subsidy.value, bill.subsidy.parse_status, 1.0),
        ]

        total = 0.0
        present: list[str] = []
        for name, value, status, _sign in components:
            number = self._ok_number(value, status)
            if number is None:
                continue
            present.append(name)
            if name == "subsidy":
                # If subsidy was extracted as positive benefit amount, subtract it.
                total += -abs(number) if number > 0 else number
            else:
                total += number

        if len(present) < 2:
            return None, present
        return total, present
