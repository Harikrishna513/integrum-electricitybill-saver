"""
Apply user field corrections onto an extraction snapshot — Milestone 24.

Deterministic: no LLM. Patch ExtractedField values → re-validate downstream.
"""

from __future__ import annotations

from typing import Any

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.category import (
    CategoryClassificationResult,
    CategorySignal,
    ClassificationStatus,
    ConsumerCategory,
)
from app.domain.models.confirmation import CONFIRMABLE_FIELDS, BillConfirmationRequest
from app.domain.models.extracted_field import ExtractedField


class BillConfirmationError(ValueError):
    """Invalid confirmation payload."""


def apply_extraction_corrections(
    extraction: ElectricityBillExtraction,
    request: BillConfirmationRequest,
) -> tuple[ElectricityBillExtraction, list[str], list[str]]:
    """
    Returns (patched_extraction, fields_corrected, fields_accepted_as_printed).
    """
    data = extraction.model_dump(mode="python")
    corrected: list[str] = []
    accepted: list[str] = []

    unknown = [k for k in request.corrections if k not in CONFIRMABLE_FIELDS]
    if unknown:
        raise BillConfirmationError(
            f"Unknown or non-confirmable field(s): {', '.join(sorted(unknown))}"
        )

    for name, raw in request.corrections.items():
        data[name] = _user_field(raw)
        corrected.append(name)

    for name in request.accept_extracted_as_printed:
        if name not in CONFIRMABLE_FIELDS:
            raise BillConfirmationError(
                f"Unknown or non-confirmable field for accept_as_printed: {name}"
            )
        if name in corrected:
            continue
        current = ExtractedField.model_validate(data[name])
        if current.value is None or current.value == "":
            raise BillConfirmationError(
                f"Cannot accept empty field as printed: {name}. Provide a correction."
            )
        data[name] = _user_field(current.value)
        accepted.append(name)

    # If category enum confirmed, also stamp consumer_category text when missing/weak
    if request.confirm_category and request.confirm_category != ConsumerCategory.UNKNOWN:
        label = request.confirm_category.value.replace("_", " ").title()
        cat = ExtractedField.model_validate(data["consumer_category"])
        if "consumer_category" not in corrected and (
            cat.value is None or cat.level.value in {"LOW", "MISSING"}
        ):
            data["consumer_category"] = _user_field(label)
            if "consumer_category" not in accepted:
                accepted.append("consumer_category")

    patched = ElectricityBillExtraction.model_validate(data)
    return patched, corrected, accepted


def apply_user_category_confirmation(
    classification: CategoryClassificationResult,
    *,
    confirm_category: ConsumerCategory,
    rule_version: str,
    verification_status: str,
) -> CategoryClassificationResult:
    """
    Explicit consumer attestation of category.
    Does not invent money — only unlocks/locks the domestic pipeline gate.
    """
    if confirm_category == ConsumerCategory.UNKNOWN:
        raise BillConfirmationError("confirm_category cannot be UNKNOWN.")

    supported = confirm_category == ConsumerCategory.DOMESTIC
    signals = list(classification.signals) + [
        CategorySignal(
            source="user_confirmation",
            evidence=confirm_category.value,
            mapped_category=confirm_category,
            weight=1.0,
        )
    ]
    return CategoryClassificationResult(
        category=confirm_category,
        status=ClassificationStatus.CLASSIFIED,
        confidence=1.0,
        signals=signals,
        conflicting_categories=[],
        supported_by_app_v1=supported,
        requires_user_confirmation=False,
        rule_version=rule_version,
        verification_status=verification_status,
        user_message=(
            f"Category confirmed by user as {confirm_category.value}."
            if supported
            else (
                f"Category confirmed by user as {confirm_category.value}. "
                "This app version still only runs money engines for DOMESTIC."
            )
        ),
    )


def _user_field(raw: Any) -> dict[str, Any]:
    if isinstance(raw, bool):
        value: str | float | int | bool | None = raw
    elif isinstance(raw, (int, float)):
        value = raw
    elif raw is None:
        value = None
    else:
        text = str(raw).strip()
        value = text if text else None
        # Booleans from form strings
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            value = value.lower() == "true"
    return {
        "value": value,
        "confidence": 1.0,
        "source": "user",
    }
