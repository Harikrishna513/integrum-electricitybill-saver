from __future__ import annotations

from app.domain.models.history import (
    BillHistoryItem,
    BillHistorySummary,
    DuplicateBillWarning,
)
from app.infrastructure.persistence.repository import StoredBillAnalysis


def build_history_summary(
    *,
    consumer_id: str,
    discom: str | None,
    rr_number: str | None,
    account_id: str | None,
    analyses: list[StoredBillAnalysis],
    duplicate_warnings: list[DuplicateBillWarning] | None = None,
) -> BillHistorySummary:
    items = [
        BillHistoryItem(
            analysis_id=a.id,
            document_id=a.document_id,
            bill_date=a.bill_date,
            billing_period=a.billing_period,
            units_consumed=a.units_consumed,
            total_amount=a.total_amount,
            tariff_code=a.tariff_code,
            category=a.category,
            consistency_status=a.consistency_status,
            created_at=a.created_at,
        )
        for a in analyses
    ]
    # Prefer bill_date ascending; undated bills go last
    items.sort(key=lambda b: (b.bill_date is None, b.bill_date or date_min(), b.created_at or ""))

    return BillHistorySummary(
        consumer_id=consumer_id,
        discom=discom,
        rr_number=rr_number,
        account_id=account_id,
        bill_count=len(items),
        bills=items,
        duplicate_warnings=duplicate_warnings or [],
    )


def date_min():
    from datetime import date

    return date.min


def find_duplicate_warnings(
    *,
    incoming: StoredBillAnalysis,
    existing_for_consumer: list[StoredBillAnalysis],
    incoming_sha256: str | None = None,
    existing_sha256_by_analysis_id: dict[str, str] | None = None,
) -> list[DuplicateBillWarning]:
    """
    Compare the newly saved bill against prior bills for the same consumer.
    """
    warnings: list[DuplicateBillWarning] = []
    sha_map = existing_sha256_by_analysis_id or {}

    for prior in existing_for_consumer:
        if prior.id == incoming.id:
            continue

        if (
            incoming.bill_date is not None
            and prior.bill_date is not None
            and incoming.bill_date == prior.bill_date
        ):
            warnings.append(
                DuplicateBillWarning(
                    code="POSSIBLE_DUPLICATE_BILL_DATE",
                    matched_analysis_id=prior.id,
                    match_reason="same_bill_date",
                    message=(
                        f"Another saved bill for this consumer has the same bill_date "
                        f"({incoming.bill_date.isoformat()}). Confirm this is not a duplicate upload."
                    ),
                )
            )

        if (
            incoming.billing_period
            and prior.billing_period
            and _normalize_period(incoming.billing_period)
            == _normalize_period(prior.billing_period)
        ):
            warnings.append(
                DuplicateBillWarning(
                    code="POSSIBLE_DUPLICATE_BILLING_PERIOD",
                    matched_analysis_id=prior.id,
                    match_reason="same_billing_period",
                    message=(
                        f"Another saved bill has the same billing_period "
                        f"({incoming.billing_period!r}). Confirm this is not a duplicate."
                    ),
                )
            )

        if incoming_sha256 and sha_map.get(prior.id) == incoming_sha256:
            warnings.append(
                DuplicateBillWarning(
                    code="POSSIBLE_DUPLICATE_FILE_HASH",
                    matched_analysis_id=prior.id,
                    match_reason="same_sha256",
                    message=(
                        "An identical file (same SHA-256) was already analyzed for this consumer."
                    ),
                )
            )

    # One warning per duplicate type — multiple prior bills may trigger the same message.
    unique: list[DuplicateBillWarning] = []
    seen_codes: set[str] = set()
    for w in warnings:
        if w.code in seen_codes:
            continue
        seen_codes.add(w.code)
        unique.append(w)
    return unique


def _normalize_period(value: str) -> str:
    return " ".join(value.strip().lower().split())
