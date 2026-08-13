"""
Metering arrangement models — Milestone 15.

Net / Gross settlement estimates for individual rooftop.
VNM / GNM are conceptual placeholders until Milestones 16 / 17.
"""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class MeteringArrangement(str, Enum):
    NET_METERING = "NET_METERING"
    GROSS_METERING = "GROSS_METERING"
    VIRTUAL_NET_METERING = "VIRTUAL_NET_METERING"
    GROUP_NET_METERING = "GROUP_NET_METERING"


class MeteringSettlementStatus(str, Enum):
    ESTIMATED = "ESTIMATED"
    CONCEPT_ONLY = "CONCEPT_ONLY"
    INVALID_INPUT = "INVALID_INPUT"
    TARIFF_UNAVAILABLE = "TARIFF_UNAVAILABLE"
    UNSUPPORTED_CATEGORY = "UNSUPPORTED_CATEGORY"


class MeterRegisters(BaseModel):
    """Estimated bi-directional meter register totals for a period."""

    consumption_kwh: float
    generation_kwh: float
    coincidence_fraction: float
    self_consumed_kwh: float
    import_kwh: float
    export_kwh: float
    net_import_kwh: float  # import - export (= C - G); negative ⇒ net export
    note: str = (
        "Estimated registers from monthly consumption/generation assumptions — "
        "not MRI downloads from a bi-directional meter."
    )


class MeteringSettlementResult(BaseModel):
    status: MeteringSettlementStatus
    arrangement: MeteringArrangement
    as_of: date
    rule_version: str | None = None
    verification_status: str | None = None
    source: str | None = None

    registers: MeterRegisters | None = None
    export_tariff_inr_per_kwh: float | None = None
    availed_cfa_for_export_tariff: bool | None = None

    baseline_retail_bill_inr: float | None = None
    retail_bill_after_arrangement_inr: float | None = None
    export_credit_or_sale_inr: float | None = None
    estimated_net_cost_inr: float | None = None
    estimated_monthly_saving_inr: float | None = None

    tariff_rule_version: str | None = None
    tariff_verification_status: str | None = None

    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: dict[str, Any] = Field(default_factory=dict)
    message: str
    disclaimer: str = (
        "Estimated metering settlement only. Not an official BESCOM bill or PPA "
        "credit. Confirm export tariff against your signed PPA / latest KERC order."
    )


class MeteringConcept(BaseModel):
    arrangement: MeteringArrangement
    label: str
    summary: str
    scope: str
    implementation_status: str
    diagram: str = ""


class MeteringCompareResult(BaseModel):
    status: Literal["ESTIMATED", "INVALID_INPUT", "TARIFF_UNAVAILABLE"] = "ESTIMATED"
    as_of: date
    net: MeteringSettlementResult
    gross: MeteringSettlementResult
    preferred_hint: str
    message: str
