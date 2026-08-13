"""
Tests for Milestone 17 — GNM preliminary analysis.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.gnm import GNMAnalysisEngine
from app.domain.models.gnm import GNMInstallationInput, GNMPlantInput, GNMStatus


AS_OF = date(2025, 8, 1)


def _installs():
    return [
        GNMInstallationInput(
            connection_id="RR-HOST",
            category="DOMESTIC",
            sanctioned_load_kw=5,
            monthly_units=50,  # low host use → lapse from 20% band
            priority=1,
            is_host=True,
        ),
        GNMInstallationInput(
            connection_id="RR-2",
            category="DOMESTIC",
            sanctioned_load_kw=3,
            monthly_units=200,
            priority=2,
            is_host=False,
        ),
        GNMInstallationInput(
            connection_id="RR-3",
            category="DOMESTIC",
            sanctioned_load_kw=2,
            monthly_units=150,
            priority=3,
            is_host=False,
        ),
    ]


def test_gnm_host_lapse_and_priority_waterfall():
    # G=1000 → reserved 200; host takes min(50,200)=50; lapsed=150; pool=800
    # priority1 host need remaining 0; RR-2 takes 200; RR-3 takes 150; unallocated=450
    result = GNMAnalysisEngine().analyze(
        installations=_installs(),
        plant=GNMPlantInput(
            proposed_kwp=6.0,
            same_discom_area=True,
            same_consumer_name=True,
            estimated_monthly_generation_kwh=1000.0,
            grid_topology_hint="same_dt",
        ),
        as_of=AS_OF,
    )
    assert result.status == GNMStatus.POTENTIALLY_SUITABLE
    assert "approv" not in result.message.lower()
    assert result.host_reserved_kwh == 200.0
    assert result.lapsed_kwh == 150.0
    assert result.unallocated_generation_kwh == 450.0

    by_id = {i.connection_id: i for i in result.installations}
    assert by_id["RR-HOST"].allocated_generation_kwh == 50.0
    assert by_id["RR-2"].allocated_generation_kwh == 200.0
    assert by_id["RR-3"].allocated_generation_kwh == 150.0
    # leftover surplus attributed to host for export credit estimate
    assert by_id["RR-HOST"].surplus_export_kwh == 450.0
    assert result.estimated_group_monthly_saving_inr is not None
    assert result.estimated_group_monthly_saving_inr > 0


def test_plant_below_min_unsuitable():
    result = GNMAnalysisEngine().analyze(
        installations=_installs(),
        plant=GNMPlantInput(
            proposed_kwp=4.0,
            same_discom_area=True,
            same_consumer_name=True,
        ),
        as_of=AS_OF,
    )
    assert result.status == GNMStatus.POTENTIALLY_UNSUITABLE
    assert any(c.code == "PLANT_MIN_KWP" and c.passed is False for c in result.conditions)


def test_duplicate_priority_unsuitable():
    installs = _installs()
    installs[2].priority = 2
    result = GNMAnalysisEngine().analyze(
        installations=installs,
        plant=GNMPlantInput(
            proposed_kwp=6.0,
            same_discom_area=True,
            same_consumer_name=True,
        ),
        as_of=AS_OF,
    )
    assert result.status == GNMStatus.POTENTIALLY_UNSUITABLE
    assert any(
        c.code == "UNIQUE_PRIORITIES" and c.passed is False for c in result.conditions
    )


def test_missing_same_consumer_name():
    result = GNMAnalysisEngine().analyze(
        installations=_installs(),
        plant=GNMPlantInput(
            proposed_kwp=6.0,
            same_discom_area=True,
            same_consumer_name=None,
        ),
        as_of=AS_OF,
    )
    assert result.status == GNMStatus.INSUFFICIENT_INFORMATION
    assert "same_consumer_name" in result.missing_inputs


def test_no_host_unsuitable_or_insufficient():
    installs = _installs()
    for i in installs:
        i.is_host = False
    result = GNMAnalysisEngine().analyze(
        installations=installs,
        plant=GNMPlantInput(
            proposed_kwp=6.0,
            same_discom_area=True,
            same_consumer_name=True,
        ),
        as_of=AS_OF,
    )
    assert result.status in {
        GNMStatus.POTENTIALLY_UNSUITABLE,
        GNMStatus.INSUFFICIENT_INFORMATION,
    }
    assert any(c.code == "SINGLE_HOST" and c.passed is False for c in result.conditions)


def test_multi_substation_technical_verification():
    result = GNMAnalysisEngine().analyze(
        installations=_installs(),
        plant=GNMPlantInput(
            proposed_kwp=6.0,
            same_discom_area=True,
            same_consumer_name=True,
            estimated_monthly_generation_kwh=500,
            grid_topology_hint="multi_substation",
        ),
        as_of=AS_OF,
    )
    assert result.status == GNMStatus.TECHNICAL_VERIFICATION_REQUIRED
