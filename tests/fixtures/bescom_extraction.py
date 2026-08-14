"""Shared BESCOM extraction fixtures for tests."""

from __future__ import annotations

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ExtractedField


def complete_bescom_extraction(**overrides) -> ElectricityBillExtraction:
    base = dict(
        utility=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
        discom=ExtractedField(value="BESCOM", confidence=0.99, source="bill"),
        consumer_name=ExtractedField(value="Test Consumer", confidence=0.95, source="bill"),
        account_id=ExtractedField(value="ACC123", confidence=0.95, source="bill"),
        rr_number=ExtractedField(value="RR123", confidence=0.9, source="bill"),
        address=ExtractedField(value="Bengaluru", confidence=0.9, source="bill"),
        consumer_category=ExtractedField(value="Domestic", confidence=0.9, source="bill"),
        tariff_code=ExtractedField(value="LT-1", confidence=0.95, source="bill"),
        billing_period=ExtractedField(value="Jul-2026", confidence=0.9, source="bill"),
        bill_date=ExtractedField(value="01/08/2026", confidence=0.9, source="bill"),
        due_date=ExtractedField(value="15/08/2026", confidence=0.9, source="bill"),
        previous_meter_reading=ExtractedField(value=1000, confidence=0.9, source="bill"),
        current_meter_reading=ExtractedField(value=1286, confidence=0.9, source="bill"),
        units_consumed=ExtractedField(value=286, confidence=0.96, source="bill"),
        sanctioned_load=ExtractedField(value=3, confidence=0.9, source="bill"),
        energy_charge=ExtractedField(value=1200, confidence=0.95, source="bill"),
        fixed_charge=ExtractedField(value=150, confidence=0.95, source="bill"),
        electricity_tax=ExtractedField(value=50, confidence=0.9, source="bill"),
        fppca=ExtractedField(value=20, confidence=0.9, source="bill"),
        other_charges=ExtractedField(value=10, confidence=0.9, source="bill"),
        total_amount=ExtractedField(value=1834.5, confidence=0.97, source="bill"),
        document_language=ExtractedField(value="English", confidence=0.9, source="bill"),
        is_bescom_bill=ExtractedField(value=True, confidence=0.99, source="bill"),
    )
    base.update(overrides)
    return ElectricityBillExtraction(**base)
