
from __future__ import annotations

from app.domain.models.bill_field_requirements import (
    REQUIRED_CONFIRMATION_FIELDS,
    filter_confirmation_needs,
)
from app.domain.models.consistency import BillConsistencyResult
from app.domain.models.validated_bill import BillValidationResult


def compute_needs_confirmation(
    validation: BillValidationResult,
    consistency: BillConsistencyResult | None = None,
    *,
    attested: set[str] | None = None,
) -> list[str]:
    """
    Fields the user must still verify before Module 1 is complete.

    Only required fields block confirmation. Optional meter readings, RR number,
    consumer category (derived from tariff), and charge add-ons never block.
    """
    needs = list(validation.fields_needing_confirmation)

    if consistency is not None:
        for name in consistency.fields_needing_confirmation:
            if name in REQUIRED_CONFIRMATION_FIELDS and name not in needs:
                needs.append(name)

    return filter_confirmation_needs(needs, attested=attested)


def attested_fields_from_audit(audit: list | None) -> set[str]:
    """Field names the user corrected or accepted during bill confirmation."""
    if not isinstance(audit, list):
        return set()
    fields: set[str] = set()
    for entry in audit:
        if isinstance(entry, dict):
            name = entry.get("field")
            if name:
                fields.add(str(name))
    return fields


def attested_fields_from_stored_validation(validation_payload: dict | object) -> set[str]:
    if isinstance(validation_payload, dict):
        return attested_fields_from_audit(validation_payload.get("corrections_audit"))
    return set()
