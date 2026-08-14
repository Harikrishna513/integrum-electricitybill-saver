"""
Canonical electricity bill extraction schema (Milestone 3).

CONCEPT
  Stable internal schema for BESCOM bill fields — independent of bill layout.

WHY
  BESCOM layouts change. We must NOT parse "line 17 = units".
  Gemini reads semantically → fills this schema.

IMPORTANT
  This is EXTRACTION only (what the document appears to say).
  It is NOT tariff calculation. Do not ask Gemini to recompute charges.

SPRING ANALOGY
  Like a BillExtractionDto returned from an OCR adapter before domain validation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field

from app.domain.models.bill_field_requirements import REQUIRED_CONFIRMATION_FIELDS
from app.domain.models.extracted_field import ConfidenceLevel, ExtractedField


class ElectricityBillExtraction(BaseModel):
    """
    Structured fields extracted from a Karnataka / BESCOM electricity bill image or PDF.

    All monetary/quantity fields use ExtractedField so confidence is visible.
    Fields are optional at the value level because bills omit some lines.
    """

    # Identity / location
    utility: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Utility / board name if visible, e.g. BESCOM.",
    )
    discom: ExtractedField = Field(
        default_factory=ExtractedField,
        description="DISCOM name if visible (often BESCOM for Bengaluru area).",
    )
    consumer_name: ExtractedField = Field(default_factory=ExtractedField)
    account_id: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Account / Consumer ID / Account No if present.",
    )
    rr_number: ExtractedField = Field(
        default_factory=ExtractedField,
        description="RR Number / Revenue Register number if present.",
    )
    address: ExtractedField = Field(default_factory=ExtractedField)

    # Category signals (classification engine comes in Milestone 5)
    consumer_category: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Category text if present, e.g. Domestic / LT-1 / Residential.",
    )
    tariff_code: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Tariff code if present, e.g. LT-1, LT1.",
    )

    # Dates / period
    billing_period: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Billing period text as printed, e.g. Jul-2026 or 01/07/2026-31/07/2026.",
    )
    bill_date: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Bill date as printed on the bill.",
    )
    due_date: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Payment due date as printed.",
    )

    # Meter / consumption
    previous_meter_reading: ExtractedField = Field(default_factory=ExtractedField)
    current_meter_reading: ExtractedField = Field(default_factory=ExtractedField)
    units_consumed: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Consumed units / kWh for the period.",
    )
    sanctioned_load: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Sanctioned / contracted load, often in kW.",
    )

    # Charges as printed on the bill (do NOT recalculate)
    energy_charge: ExtractedField = Field(default_factory=ExtractedField)
    fixed_charge: ExtractedField = Field(default_factory=ExtractedField)
    electricity_tax: ExtractedField = Field(default_factory=ExtractedField)
    fppca: ExtractedField = Field(
        default_factory=ExtractedField,
        description="FPPCA / fuel or power purchase adjustment if present.",
    )
    other_charges: ExtractedField = Field(default_factory=ExtractedField)
    subsidy: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Subsidy / Gruha Jyothi benefit amount if shown as a line item.",
    )
    arrears: ExtractedField = Field(default_factory=ExtractedField)
    late_payment_charge: ExtractedField = Field(default_factory=ExtractedField)
    total_amount: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Total amount payable as printed.",
    )

    # Document quality signals
    document_language: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Primary language visible, e.g. English / Kannada / mixed.",
    )
    is_bescom_bill: ExtractedField = Field(
        default_factory=ExtractedField,
        description="true/false whether this appears to be a BESCOM electricity bill.",
    )
    extraction_notes: ExtractedField = Field(
        default_factory=ExtractedField,
        description="Short notes about unclear areas, blur, missing sections — not calculations.",
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def confidence_summary(self) -> dict[str, list[str]]:
        """Group field names by confidence level for UI / learning logs."""
        summary: dict[str, list[str]] = {
            ConfidenceLevel.HIGH.value: [],
            ConfidenceLevel.MEDIUM.value: [],
            ConfidenceLevel.LOW.value: [],
            ConfidenceLevel.MISSING.value: [],
        }
        for name, field in self.iter_extracted_fields():
            summary[field.level.value].append(name)
        return summary

    def iter_extracted_fields(self) -> list[tuple[str, ExtractedField]]:
        pairs: list[tuple[str, ExtractedField]] = []
        for name, value in self:
            if isinstance(value, ExtractedField):
                pairs.append((name, value))
        return pairs

    def low_or_missing_critical_fields(self) -> list[str]:
        """
        Fields that usually matter for later analysis and are weak/missing.
        Used to prompt the user to confirm (Milestone 4+ will harden this).
        """
        critical = REQUIRED_CONFIRMATION_FIELDS
        weak: list[str] = []
        data = self.model_dump()
        for name in critical:
            field = ExtractedField.model_validate(data[name])
            if field.level in (ConfidenceLevel.LOW, ConfidenceLevel.MISSING):
                weak.append(name)
        return weak
