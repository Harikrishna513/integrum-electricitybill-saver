"""Tests for Module 1 bill field requirements."""

from __future__ import annotations

from app.domain.models.bill_field_requirements import (
    REQUIRED_CONFIRMATION_FIELDS,
    filter_confirmation_needs,
    should_show_review_field,
)


def test_required_fields_match_module_one_spec():
    assert "consumer_name" in REQUIRED_CONFIRMATION_FIELDS
    assert "units_consumed" in REQUIRED_CONFIRMATION_FIELDS
    assert "energy_charge" in REQUIRED_CONFIRMATION_FIELDS
    assert "rr_number" not in REQUIRED_CONFIRMATION_FIELDS
    assert "consumer_category" not in REQUIRED_CONFIRMATION_FIELDS
    assert "previous_meter_reading" not in REQUIRED_CONFIRMATION_FIELDS


def test_filter_confirmation_needs_drops_optional_fields():
    raw = [
        "units_consumed",
        "rr_number",
        "previous_meter_reading",
        "consumer_category",
    ]
    assert filter_confirmation_needs(raw) == ["units_consumed"]


def test_subsidy_hidden_unless_detected():
    assert should_show_review_field(
        "subsidy",
        extraction_data={"subsidy": {"value": None}},
        validated_data={},
    ) is False
    assert should_show_review_field(
        "subsidy",
        extraction_data={"subsidy": {"value": 0}},
        validated_data={},
    ) is False
    assert should_show_review_field(
        "subsidy",
        extraction_data={"subsidy": {"value": 91.68}},
        validated_data={},
    ) is True


def test_extraction_notes_never_shown():
    assert (
        should_show_review_field(
            "extraction_notes",
            extraction_data={"extraction_notes": {"value": "foo"}},
        )
        is False
    )
