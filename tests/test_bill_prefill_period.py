"""Tests for billing-period-aware solar prefill."""

from __future__ import annotations

from datetime import date

from app.application.services.bill_to_solar_inputs import bill_prefill_from_stored
from app.infrastructure.persistence.repository import StoredBillAnalysis


def _stored(**overrides) -> StoredBillAnalysis:
    bill = {
        "consumer_name": {"value": "Test", "parse_status": "ok"},
        "account_id": {"value": "2295199377", "parse_status": "ok"},
        "rr_number": {"value": "7ELGK45173", "parse_status": "ok"},
        "address": {"value": "Bengaluru", "parse_status": "ok"},
        "utility": {"value": "BESCOM", "parse_status": "ok"},
        "discom": {"value": "BESCOM", "parse_status": "ok"},
        "tariff_code": {"value": "LT-1", "parse_status": "ok"},
        "billing_period": {"value": "01/06/2026 - 01/08/2026", "parse_status": "ok"},
        "bill_date": {"value": "2026-08-01", "parse_status": "ok"},
        "units_consumed": {"value": 94, "parse_status": "ok"},
        "sanctioned_load": {"value": 1, "parse_status": "ok"},
        "total_amount": {"value": 482, "parse_status": "ok"},
    }
    bill.update(overrides)
    return StoredBillAnalysis(
        id="jun-july",
        document_id="doc-1",
        consumer_id=None,
        model_name="test",
        discom="BESCOM",
        rr_number="7ELGK45173",
        account_id="2295199377",
        tariff_code="LT-1",
        category="DOMESTIC",
        classification_status="OK",
        consistency_status="OK",
        supported_by_app_v1=True,
        billing_period="01/06/2026 - 01/08/2026",
        bill_date=date(2026, 8, 1),
        units_consumed=94,
        total_amount=482,
        sanctioned_load=1,
        extraction={},
        validation={"bill": bill, "issues": []},
        classification={},
        consistency={},
        canonical_bill={},
        created_at="2026-08-01T00:00:00",
    )


def test_prefill_splits_multi_month_consumption():
    prefill = bill_prefill_from_stored(_stored())
    assert prefill.period_units_kwh == 94
    assert prefill.monthly_units == 47.0
    assert prefill.is_multi_month_period is True
    assert prefill.billing_period_months >= 1.9
    assert prefill.period_consumption_note is not None
    assert "94" in prefill.period_consumption_note
