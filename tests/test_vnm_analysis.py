"""
Tests for Milestone 16 — VNM preliminary analysis.
"""

from __future__ import annotations

from datetime import date

from app.domain.engines.vnm import VNMAnalysisEngine
from app.domain.models.vnm import (
    VNMParticipantInput,
    VNMPlantInput,
    VNMStatus,
)


AS_OF = date(2025, 8, 1)


def _flats(*, shares=(25.0, 25.0, 25.0, 25.0), load=3.0, units=200.0):
    return [
        VNMParticipantInput(
            connection_id=f"Flat-{i+1}",
            category="DOMESTIC",
            sanctioned_load_kw=load,
            monthly_units=units,
            procurement_share_percent=shares[i],
        )
        for i in range(len(shares))
    ]


def test_apartment_vnm_potentially_suitable():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(),
        plant=VNMPlantInput(
            proposed_kwp=8.0,
            same_discom_area=True,
            grid_topology_hint="same_dt",
            estimated_monthly_generation_kwh=800.0,
        ),
        as_of=AS_OF,
    )
    assert result.status == VNMStatus.POTENTIALLY_SUITABLE
    assert "approv" not in result.message.lower()
    assert result.combined_sanctioned_load_kw == 12.0
    assert result.max_plant_kwp == 12.0
    assert len(result.participants) == 4
    # 800 * 25% = 200 allocated each → residual 0
    assert result.participants[0].allocated_generation_kwh == 200.0
    assert result.participants[0].residual_retail_units == 0.0
    assert result.estimated_group_monthly_saving_inr is not None
    assert result.estimated_group_monthly_saving_inr > 0
    assert result.excess_purchase_rate_inr_per_kwh == round(3.66 * 0.75, 4)
    codes = {c.code: c.passed for c in result.conditions}
    assert codes["MIN_PARTICIPANTS"] is True
    assert codes["PLANT_MIN_KWP"] is True
    assert codes["TECHNICAL_FEASIBILITY"] is None


def test_plant_below_min_unsuitable():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(),
        plant=VNMPlantInput(proposed_kwp=3.0, same_discom_area=True),
        as_of=AS_OF,
    )
    assert result.status == VNMStatus.POTENTIALLY_UNSUITABLE
    assert any(c.code == "PLANT_MIN_KWP" and c.passed is False for c in result.conditions)


def test_plant_above_combined_load_unsuitable():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(load=1.0),  # combined 4 kW
        plant=VNMPlantInput(proposed_kwp=5.0, same_discom_area=True),
        as_of=AS_OF,
    )
    assert result.status == VNMStatus.POTENTIALLY_UNSUITABLE
    assert any(
        c.code == "PLANT_MAX_VS_COMBINED_LOAD" and c.passed is False
        for c in result.conditions
    )


def test_shares_must_sum_to_100():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(shares=(40.0, 40.0, 10.0, 5.0)),
        plant=VNMPlantInput(proposed_kwp=6.0, same_discom_area=True),
        as_of=AS_OF,
    )
    assert result.status == VNMStatus.POTENTIALLY_UNSUITABLE
    assert any(
        c.code == "PROCUREMENT_SHARES_SUM" and c.passed is False for c in result.conditions
    )


def test_single_participant_insufficient_or_unsuitable():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(shares=(100.0,))[:1],
        plant=VNMPlantInput(proposed_kwp=5.0, same_discom_area=True),
        as_of=AS_OF,
    )
    assert result.status in {
        VNMStatus.POTENTIALLY_UNSUITABLE,
        VNMStatus.INSUFFICIENT_INFORMATION,
    }
    assert any(c.code == "MIN_PARTICIPANTS" and c.passed is False for c in result.conditions)


def test_missing_same_discom_area():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(),
        plant=VNMPlantInput(proposed_kwp=6.0, same_discom_area=None),
        as_of=AS_OF,
    )
    assert result.status == VNMStatus.INSUFFICIENT_INFORMATION
    assert "same_discom_area" in result.missing_inputs


def test_multi_substation_flags_technical_verification():
    result = VNMAnalysisEngine().analyze(
        participants=_flats(),
        plant=VNMPlantInput(
            proposed_kwp=6.0,
            same_discom_area=True,
            grid_topology_hint="multi_substation",
            estimated_monthly_generation_kwh=600,
        ),
        as_of=AS_OF,
    )
    assert result.status == VNMStatus.TECHNICAL_VERIFICATION_REQUIRED
