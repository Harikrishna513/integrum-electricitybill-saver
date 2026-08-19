from __future__ import annotations

from typing import Any

# User must verify these before continuing to bill summary / calculations.
REQUIRED_CONFIRMATION_FIELDS: frozenset[str] = frozenset(
    {
        "consumer_name",
        "account_id",
        "address",
        "utility",
        "discom",
        "tariff_code",
        "sanctioned_load",
        "billing_period",
        "bill_date",
        "units_consumed",
        "energy_charge",
        "fixed_charge",
        "total_amount",
        "document_language",
        "is_bescom_bill",
    }
)

# Shown in review when extracted; never required for confirmation.
OPTIONAL_REVIEW_FIELDS: frozenset[str] = frozenset(
    {
        "rr_number",
        "consumer_category",
        "due_date",
        "previous_meter_reading",
        "current_meter_reading",
        "electricity_tax",
        "fppca",
        "other_charges",
        "arrears",
        "late_payment_charge",
    }
)

# Never shown in the review UI.
HIDDEN_REVIEW_FIELDS: frozenset[str] = frozenset({"extraction_notes"})

# Shown only when the extractor found a non-zero value on the bill.
CONDITIONAL_REVIEW_FIELDS: frozenset[str] = frozenset({"subsidy"})


def is_required_for_confirmation(field_name: str) -> bool:
    return field_name in REQUIRED_CONFIRMATION_FIELDS


def _field_value(data: dict[str, Any], name: str) -> Any:
    field = data.get(name)
    if isinstance(field, dict):
        return field.get("value")
    return None


def should_show_review_field(
    field_name: str,
    *,
    extraction_data: dict[str, Any],
    validated_data: dict[str, Any] | None = None,
) -> bool:
    if field_name in HIDDEN_REVIEW_FIELDS:
        return False
    if field_name in CONDITIONAL_REVIEW_FIELDS:
        return _subsidy_detected(extraction_data, validated_data or {})
    return True


def _subsidy_detected(
    extraction_data: dict[str, Any],
    validated_data: dict[str, Any],
) -> bool:
    for data in (validated_data, extraction_data):
        value = _field_value(data, "subsidy")
        if value is None or value == "":
            continue
        try:
            if float(value) != 0:
                return True
        except (TypeError, ValueError):
            return True
    return False


def filter_confirmation_needs(
    fields: list[str],
    *,
    attested: set[str] | None = None,
) -> list[str]:
    """Keep only required fields that still need user attention."""
    needed = [name for name in fields if name in REQUIRED_CONFIRMATION_FIELDS]
    if attested:
        needed = [name for name in needed if name not in attested]
    return needed
