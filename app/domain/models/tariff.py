from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class TariffCalculationStatus(str, Enum):
    CALCULATED = "CALCULATED"
    RULE_NOT_FOUND = "RULE_NOT_FOUND"
    UNSUPPORTED_CATEGORY = "UNSUPPORTED_CATEGORY"
    INVALID_INPUT = "INVALID_INPUT"
    REQUIRES_VERIFICATION = "REQUIRES_VERIFICATION"


class TariffSlab(BaseModel):
    up_to: float | None = None  # null = open-ended
    rate_per_kwh: float


class EnergyRule(BaseModel):
    model: str  # telescopic_slabs | flat
    unit: str = "kWh"
    rate_per_kwh: float | None = None
    slabs: list[TariffSlab] = Field(default_factory=list)


class FixedChargeRule(BaseModel):
    model: str  # per_kw_month | flat
    rate_per_kw: float | None = None
    flat_amount: float | None = None
    minimum_kw: float = 1.0


class TaxRule(BaseModel):
    model: str  # percent_of_energy_plus_fixed | percent_of_energy | none
    percent: float = 0.0


class SurchargeRule(BaseModel):
    code: str
    description: str = ""
    model: str  # per_kwh | flat
    rate_per_kwh: float | None = None
    flat_amount: float | None = None


class TariffRule(BaseModel):
    rule_version: str
    state: str
    discom: str
    category: str
    tariff_codes: list[str] = Field(default_factory=list)
    effective_from: date
    effective_to: date | None = None
    verification_status: str
    source: str
    notes: str = ""
    energy: EnergyRule
    fixed_charge: FixedChargeRule
    electricity_tax: TaxRule
    surcharges: list[SurchargeRule] = Field(default_factory=list)

    def applies_on(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of > self.effective_to:
            return False
        return True


class ChargeLine(BaseModel):
    code: str
    description: str
    amount: float
    detail: str | None = None


class TariffCalculationResult(BaseModel):
    status: TariffCalculationStatus
    discom: str
    category: str
    as_of: date
    units: float | None = None
    sanctioned_load_kw: float | None = None

    rule_version: str | None = None
    verification_status: str | None = None
    source: str | None = None

    energy_charge: float | None = None
    fixed_charge: float | None = None
    electricity_tax: float | None = None
    surcharge_total: float | None = None
    estimated_total: float | None = None

    lines: list[ChargeLine] = Field(default_factory=list)
    explanation_steps: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    message: str
