"""Tests: Account ID must not be filled from Bill Number."""

from __future__ import annotations

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ExtractedField
from app.domain.services.bill_identity_guards import (
    find_printed_bill_numbers,
    scrub_misplaced_identity_fields,
)


def test_finds_kannada_bill_number_in_table():
    ocr = "|  ಬಿಲ್ ಸಂಖ್ಯೆ | 87451601  |\n|  ಬಳಕೆ | 248  |"
    assert find_printed_bill_numbers(ocr) == {"87451601"}


def test_scrub_clears_account_id_when_it_is_bill_number():
    extraction = ElectricityBillExtraction(
        account_id=ExtractedField(value="87451601", confidence=0.9, source="bill"),
        units_consumed=ExtractedField(value=248, confidence=0.9, source="bill"),
    )
    ocr = "| ಬಿಲ್ ಸಂಖ್ಯೆ | 87451601 |\n| ಬಳಕೆ | 248 |"
    result = scrub_misplaced_identity_fields(extraction, ocr_text=ocr)
    assert result.account_id.value is None
    assert result.account_id.confidence == 0.0
    assert "Bill Number" in (result.extraction_notes.value or "")


def test_scrub_keeps_real_account_id():
    extraction = ElectricityBillExtraction(
        account_id=ExtractedField(value="9981234567", confidence=0.95, source="bill"),
    )
    ocr = "Account Id: 9981234567\nBill No: 87451601"
    result = scrub_misplaced_identity_fields(extraction, ocr_text=ocr)
    assert result.account_id.value == "9981234567"
