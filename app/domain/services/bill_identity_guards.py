"""Guards so bill identity fields are not confused (Account ID ≠ Bill Number)."""

from __future__ import annotations

import re

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ExtractedField

# Labels that introduce a per-bill serial (changes monthly) — NOT the account ID.
_BILL_NO_LABEL = re.compile(
    r"(?:"
    r"ಬಿಲ್\s*ಸಂಖ್ಯೆ|"
    r"bill\s*(?:no\.?|number|#|num)|"
    r"invoice\s*(?:no\.?|number)"
    r")"
    r"\s*[:|]?\s*"
    r"(?P<num>[0-9]{6,20})",
    re.IGNORECASE,
)

# Table-row style: | ಬಿಲ್ ಸಂಖ್ಯೆ | 87451601 |
_BILL_NO_TABLE = re.compile(
    r"\|\s*(?:"
    r"ಬಿಲ್\s*ಸಂಖ್ಯೆ|"
    r"bill\s*(?:no\.?|number|#)"
    r")\s*\|\s*(?P<num>[0-9]{6,20})",
    re.IGNORECASE,
)


def find_printed_bill_numbers(ocr_text: str) -> set[str]:
    """Return bill-number values found next to bill-number labels in OCR text."""
    found: set[str] = set()
    for pattern in (_BILL_NO_LABEL, _BILL_NO_TABLE):
        for match in pattern.finditer(ocr_text or ""):
            found.add(match.group("num"))
    return found


def scrub_misplaced_identity_fields(
    extraction: ElectricityBillExtraction,
    *,
    ocr_text: str | None = None,
) -> ElectricityBillExtraction:
    """
    Clear account_id when it matches a printed Bill Number.

    Account ID / Consumer ID is stable across months.
    Bill Number (ಬಿಲ್ ಸಂಖ್ಯೆ) changes every month and must never fill account_id.
    """
    account = extraction.account_id
    if account.value is None or account.value == "":
        return extraction

    account_digits = re.sub(r"\D", "", str(account.value))
    if len(account_digits) < 4:
        return extraction

    bill_numbers = find_printed_bill_numbers(ocr_text or "")
    if not bill_numbers:
        return extraction

    # Exact match, or account_id is the full bill number with formatting stripped.
    if account_digits not in bill_numbers:
        return extraction

    note = (
        "Cleared account_id: value matched Bill Number (ಬಿಲ್ ಸಂಖ್ಯೆ / Bill No), "
        "which changes every month and is not the Account ID. "
        "Enter Account ID from the bill header if visible."
    )
    extraction.account_id = ExtractedField(value=None, confidence=0.0, source="unknown")
    if extraction.extraction_notes.value:
        extraction.extraction_notes.value = f"{extraction.extraction_notes.value} {note}"
    else:
        extraction.extraction_notes = ExtractedField(
            value=note, confidence=0.95, source="inferred"
        )
    return extraction
