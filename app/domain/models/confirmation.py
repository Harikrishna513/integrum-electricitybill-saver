from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field
from app.domain.models.category import ConsumerCategory

# Fields the confirm API may patch (subset of ElectricityBillExtraction).
CONFIRMABLE_FIELDS: frozenset[str] = frozenset(
    {
        "utility",
        "discom",
        "consumer_name",
        "account_id",
        "rr_number",
        "address",
        "consumer_category",
        "tariff_code",
        "billing_period",
        "bill_date",
        "due_date",
        "previous_meter_reading",
        "current_meter_reading",
        "units_consumed",
        "sanctioned_load",
        "energy_charge",
        "fixed_charge",
        "electricity_tax",
        "fppca",
        "other_charges",
        "subsidy",
        "arrears",
        "late_payment_charge",
        "total_amount",
        "document_language",
        "is_bescom_bill",
    }
)


class BillConfirmationRequest(BaseModel):
    """
    corrections: field_name → new raw value (string/number/bool).
    confirm_category: explicit category attestation (overrides classifier conflict).
    accept_extracted_as_printed: bump confidence on listed weak fields that already
      have values, without changing them (user says "as printed is correct").
    """

    corrections: dict[str, Any] = Field(default_factory=dict)
    confirm_category: ConsumerCategory | None = None
    accept_extracted_as_printed: list[str] = Field(default_factory=list)
    note: str | None = Field(
        default=None,
        description="Optional operator note stored on the analysis row.",
    )


class BillConfirmationApplied(BaseModel):
    analysis_id: str
    fields_corrected: list[str] = Field(default_factory=list)
    fields_accepted_as_printed: list[str] = Field(default_factory=list)
    category_confirmed: ConsumerCategory | None = None
    needs_confirmation: list[str] = Field(default_factory=list)
    message: str
