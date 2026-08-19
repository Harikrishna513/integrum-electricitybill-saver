from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SavingsStatus(str, Enum):
    ESTIMATED = "ESTIMATED"
    INVALID_INPUT = "INVALID_INPUT"
    TARIFF_UNAVAILABLE = "TARIFF_UNAVAILABLE"


class SavingsConfidence(str, Enum):
    HIGH = "HIGH"  # user-provided precise assumptions
    MEDIUM = "MEDIUM"  # catalog defaults
    LOW = "LOW"  # rough defaults / incomplete tariff verification


class AssumptionSet(BaseModel):
    """Explicit assumptions used in the estimate (auditable)."""

    description: str
    values: dict[str, Any] = Field(default_factory=dict)


class SavingsEstimate(BaseModel):
    status: SavingsStatus
    recommendation_id: str | None = None
    title: str
    assumptions: AssumptionSet

    current_units: float
    estimated_new_units: float
    units_saved: float

    current_bill_estimate: float | None = None
    new_bill_estimate: float | None = None
    estimated_monthly_saving: float | None = None
    estimated_annual_saving: float | None = None

    tariff_rule_version: str | None = None
    tariff_verification_status: str | None = None
    as_of: date | None = None

    confidence: SavingsConfidence = SavingsConfidence.MEDIUM
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str


class RecommendationTemplate(BaseModel):
    id: str
    title: str
    category: str  # behavior | appliance_swap | other
    impact: str  # high | medium | low
    default_assumptions: dict[str, Any] = Field(default_factory=dict)
    formula: str
    tips: list[str] = Field(default_factory=list)
    notes: str = ""
