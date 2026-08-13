"""
Agent tool catalog — Milestone 18.

CONCEPT
  Gemini (or a rules router) chooses WHICH tool to call.
  Each tool is a thin wrapper over a deterministic engine.
  Tools return JSON strings — never free-form invented ₹ math inside the LLM.

Spring analogy: like @Service facades the controller/agent calls.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.domain.engines.appliance import ApplianceAnalysisEngine
from app.domain.engines.gnm import GNMAnalysisEngine
from app.domain.engines.gruha_jyothi import GruhaJyothiEngine
from app.domain.engines.metering import NetMeteringEngine
from app.domain.engines.savings import SavingsEngine
from app.domain.engines.solar import SolarAnalysisEngine
from app.domain.engines.tariff import TariffEngine
from app.domain.engines.vnm import VNMAnalysisEngine
from app.domain.models.appliance import HouseholdApplianceProfile
from app.domain.models.gnm import GNMInstallationInput, GNMPlantInput
from app.domain.models.metering import MeteringArrangement
from app.domain.models.solar import SolarProfile
from app.domain.models.vnm import VNMParticipantInput, VNMPlantInput


def _dumps(payload: Any) -> str:
    def convert(obj: Any) -> Any:
        if hasattr(obj, "model_dump"):
            return obj.model_dump(mode="json")
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(v) for v in obj]
        return obj

    return json.dumps(convert(payload), default=str)


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return date.fromisoformat(value)


class TariffArgs(BaseModel):
    units: float = Field(ge=0, description="Monthly consumption in kWh")
    as_of: str = Field(description="ISO date YYYY-MM-DD for tariff rule selection")
    sanctioned_load_kw: float = Field(default=2.0, ge=0)
    category: str = "DOMESTIC"
    discom: str = "BESCOM"
    tariff_code: str | None = "LT-1"


class SavingsArgs(BaseModel):
    current_units: float = Field(ge=0)
    units_saved: float = Field(ge=0)
    as_of: str
    title: str = "Usage reduction"
    sanctioned_load_kw: float = Field(default=2.0, ge=0)


class GruhaArgs(BaseModel):
    category: str = "DOMESTIC"
    as_of: str | None = None
    baseline_fy_2022_23_avg_units: float | None = None
    current_units: float | None = None
    subsidy_line_seen_on_bill: bool | None = None
    consumer_declares_enrolled: bool | None = None


class ApplianceArgs(BaseModel):
    people_count: int = 3
    ac_count: int = 0
    ac_hours_per_day: float | None = None
    geyser: bool = False
    geyser_hours_per_day: float | None = None
    refrigerator: bool = True
    washing_machine: bool = False
    fan_count: int = 3
    bill_units: float | None = None


class SolarArgs(BaseModel):
    monthly_units: float = Field(ge=0)
    as_of: str
    sanctioned_load_kw: float = 3.0
    roof_area_m2: float | None = None
    proposed_kwp: float | None = None
    apply_cfa_estimate: bool = True


class MeteringSettleArgs(BaseModel):
    consumption_kwh: float = Field(ge=0)
    generation_kwh: float = Field(ge=0)
    as_of: str
    arrangement: str = Field(
        default="NET_METERING",
        description="NET_METERING or GROSS_METERING",
    )
    sanctioned_load_kw: float = 3.0
    availed_cfa: bool = False


class VnmJsonArgs(BaseModel):
    as_of: str
    proposed_kwp: float
    participants_json: str = Field(
        description=(
            "JSON array of participants: "
            "[{connection_id, sanctioned_load_kw, monthly_units, "
            "procurement_share_percent, category?}]"
        )
    )
    same_discom_area: bool = True
    estimated_monthly_generation_kwh: float | None = None


class GnmJsonArgs(BaseModel):
    as_of: str
    proposed_kwp: float
    installations_json: str = Field(
        description=(
            "JSON array of installations: "
            "[{connection_id, sanctioned_load_kw, monthly_units, priority, "
            "is_host, category?}]"
        )
    )
    same_discom_area: bool = True
    same_consumer_name: bool = True
    estimated_monthly_generation_kwh: float | None = None


class OfficialDocsArgs(BaseModel):
    query: str = Field(
        description=(
            "Policy / regulatory question for official BESCOM/KERC docs under data/Docs. "
            "Use for latest VNM/GNM/net-metering rule wording — not for ₹ calculation."
        )
    )
    top_k: int = Field(default=5, ge=1, le=10)


def calculate_tariff(
    units: float,
    as_of: str,
    sanctioned_load_kw: float = 2.0,
    category: str = "DOMESTIC",
    discom: str = "BESCOM",
    tariff_code: str | None = "LT-1",
) -> str:
    """Calculate estimated BESCOM domestic bill using versioned TariffEngine (not Gemini math)."""
    result = TariffEngine().calculate(
        discom=discom,
        category=category,
        as_of=_parse_date(as_of),
        units=units,
        sanctioned_load_kw=sanctioned_load_kw,
        tariff_code=tariff_code,
    )
    return _dumps({"tool": "calculate_tariff", "result": result})


def estimate_savings(
    current_units: float,
    units_saved: float,
    as_of: str,
    title: str = "Usage reduction",
    sanctioned_load_kw: float = 2.0,
) -> str:
    """Estimate ₹ saving from an assumed kWh reduction via SavingsEngine → TariffEngine."""
    result = SavingsEngine().estimate_from_units_saved(
        title=title,
        current_units=current_units,
        units_saved=units_saved,
        as_of=_parse_date(as_of),
        sanctioned_load_kw=sanctioned_load_kw,
    )
    return _dumps({"tool": "estimate_savings", "result": result})


def check_gruha_jyothi(
    category: str = "DOMESTIC",
    as_of: str | None = None,
    baseline_fy_2022_23_avg_units: float | None = None,
    current_units: float | None = None,
    subsidy_line_seen_on_bill: bool | None = None,
    consumer_declares_enrolled: bool | None = None,
) -> str:
    """Preliminary Gruha Jyothi condition check — never an approval."""
    result = GruhaJyothiEngine().assess(
        category=category,
        as_of=_parse_date(as_of) if as_of else date.today(),
        baseline_fy_2022_23_avg_units=baseline_fy_2022_23_avg_units,
        current_units=current_units,
        subsidy_line_seen_on_bill=subsidy_line_seen_on_bill,
        consumer_declares_enrolled=consumer_declares_enrolled,
    )
    return _dumps({"tool": "check_gruha_jyothi", "result": result})


def analyze_appliances(
    people_count: int = 3,
    ac_count: int = 0,
    ac_hours_per_day: float | None = None,
    geyser: bool = False,
    geyser_hours_per_day: float | None = None,
    refrigerator: bool = True,
    washing_machine: bool = False,
    fan_count: int = 3,
    bill_units: float | None = None,
) -> str:
    """Estimate appliance kWh shares from questionnaire assumptions (not metered)."""
    profile = HouseholdApplianceProfile(
        people_count=people_count,
        ac_count=ac_count,
        ac_hours_per_day=ac_hours_per_day,
        geyser=geyser,
        geyser_hours_per_day=geyser_hours_per_day,
        refrigerator=refrigerator,
        washing_machine=washing_machine,
        fan_count=fan_count,
    )
    result = ApplianceAnalysisEngine().analyze(profile, bill_units=bill_units)
    return _dumps({"tool": "analyze_appliances", "result": result})


def analyze_solar(
    monthly_units: float,
    as_of: str,
    sanctioned_load_kw: float = 3.0,
    roof_area_m2: float | None = None,
    proposed_kwp: float | None = None,
    apply_cfa_estimate: bool = True,
) -> str:
    """Estimate individual rooftop solar size / economics (simplified offset in solar engine)."""
    profile = SolarProfile(
        monthly_units=monthly_units,
        as_of=_parse_date(as_of),
        sanctioned_load_kw=sanctioned_load_kw,
        roof_area_m2=roof_area_m2,
        proposed_kwp=proposed_kwp,
        apply_cfa_estimate=apply_cfa_estimate,
    )
    result = SolarAnalysisEngine().analyze(profile)
    return _dumps({"tool": "analyze_solar", "result": result})


def settle_metering(
    consumption_kwh: float,
    generation_kwh: float,
    as_of: str,
    arrangement: str = "NET_METERING",
    sanctioned_load_kw: float = 3.0,
    availed_cfa: bool = False,
) -> str:
    """Estimate Net or Gross metering settlement from consumption + generation."""
    arr = MeteringArrangement(arrangement.upper())
    result = NetMeteringEngine().settle(
        arrangement=arr,
        consumption_kwh=consumption_kwh,
        generation_kwh=generation_kwh,
        as_of=_parse_date(as_of),
        sanctioned_load_kw=sanctioned_load_kw,
        availed_cfa=availed_cfa,
    )
    return _dumps({"tool": "settle_metering", "result": result})


def list_metering_concepts() -> str:
    """Explain Net vs Gross vs VNM vs GNM concepts."""
    concepts = NetMeteringEngine().list_concepts()
    return _dumps(
        {
            "tool": "list_metering_concepts",
            "concepts": [c.model_dump() for c in concepts],
        }
    )


def analyze_vnm(
    as_of: str,
    proposed_kwp: float,
    participants_json: str,
    same_discom_area: bool = True,
    estimated_monthly_generation_kwh: float | None = None,
) -> str:
    """
    Preliminary VNM analysis for apartment/community participants.
    participants_json: JSON list of participant objects. Never an approval.
    """
    raw = json.loads(participants_json)
    participants = [
        VNMParticipantInput(
            connection_id=p["connection_id"],
            category=p.get("category", "DOMESTIC"),
            sanctioned_load_kw=p["sanctioned_load_kw"],
            monthly_units=p["monthly_units"],
            procurement_share_percent=p["procurement_share_percent"],
        )
        for p in raw
    ]
    plant = VNMPlantInput(
        proposed_kwp=proposed_kwp,
        same_discom_area=same_discom_area,
        estimated_monthly_generation_kwh=estimated_monthly_generation_kwh,
    )
    result = VNMAnalysisEngine().analyze(
        participants=participants,
        plant=plant,
        as_of=_parse_date(as_of),
    )
    return _dumps({"tool": "analyze_vnm", "result": result})


def analyze_gnm(
    as_of: str,
    proposed_kwp: float,
    installations_json: str,
    same_discom_area: bool = True,
    same_consumer_name: bool = True,
    estimated_monthly_generation_kwh: float | None = None,
) -> str:
    """
    Preliminary GNM analysis for same-name multi-RR consumer.
    installations_json: JSON list of installation objects. Never an approval.
    """
    raw = json.loads(installations_json)
    installations = [
        GNMInstallationInput(
            connection_id=p["connection_id"],
            category=p.get("category", "DOMESTIC"),
            sanctioned_load_kw=p["sanctioned_load_kw"],
            monthly_units=p["monthly_units"],
            priority=p["priority"],
            is_host=bool(p.get("is_host", False)),
        )
        for p in raw
    ]
    plant = GNMPlantInput(
        proposed_kwp=proposed_kwp,
        same_discom_area=same_discom_area,
        same_consumer_name=same_consumer_name,
        estimated_monthly_generation_kwh=estimated_monthly_generation_kwh,
    )
    result = GNMAnalysisEngine().analyze(
        installations=installations,
        plant=plant,
        as_of=_parse_date(as_of),
    )
    return _dumps({"tool": "analyze_gnm", "result": result})


def search_official_docs(query: str, top_k: int = 5) -> str:
    """Search local official docs in data/Docs (VNM/GNM/KSEC). Never invent ₹."""
    from app.application.services.rag_service import OfficialSourceRetriever

    result = OfficialSourceRetriever().search(query, top_k=top_k)
    return _dumps({"tool": "search_official_docs", "result": result})


_TOOL_NAMES = [
    "calculate_tariff",
    "estimate_savings",
    "check_gruha_jyothi",
    "analyze_appliances",
    "analyze_solar",
    "settle_metering",
    "list_metering_concepts",
    "analyze_vnm",
    "analyze_gnm",
    "search_official_docs",
    "list_agent_tools",
]


def list_agent_tools() -> str:
    """List available agent tools and remind that money comes from engines, not the LLM."""
    return _dumps(
        {
            "tool": "list_agent_tools",
            "tools": list(_TOOL_NAMES),
            "rule": (
                "LLM routes questions to tools. Deterministic engines calculate money, "
                "tariffs, eligibility pre-screens, and savings."
            ),
        }
    )


def build_agent_tools() -> list[StructuredTool]:
    """LangChain StructuredTool list for bind_tools / agent loop."""
    return [
        StructuredTool.from_function(
            func=calculate_tariff,
            name="calculate_tariff",
            description=calculate_tariff.__doc__ or "Calculate tariff",
            args_schema=TariffArgs,
        ),
        StructuredTool.from_function(
            func=estimate_savings,
            name="estimate_savings",
            description=estimate_savings.__doc__ or "Estimate savings",
            args_schema=SavingsArgs,
        ),
        StructuredTool.from_function(
            func=check_gruha_jyothi,
            name="check_gruha_jyothi",
            description=check_gruha_jyothi.__doc__ or "Check Gruha Jyothi",
            args_schema=GruhaArgs,
        ),
        StructuredTool.from_function(
            func=analyze_appliances,
            name="analyze_appliances",
            description=analyze_appliances.__doc__ or "Analyze appliances",
            args_schema=ApplianceArgs,
        ),
        StructuredTool.from_function(
            func=analyze_solar,
            name="analyze_solar",
            description=analyze_solar.__doc__ or "Analyze solar",
            args_schema=SolarArgs,
        ),
        StructuredTool.from_function(
            func=settle_metering,
            name="settle_metering",
            description=settle_metering.__doc__ or "Settle metering",
            args_schema=MeteringSettleArgs,
        ),
        StructuredTool.from_function(
            func=list_metering_concepts,
            name="list_metering_concepts",
            description=list_metering_concepts.__doc__ or "List metering concepts",
        ),
        StructuredTool.from_function(
            func=analyze_vnm,
            name="analyze_vnm",
            description=analyze_vnm.__doc__ or "Analyze VNM",
            args_schema=VnmJsonArgs,
        ),
        StructuredTool.from_function(
            func=analyze_gnm,
            name="analyze_gnm",
            description=analyze_gnm.__doc__ or "Analyze GNM",
            args_schema=GnmJsonArgs,
        ),
        StructuredTool.from_function(
            func=search_official_docs,
            name="search_official_docs",
            description=search_official_docs.__doc__ or "Search official docs",
            args_schema=OfficialDocsArgs,
        ),
        StructuredTool.from_function(
            func=list_agent_tools,
            name="list_agent_tools",
            description=list_agent_tools.__doc__ or "List tools",
        ),
    ]


TOOL_BY_NAME: dict[str, StructuredTool] = {}


def get_tool_map() -> dict[str, StructuredTool]:
    global TOOL_BY_NAME
    if not TOOL_BY_NAME:
        TOOL_BY_NAME = {t.name: t for t in build_agent_tools()}
    return TOOL_BY_NAME
