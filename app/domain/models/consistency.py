"""
Bill consistency models — Milestone 6.

CONCEPT
  Cross-field arithmetic checks on the validated bill.
  Example: current_reading - previous_reading vs units_consumed.

CRITICAL PRODUCT RULE
  A mismatch is a DETECTED DISCREPANCY to verify.
  It is NOT proof that BESCOM overcharged the customer.
  OCR/extraction errors are a common cause.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, computed_field


class ConsistencyStatus(str, Enum):
    CONSISTENT = "CONSISTENT"
    DISCREPANCY_DETECTED = "DISCREPANCY_DETECTED"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class ConsistencySeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"  # strong inconsistency in extracted numbers — still not "proven fraud"


class ConsistencyIssue(BaseModel):
    code: str
    message: str
    severity: ConsistencySeverity = ConsistencySeverity.WARNING
    fields: list[str] = Field(default_factory=list)
    expected_value: float | None = None
    observed_value: float | None = None
    difference: float | None = None

    # Explicit legal/product wording helper for UI
    interpretation: str = (
        "Detected discrepancy in extracted values — please verify on the original bill. "
        "This is not proof of a billing error by the utility."
    )


class BillConsistencyResult(BaseModel):
    status: ConsistencyStatus
    issues: list[ConsistencyIssue] = Field(default_factory=list)
    checks_performed: list[str] = Field(default_factory=list)
    checks_skipped: list[str] = Field(default_factory=list)
    reading_delta: float | None = None
    units_consumed: float | None = None
    summary_message: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_discrepancy(self) -> bool:
        return self.status == ConsistencyStatus.DISCREPANCY_DETECTED

    @computed_field  # type: ignore[prop-decorator]
    @property
    def fields_needing_confirmation(self) -> list[str]:
        fields: list[str] = []
        for issue in self.issues:
            for name in issue.fields:
                if name not in fields:
                    fields.append(name)
        return fields
