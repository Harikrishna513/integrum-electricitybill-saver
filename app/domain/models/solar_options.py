from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.domain.models.gnm import GNMInstallationInput, GNMPlantInput
from app.domain.models.solar_intelligence_report import SolarIntelligenceReport
from app.domain.models.vnm_comparison import VNMComparisonView
from app.domain.models.vnm import VNMParticipantInput, VNMPlantInput


class SolarOptionsPlantInput(BaseModel):
    proposed_kwp: float | None = Field(
        default=None,
        ge=0,
        description="Plant size in kWp. If omitted, derived from bill consumption.",
    )
    roof_area_m2: float | None = Field(
        default=None,
        ge=0,
        description="Usable roof area for individual rooftop sizing.",
    )
    same_discom_area: bool = True
    same_consumer_name: bool = True
    estimated_monthly_generation_kwh: float | None = Field(default=None, ge=0)


class VNMParticipantOverride(BaseModel):
    connection_id: str
    category: str = "DOMESTIC"
    monthly_units: float | None = Field(default=None, ge=0)
    sanctioned_load_kw: float | None = Field(default=None, ge=0)
    procurement_share_percent: float | None = Field(default=None, ge=0, le=100)


class GNMInstallationOverride(BaseModel):
    connection_id: str
    category: str = "DOMESTIC"
    monthly_units: float | None = Field(default=None, ge=0)
    sanctioned_load_kw: float | None = Field(default=None, ge=0)
    priority: int | None = Field(default=None, ge=1)
    is_host: bool = False


class CompareSolarOptionsRequest(BaseModel):
    plant: SolarOptionsPlantInput = Field(default_factory=SolarOptionsPlantInput)
    vnm_participants: list[VNMParticipantOverride] = Field(default_factory=list)
    gnm_installations: list[GNMInstallationOverride] = Field(default_factory=list)
    include_individual_solar: bool = False
    include_vnm: bool = True
    include_gnm: bool = False
    expected_vnm_solar_credit_kwh: float | None = Field(
        default=None,
        ge=0,
        description=(
            "Expected VNM solar credit for the billing period (kWh), from the "
            "VNM provider/society — not derived from consumption or sanctioned load."
        ),
    )


class BillSolarPrefill(BaseModel):
    analysis_id: str
    connection_id: str
    consumer_name: str | None = None
    address: str | None = None
    # Raw kWh on the bill for the full billing period (may span >1 month).
    period_units_kwh: float
    # Average kWh/month when period spans multiple months; else same as period_units.
    monthly_units: float
    sanctioned_load_kw: float
    current_monthly_bill_inr: float | None = None
    tariff_code: str
    discom: str
    category: str
    as_of: date
    suggested_plant_kwp: float | None = None
    bill_date: str | None = None
    billing_period: str | None = None
    billing_period_days: int | None = None
    billing_period_months: float = 1.0
    is_multi_month_period: bool = False
    period_consumption_note: str | None = None


class SolarOptionCard(BaseModel):
    option: Literal["individual_solar", "vnm", "gnm"]
    title: str
    status: str
    monthly_saving_inr: float | None = None
    plant_kwp: float | None = None
    message: str
    official_next_step: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    result: dict[str, Any] = Field(default_factory=dict)
    intelligence_report: SolarIntelligenceReport | None = None


class SolarOptionsComparisonView(BaseModel):
    analysis_id: str
    prefill: BillSolarPrefill
    options: list[SolarOptionCard] = Field(default_factory=list)
    best_option: Literal["individual_solar", "vnm", "gnm"] | None = None
    vnm_comparison: VNMComparisonView | None = None
    disclaimer: str
    message: str


def build_assumed_vnm_participants(
    prefill: BillSolarPrefill,
    *,
    typical_flats: int = 20,
) -> list[VNMParticipantInput]:
    """Society model — user does not enter neighbour details."""
    flats = max(2, typical_flats)
    user_share = round(100.0 / flats, 4)
    other_share = round(100.0 - user_share, 4)
    participants = [
        VNMParticipantInput(
            connection_id=prefill.connection_id,
            category=prefill.category,
            sanctioned_load_kw=prefill.sanctioned_load_kw,
            monthly_units=prefill.monthly_units,
            procurement_share_percent=user_share,
        ),
        VNMParticipantInput(
            connection_id="Other flats (assumed)",
            category=prefill.category,
            sanctioned_load_kw=prefill.sanctioned_load_kw,
            monthly_units=prefill.monthly_units * (flats - 1),
            procurement_share_percent=other_share,
        ),
    ]
    return participants


def build_vnm_participants(
    prefill: BillSolarPrefill,
    extras: list[VNMParticipantOverride],
) -> list[VNMParticipantInput]:
    participants: list[VNMParticipantInput] = []
    bill_share = 100.0
    if extras:
        extra_shares = sum(p.procurement_share_percent or 0 for p in extras)
        bill_share = max(0.0, 100.0 - extra_shares)

    participants.append(
        VNMParticipantInput(
            connection_id=prefill.connection_id,
            category=prefill.category,
            sanctioned_load_kw=prefill.sanctioned_load_kw,
            monthly_units=prefill.monthly_units,
            procurement_share_percent=bill_share,
        )
    )
    for extra in extras:
        participants.append(
            VNMParticipantInput(
                connection_id=extra.connection_id,
                category=extra.category,
                sanctioned_load_kw=extra.sanctioned_load_kw or prefill.sanctioned_load_kw,
                monthly_units=extra.monthly_units or prefill.monthly_units,
                procurement_share_percent=extra.procurement_share_percent or 0.0,
            )
        )
    return participants


def build_gnm_installations(
    prefill: BillSolarPrefill,
    extras: list[GNMInstallationOverride],
) -> list[GNMInstallationInput]:
    installations: list[GNMInstallationInput] = []
    has_host = any(e.is_host for e in extras)
    installations.append(
        GNMInstallationInput(
            connection_id=prefill.connection_id,
            category=prefill.category,
            sanctioned_load_kw=prefill.sanctioned_load_kw,
            monthly_units=prefill.monthly_units,
            priority=1,
            is_host=not has_host,
        )
    )
    for i, extra in enumerate(extras, start=2):
        installations.append(
            GNMInstallationInput(
                connection_id=extra.connection_id,
                category=extra.category,
                sanctioned_load_kw=extra.sanctioned_load_kw or prefill.sanctioned_load_kw,
                monthly_units=extra.monthly_units or prefill.monthly_units,
                priority=extra.priority or i,
                is_host=extra.is_host,
            )
        )
    return installations


def build_vnm_plant(
    plant: SolarOptionsPlantInput,
    proposed_kwp: float,
) -> VNMPlantInput:
    return VNMPlantInput(
        proposed_kwp=proposed_kwp,
        same_discom_area=plant.same_discom_area,
        estimated_monthly_generation_kwh=plant.estimated_monthly_generation_kwh,
    )


def build_gnm_plant(
    plant: SolarOptionsPlantInput,
    proposed_kwp: float,
) -> GNMPlantInput:
    return GNMPlantInput(
        proposed_kwp=proposed_kwp,
        same_discom_area=plant.same_discom_area,
        same_consumer_name=plant.same_consumer_name,
        estimated_monthly_generation_kwh=plant.estimated_monthly_generation_kwh,
    )
