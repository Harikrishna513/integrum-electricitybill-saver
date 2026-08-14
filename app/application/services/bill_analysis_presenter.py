"""
Bill Analysis presenter — maps domain pipeline results to UI-friendly DTOs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.api.middleware import build_support_gate
from app.application.use_cases.confirm_bill import ConfirmBillResult
from app.application.use_cases.extract_bill import ExtractBillResult
from app.domain.models.bill_analysis import (
    BillAnalysisView,
    BillCalculationView,
    BillFieldView,
    BillSectionView,
    FieldAuditEntry,
    HistoryBillView,
    HistorySummaryView,
    SupportView,
    ValidationIssueView,
)
from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.category import CategoryClassificationResult
from app.domain.models.consistency import BillConsistencyResult
from app.domain.models.document import BillDocument
from app.domain.models.extracted_field import ConfidenceLevel
from app.domain.models.history import BillHistorySummary
from app.domain.models.validated_bill import BillValidationResult
from app.domain.services.bill_calculator import BillCalculator

FIELD_SECTIONS: list[tuple[str, str, list[tuple[str, str]]]] = [
    (
        "consumer",
        "Consumer Details",
        [
            ("consumer_name", "Consumer Name"),
            ("account_id", "Account ID"),
            ("rr_number", "RR Number"),
            ("address", "Address"),
        ],
    ),
    (
        "connection",
        "Connection Details",
        [
            ("utility", "Utility"),
            ("discom", "DISCOM"),
            ("consumer_category", "Consumer Category"),
            ("tariff_code", "Tariff Code"),
            ("sanctioned_load", "Sanctioned Load (kW)"),
        ],
    ),
    (
        "billing",
        "Billing Details",
        [
            ("billing_period", "Billing Period"),
            ("bill_date", "Bill Date"),
            ("due_date", "Due Date"),
        ],
    ),
    (
        "meter",
        "Meter Details",
        [
            ("previous_meter_reading", "Previous Meter Reading"),
            ("current_meter_reading", "Current Meter Reading"),
            ("units_consumed", "Units Consumed (kWh)"),
        ],
    ),
    (
        "charges",
        "Charges",
        [
            ("energy_charge", "Energy Charge"),
            ("fixed_charge", "Fixed Charge"),
            ("electricity_tax", "Electricity Tax"),
            ("fppca", "FPPCA"),
            ("other_charges", "Other Charges"),
            ("subsidy", "Subsidy"),
            ("arrears", "Arrears"),
            ("late_payment_charge", "Late Payment Charge"),
            ("total_amount", "Total Amount"),
        ],
    ),
    (
        "document",
        "Document Information",
        [
            ("document_language", "Language"),
            ("is_bescom_bill", "BESCOM Bill"),
            ("extraction_notes", "Extraction Notes"),
        ],
    ),
]

from app.domain.models.bill_field_requirements import (
    HIDDEN_REVIEW_FIELDS,
    REQUIRED_CONFIRMATION_FIELDS,
    is_required_for_confirmation,
    should_show_review_field,
)


class BillAnalysisPresenter:
    def __init__(self, calculator: BillCalculator | None = None) -> None:
        self._calculator = calculator or BillCalculator()

    def from_extract(self, result: ExtractBillResult) -> BillAnalysisView:
        support_gate = build_support_gate(
            validation=result.validation,
            classification=result.classification,
        )
        needs = result.needs_confirmation
        confirmed = len(needs) == 0
        status = self._status(support_gate, needs, confirmed=False)
        bescom_hint = _likely_bescom_partial(support_gate, result.validation)
        calculations = self._maybe_calculate(
            result.validation,
            result.consistency,
            support_gate["supported_for_money_engines"],
            confirmed=confirmed,
        )
        return BillAnalysisView(
            analysis_id=result.analysis_id or "",
            status=status,
            message=self._message(
                status, support_gate, needs, is_bescom_hint=bescom_hint
            ),
            document=result.document.model_dump(mode="json"),
            sections=self._sections(
                result.extraction, result.validation, needs, result.classification
            ),
            support=self._support(support_gate, result.classification),
            validation_issues=self._validation_issues(result.validation),
            consistency_warnings=self._consistency_warnings(result.consistency),
            needs_confirmation=needs,
            calculations=calculations,
            history=self._history(result.history),
            confirmed=confirmed,
        )

    def from_confirm(self, result: ConfirmBillResult) -> BillAnalysisView:
        support_gate = build_support_gate(
            validation=result.validation,
            classification=result.classification,
        )
        needs = result.needs_confirmation
        confirmed = len(needs) == 0
        status = self._status(support_gate, needs, confirmed=confirmed)
        calculations = self._maybe_calculate(
            result.validation,
            result.consistency,
            support_gate["supported_for_money_engines"],
            confirmed=confirmed,
        )
        audit = _load_audit(result.stored.validation)
        view = BillAnalysisView(
            analysis_id=result.analysis_id,
            status=status,
            message=(
                _monthly_summary_message(result.validation, calculations)
                if confirmed and calculations
                else result.confirmation.message
            ),
            document={"analysis_id": result.analysis_id},
            sections=self._sections(
                result.extraction, result.validation, needs, result.classification
            ),
            support=self._support(support_gate, result.classification),
            validation_issues=self._validation_issues(result.validation),
            consistency_warnings=self._consistency_warnings(result.consistency),
            needs_confirmation=needs,
            calculations=calculations,
            history=None,
            corrections_audit=audit,
            confirmed=confirmed,
        )
        return view

    def _status(
        self,
        support_gate: dict[str, Any],
        needs: list[str],
        *,
        confirmed: bool,
    ) -> str:
        """needs_review until required fields are confirmed; unsupported only after confirm still blocked."""
        if needs:
            return "needs_review"
        if support_gate["supported_for_money_engines"]:
            if confirmed:
                return "ready"
            return "needs_review"
        if not confirmed:
            # Partial / unclear bill — let user complete DISCOM, tariff, category, etc.
            return "needs_review"
        return "unsupported"

    def _message(
        self,
        status: str,
        support_gate: dict[str, Any],
        needs: list[str],
        *,
        is_bescom_hint: bool | None = None,
    ) -> str:
        if status == "unsupported":
            return (
                support_gate.get("user_guidance")
                or "This bill is outside the supported Karnataka / BESCOM domestic scope."
            )
        if needs or (status == "needs_review" and not support_gate["supported_for_money_engines"]):
            if is_bescom_hint:
                return (
                    "We detected a possible BESCOM bill, but the image may be partial or "
                    "some details are missing. Please complete and verify the required fields "
                    "(marked with *) — including DISCOM, tariff code, and account details."
                )
            return (
                "We extracted your bill. Please review and confirm the required fields "
                "(marked with *) before continuing."
            )
        return "Bill analysis is ready."

    def _support(
        self,
        support_gate: dict[str, Any],
        classification: CategoryClassificationResult,
    ) -> SupportView:
        return SupportView(
            supported=bool(support_gate["supported_for_money_engines"]),
            discom=None,
            category=classification.category.value,
            is_bescom_bill=support_gate.get("is_bescom_bill"),
            can_analyze=bool(support_gate.get("can_continue_domestic_analysis")),
            message=str(support_gate.get("user_guidance") or ""),
            block_reasons=list(support_gate.get("block_reasons") or []),
        )

    def _sections(
        self,
        extraction: ElectricityBillExtraction,
        validation: BillValidationResult,
        needs: list[str],
        classification: CategoryClassificationResult | None = None,
    ) -> list[BillSectionView]:
        extraction_data = extraction.model_dump()
        bill_data = validation.bill.model_dump()
        sections: list[BillSectionView] = []

        for section_id, title, fields in FIELD_SECTIONS:
            field_views: list[BillFieldView] = []
            for name, label in fields:
                if not should_show_review_field(
                    name,
                    extraction_data=extraction_data,
                    validated_data=bill_data,
                ):
                    continue
                extracted = extraction_data.get(name, {})
                validated = bill_data.get(name, {})
                value = validated.get("value")
                if value is None:
                    value = extracted.get("value")
                if (
                    name == "consumer_category"
                    and (value is None or value == "")
                    and classification is not None
                    and classification.category.value != "UNKNOWN"
                ):
                    value = classification.category.value.title()
                confidence = float(
                    validated.get("confidence", extracted.get("confidence", 0.0)) or 0.0
                )
                level_raw = validated.get("level", extracted.get("level", "MISSING"))
                level = str(level_raw.value if hasattr(level_raw, "value") else level_raw)
                source = str(validated.get("source", extracted.get("source", "unknown")))
                required = is_required_for_confirmation(name)
                if name in HIDDEN_REVIEW_FIELDS:
                    needs_verify = False
                elif name in needs:
                    needs_verify = True
                elif required and level in {
                    ConfidenceLevel.LOW.value,
                    ConfidenceLevel.MISSING.value,
                }:
                    needs_verify = True
                else:
                    needs_verify = False
                field_views.append(
                    BillFieldView(
                        name=name,
                        label=label,
                        section=section_id,
                        value=value,
                        display_value=_display(value),
                        confidence=confidence,
                        level=level,  # type: ignore[arg-type]
                        source=source,
                        needs_verification=needs_verify,
                        required=required,
                    )
                )
            if field_views:
                sections.append(BillSectionView(id=section_id, title=title, fields=field_views))
        return sections

    def _validation_issues(self, validation: BillValidationResult) -> list[ValidationIssueView]:
        return [
            ValidationIssueView(
                code=i.code,
                message=i.message,
                field=i.field,
                severity=i.severity.value,
            )
            for i in validation.issues
        ]

    def _consistency_warnings(self, consistency: BillConsistencyResult) -> list[str]:
        return [i.message for i in consistency.issues if i.severity.value != "INFO"]

    def _maybe_calculate(
        self,
        validation: BillValidationResult,
        consistency: BillConsistencyResult,
        supported: bool,
        *,
        confirmed: bool,
    ) -> BillCalculationView | None:
        if not supported:
            return None
        if not confirmed and any(
            f in validation.fields_needing_confirmation for f in REQUIRED_CONFIRMATION_FIELDS
        ):
            return None
        return self._calculator.calculate(validation.bill, consistency=consistency)

    def _history(self, history: BillHistorySummary | None) -> HistorySummaryView | None:
        if history is None:
            return None
        return HistorySummaryView(
            consumer_id=history.consumer_id,
            bill_count=history.bill_count,
            ready_for_trend_analysis=history.ready_for_trend_analysis,
            bills=[
                HistoryBillView(
                    analysis_id=b.analysis_id,
                    billing_period=b.billing_period,
                    bill_date=b.bill_date.isoformat() if b.bill_date else None,
                    units_consumed=b.units_consumed,
                    total_amount=b.total_amount,
                )
                for b in history.bills
            ],
            duplicate_warnings=[w.message for w in history.duplicate_warnings],
        )


def build_batch_item(
    *,
    filename: str,
    result: ExtractBillResult | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    if error or result is None:
        return {
            "filename": filename,
            "status": "error",
            "error": error or "Processing failed.",
        }
    presenter = BillAnalysisPresenter()
    view = presenter.from_extract(result)
    return {
        "filename": filename,
        "status": view.status,
        "analysis_id": result.analysis_id,
        "billing_period": result.stored.billing_period if result.stored else None,
        "units_consumed": result.stored.units_consumed if result.stored else None,
        "total_amount": result.stored.total_amount if result.stored else None,
        "needs_confirmation": view.needs_confirmation,
        "duplicate_warnings": view.history.duplicate_warnings if view.history else [],
        "analysis": view.model_dump(mode="json"),
    }


def append_audit_entries(
    validation: BillValidationResult,
    entries: list[FieldAuditEntry],
) -> BillValidationResult:
    data = validation.model_dump(mode="python")
    existing = data.get("corrections_audit") or []
    if not isinstance(existing, list):
        existing = []
    data["corrections_audit"] = existing + [e.model_dump(mode="json") for e in entries]
    return BillValidationResult.model_validate(data)


def _load_audit(validation_json: dict[str, Any]) -> list[FieldAuditEntry]:
    raw = validation_json.get("corrections_audit") if isinstance(validation_json, dict) else None
    if not isinstance(raw, list):
        return []
    return [FieldAuditEntry.model_validate(item) for item in raw]


def _likely_bescom_partial(
    support_gate: dict[str, Any],
    validation: BillValidationResult,
) -> bool:
    """True when bill looks like BESCOM but support gate is not open yet (partial crop, etc.)."""
    if support_gate.get("supported_for_money_engines"):
        return False
    bill = validation.bill
    if support_gate.get("is_bescom_bill") is True:
        return True
    discom = (bill.discom.value or bill.utility.value or "").upper()
    if "BESCOM" in discom:
        return True
    if bill.units_consumed.value is not None and bill.total_amount.value is not None:
        return support_gate.get("is_bescom_bill") is not False
    return False


def _monthly_summary_message(
    validation: BillValidationResult,
    calculations: BillCalculationView | None,
) -> str:
    bill = validation.bill
    units = calculations.units_consumed if calculations else bill.units_consumed.value
    total = calculations.total_amount if calculations else bill.total_amount.value
    period = bill.billing_period.value
    if units is not None and total is not None:
        period_bit = f" for {period}" if period else " this month"
        return (
            f"Bill confirmed. You paid ₹{total:,.2f} for {units:g} kWh{period_bit}."
        )
    return "Bill analysis is ready. Your bill has been confirmed."


def _display(value: Any) -> str:
    if value is None or value == "":
        return "Not detected — please enter"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:g}"
    return str(value)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
