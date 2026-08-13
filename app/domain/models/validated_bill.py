"""
Canonical validated bill — Milestone 4.

CONCEPT
  Gemini returns messy values:
    units = "286"
    amount = "₹1,834.50"
    date = "12/07/2026"

  After Milestone 4 we have typed, normalized values PLUS the raw extraction
  and a list of validation issues.

WHY
  Downstream engines (tariff, savings) must receive floats/dates, not "₹1,834.50".
  Normalization is deterministic Python — not another LLM call.

SPRING ANALOGY
  Like mapping an OCR DTO → domain Bill entity with Bean Validation results.

NOT IN THIS MILESTONE
  - Consumer category classification (Milestone 5)
  - Meter reading arithmetic mismatch (Milestone 6)
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.domain.models.extracted_field import ConfidenceLevel


class ValidationSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationIssue(BaseModel):
    code: str
    message: str
    field: str | None = None
    severity: ValidationSeverity = ValidationSeverity.WARNING


class ParseStatus(str, Enum):
    OK = "ok"
    MISSING = "missing"
    PARSE_FAILED = "parse_failed"
    OUT_OF_RANGE = "out_of_range"


class ValidatedString(BaseModel):
    value: str | None = None
    raw: str | float | int | None = None
    confidence: float = 0.0
    level: ConfidenceLevel = ConfidenceLevel.MISSING
    source: Literal["bill", "inferred", "unknown", "user"] = "unknown"
    parse_status: ParseStatus = ParseStatus.MISSING
    coerced: bool = False


class ValidatedNumber(BaseModel):
    value: float | None = None
    raw: str | float | int | None = None
    confidence: float = 0.0
    level: ConfidenceLevel = ConfidenceLevel.MISSING
    source: Literal["bill", "inferred", "unknown", "user"] = "unknown"
    parse_status: ParseStatus = ParseStatus.MISSING
    coerced: bool = False


class ValidatedDate(BaseModel):
    """value is a real date when parsing succeeded; raw_text keeps printed form."""

    value: date | None = None
    raw_text: str | None = None
    raw: str | float | int | None = None
    confidence: float = 0.0
    level: ConfidenceLevel = ConfidenceLevel.MISSING
    source: Literal["bill", "inferred", "unknown", "user"] = "unknown"
    parse_status: ParseStatus = ParseStatus.MISSING
    coerced: bool = False


class ValidatedBool(BaseModel):
    value: bool | None = None
    raw: str | float | int | None = None
    confidence: float = 0.0
    level: ConfidenceLevel = ConfidenceLevel.MISSING
    source: Literal["bill", "inferred", "unknown", "user"] = "unknown"
    parse_status: ParseStatus = ParseStatus.MISSING
    coerced: bool = False


class CanonicalElectricityBill(BaseModel):
    """
    Typed bill ready for later engines.

    Every field keeps confidence from extraction so uncertainty stays visible.
    """

    utility: ValidatedString = Field(default_factory=ValidatedString)
    discom: ValidatedString = Field(default_factory=ValidatedString)
    consumer_name: ValidatedString = Field(default_factory=ValidatedString)
    account_id: ValidatedString = Field(default_factory=ValidatedString)
    rr_number: ValidatedString = Field(default_factory=ValidatedString)
    address: ValidatedString = Field(default_factory=ValidatedString)

    consumer_category: ValidatedString = Field(default_factory=ValidatedString)
    tariff_code: ValidatedString = Field(default_factory=ValidatedString)

    billing_period: ValidatedString = Field(default_factory=ValidatedString)
    bill_date: ValidatedDate = Field(default_factory=ValidatedDate)
    due_date: ValidatedDate = Field(default_factory=ValidatedDate)

    previous_meter_reading: ValidatedNumber = Field(default_factory=ValidatedNumber)
    current_meter_reading: ValidatedNumber = Field(default_factory=ValidatedNumber)
    units_consumed: ValidatedNumber = Field(default_factory=ValidatedNumber)
    sanctioned_load: ValidatedNumber = Field(default_factory=ValidatedNumber)

    energy_charge: ValidatedNumber = Field(default_factory=ValidatedNumber)
    fixed_charge: ValidatedNumber = Field(default_factory=ValidatedNumber)
    electricity_tax: ValidatedNumber = Field(default_factory=ValidatedNumber)
    fppca: ValidatedNumber = Field(default_factory=ValidatedNumber)
    other_charges: ValidatedNumber = Field(default_factory=ValidatedNumber)
    subsidy: ValidatedNumber = Field(default_factory=ValidatedNumber)
    arrears: ValidatedNumber = Field(default_factory=ValidatedNumber)
    late_payment_charge: ValidatedNumber = Field(default_factory=ValidatedNumber)
    total_amount: ValidatedNumber = Field(default_factory=ValidatedNumber)

    document_language: ValidatedString = Field(default_factory=ValidatedString)
    is_bescom_bill: ValidatedBool = Field(default_factory=ValidatedBool)
    extraction_notes: ValidatedString = Field(default_factory=ValidatedString)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_usable_units(self) -> bool:
        return (
            self.units_consumed.parse_status == ParseStatus.OK
            and self.units_consumed.value is not None
            and self.units_consumed.level
            in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_usable_total(self) -> bool:
        return (
            self.total_amount.parse_status == ParseStatus.OK
            and self.total_amount.value is not None
            and self.total_amount.level
            in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM)
        )


class BillValidationResult(BaseModel):
    bill: CanonicalElectricityBill
    issues: list[ValidationIssue] = Field(default_factory=list)
    fields_needing_confirmation: list[str] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.ERROR)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == ValidationSeverity.WARNING)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_usable_for_analysis(self) -> bool:
        """
        Enough typed data to continue the pipeline later.
        Category/meter mismatch still come in later milestones.
        """
        if self.error_count > 0:
            return False
        return self.bill.has_usable_units or self.bill.has_usable_total
