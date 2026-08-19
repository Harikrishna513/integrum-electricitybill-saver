from __future__ import annotations

from app.domain.models.bill_extraction import ElectricityBillExtraction
from app.domain.models.extracted_field import ConfidenceLevel, ExtractedField
from app.domain.models.validated_bill import (
    BillValidationResult,
    CanonicalElectricityBill,
    ParseStatus,
    ValidatedBool,
    ValidatedDate,
    ValidatedNumber,
    ValidatedString,
    ValidationIssue,
    ValidationSeverity,
)
from app.domain.services.field_coercion import (
    is_implausible_future_date,
    normalize_tariff_code,
    normalize_text,
    parse_bool,
    parse_date,
    parse_number,
)

from app.domain.models.bill_field_requirements import REQUIRED_CONFIRMATION_FIELDS

_CRITICAL_FIELDS = tuple(REQUIRED_CONFIRMATION_FIELDS)


class BillExtractionValidator:
    """Pure domain validator — no I/O, no Gemini."""

    def validate(self, extraction: ElectricityBillExtraction) -> BillValidationResult:
        issues: list[ValidationIssue] = []

        bill = CanonicalElectricityBill(
            utility=self._as_string(extraction.utility, "utility", issues),
            discom=self._as_string(extraction.discom, "discom", issues, uppercase=True),
            consumer_name=self._as_string(extraction.consumer_name, "consumer_name", issues),
            account_id=self._as_string(extraction.account_id, "account_id", issues),
            rr_number=self._as_string(extraction.rr_number, "rr_number", issues),
            address=self._as_string(extraction.address, "address", issues),
            consumer_category=self._as_string(
                extraction.consumer_category, "consumer_category", issues
            ),
            tariff_code=self._as_tariff(extraction.tariff_code, issues),
            billing_period=self._as_string(
                extraction.billing_period, "billing_period", issues
            ),
            bill_date=self._as_date(extraction.bill_date, "bill_date", issues),
            due_date=self._as_date(extraction.due_date, "due_date", issues),
            previous_meter_reading=self._as_number(
                extraction.previous_meter_reading,
                "previous_meter_reading",
                issues,
                min_value=0,
            ),
            current_meter_reading=self._as_number(
                extraction.current_meter_reading,
                "current_meter_reading",
                issues,
                min_value=0,
            ),
            units_consumed=self._as_number(
                extraction.units_consumed,
                "units_consumed",
                issues,
                min_value=0,
            ),
            sanctioned_load=self._as_number(
                extraction.sanctioned_load,
                "sanctioned_load",
                issues,
                min_value=0,
            ),
            energy_charge=self._as_number(extraction.energy_charge, "energy_charge", issues),
            fixed_charge=self._as_number(extraction.fixed_charge, "fixed_charge", issues),
            electricity_tax=self._as_number(
                extraction.electricity_tax, "electricity_tax", issues
            ),
            fppca=self._as_number(extraction.fppca, "fppca", issues),
            other_charges=self._as_number(extraction.other_charges, "other_charges", issues),
            subsidy=self._as_number(extraction.subsidy, "subsidy", issues),
            arrears=self._as_number(extraction.arrears, "arrears", issues),
            late_payment_charge=self._as_number(
                extraction.late_payment_charge, "late_payment_charge", issues
            ),
            total_amount=self._as_number(extraction.total_amount, "total_amount", issues),
            document_language=self._as_string(
                extraction.document_language, "document_language", issues
            ),
            is_bescom_bill=self._as_bool(extraction.is_bescom_bill, "is_bescom_bill", issues),
            extraction_notes=self._as_string(
                extraction.extraction_notes, "extraction_notes", issues
            ),
        )

        self._add_cross_date_notes(bill, issues)
        self._add_bescom_hint(bill, issues)

        fields_needing_confirmation = self._fields_needing_confirmation(bill, issues)

        if not bill.has_usable_units and not bill.has_usable_total:
            issues.append(
                ValidationIssue(
                    code="INSUFFICIENT_CORE_FIELDS",
                    field=None,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        "Could not obtain usable units_consumed or total_amount. "
                        "Please confirm values or upload a clearer bill."
                    ),
                )
            )

        return BillValidationResult(
            bill=bill,
            issues=issues,
            fields_needing_confirmation=fields_needing_confirmation,
        )

    def _base_meta(self, field: ExtractedField) -> dict:
        return {
            "raw": field.value,
            "confidence": field.confidence,
            "level": field.level,
            "source": field.source,
        }

    def _as_string(
        self,
        field: ExtractedField,
        name: str,
        issues: list[ValidationIssue],
        *,
        uppercase: bool = False,
    ) -> ValidatedString:
        meta = self._base_meta(field)
        if field.value is None or field.value == "":
            return ValidatedString(**meta, value=None, parse_status=ParseStatus.MISSING)

        text = normalize_text(field.value)
        if text is None:
            issues.append(
                ValidationIssue(
                    code="STRING_PARSE_FAILED",
                    field=name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Could not normalize string for {name}.",
                )
            )
            return ValidatedString(**meta, value=None, parse_status=ParseStatus.PARSE_FAILED)

        if uppercase:
            text = text.upper()
            coerced = str(field.value).strip().upper() != text
        else:
            coerced = str(field.value).strip() != text

        return ValidatedString(
            **meta,
            value=text,
            parse_status=ParseStatus.OK,
            coerced=coerced,
        )

    def _as_tariff(
        self,
        field: ExtractedField,
        issues: list[ValidationIssue],
    ) -> ValidatedString:
        meta = self._base_meta(field)
        if field.value is None or field.value == "":
            return ValidatedString(**meta, value=None, parse_status=ParseStatus.MISSING)

        code = normalize_tariff_code(field.value)
        if code is None:
            issues.append(
                ValidationIssue(
                    code="TARIFF_PARSE_FAILED",
                    field="tariff_code",
                    severity=ValidationSeverity.WARNING,
                    message="Could not normalize tariff_code.",
                )
            )
            return ValidatedString(**meta, value=None, parse_status=ParseStatus.PARSE_FAILED)

        coerced = normalize_text(field.value) != code
        return ValidatedString(
            **meta,
            value=code,
            parse_status=ParseStatus.OK,
            coerced=coerced,
        )

    def _as_number(
        self,
        field: ExtractedField,
        name: str,
        issues: list[ValidationIssue],
        *,
        min_value: float | None = None,
    ) -> ValidatedNumber:
        meta = self._base_meta(field)
        if field.value is None or field.value == "":
            return ValidatedNumber(**meta, value=None, parse_status=ParseStatus.MISSING)

        number, coerced = parse_number(field.value)
        if number is None:
            issues.append(
                ValidationIssue(
                    code="NUMBER_PARSE_FAILED",
                    field=name,
                    severity=ValidationSeverity.WARNING,
                    message=f"Could not parse number for {name} from raw={field.value!r}.",
                )
            )
            return ValidatedNumber(**meta, value=None, parse_status=ParseStatus.PARSE_FAILED)

        if min_value is not None and number < min_value:
            issues.append(
                ValidationIssue(
                    code="NUMBER_OUT_OF_RANGE",
                    field=name,
                    severity=ValidationSeverity.ERROR,
                    message=f"{name}={number} is below minimum {min_value}.",
                )
            )
            return ValidatedNumber(
                **meta,
                value=number,
                parse_status=ParseStatus.OUT_OF_RANGE,
                coerced=coerced,
            )

        return ValidatedNumber(
            **meta,
            value=number,
            parse_status=ParseStatus.OK,
            coerced=coerced,
        )

    def _as_date(
        self,
        field: ExtractedField,
        name: str,
        issues: list[ValidationIssue],
    ) -> ValidatedDate:
        meta = self._base_meta(field)
        if field.value is None or field.value == "":
            return ValidatedDate(**meta, value=None, raw_text=None, parse_status=ParseStatus.MISSING)

        parsed, raw_text, coerced = parse_date(field.value)
        if parsed is None:
            issues.append(
                ValidationIssue(
                    code="DATE_PARSE_FAILED",
                    field=name,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Could not parse date for {name} from raw={field.value!r}. "
                        f"Kept raw text for display."
                    ),
                )
            )
            return ValidatedDate(
                **meta,
                value=None,
                raw_text=raw_text,
                parse_status=ParseStatus.PARSE_FAILED,
                coerced=coerced,
            )

        if is_implausible_future_date(parsed):
            issues.append(
                ValidationIssue(
                    code="DATE_IMPLAUSIBLE_FUTURE",
                    field=name,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"{name}={parsed.isoformat()} looks far in the future. "
                        "Please verify the printed bill date."
                    ),
                )
            )

        return ValidatedDate(
            **meta,
            value=parsed,
            raw_text=raw_text,
            parse_status=ParseStatus.OK,
            coerced=coerced,
        )

    def _as_bool(
        self,
        field: ExtractedField,
        name: str,
        issues: list[ValidationIssue],
    ) -> ValidatedBool:
        meta = self._base_meta(field)
        if field.value is None or field.value == "":
            return ValidatedBool(**meta, value=None, parse_status=ParseStatus.MISSING)

        value, coerced = parse_bool(field.value)
        if value is None:
            issues.append(
                ValidationIssue(
                    code="BOOL_PARSE_FAILED",
                    field=name,
                    severity=ValidationSeverity.INFO,
                    message=f"Could not parse boolean for {name} from raw={field.value!r}.",
                )
            )
            return ValidatedBool(**meta, value=None, parse_status=ParseStatus.PARSE_FAILED)

        return ValidatedBool(
            **meta,
            value=value,
            parse_status=ParseStatus.OK,
            coerced=coerced,
        )

    def _add_cross_date_notes(
        self,
        bill: CanonicalElectricityBill,
        issues: list[ValidationIssue],
    ) -> None:
        if (
            bill.bill_date.value
            and bill.due_date.value
            and bill.due_date.value < bill.bill_date.value
        ):
            issues.append(
                ValidationIssue(
                    code="DUE_DATE_BEFORE_BILL_DATE",
                    field="due_date",
                    severity=ValidationSeverity.WARNING,
                    message="Due date is before bill date — verify extraction.",
                )
            )

    def _add_bescom_hint(
        self,
        bill: CanonicalElectricityBill,
        issues: list[ValidationIssue],
    ) -> None:
        if bill.is_bescom_bill.value is False:
            issues.append(
                ValidationIssue(
                    code="NOT_BESCOM_BILL",
                    field="is_bescom_bill",
                    severity=ValidationSeverity.WARNING,
                    message=(
                        "Document may not be a BESCOM bill. "
                        "This app currently targets BESCOM domestic bills."
                    ),
                )
            )

    def _fields_needing_confirmation(
        self,
        bill: CanonicalElectricityBill,
        issues: list[ValidationIssue],
    ) -> list[str]:
        needed: list[str] = []

        for name in _CRITICAL_FIELDS:
            field_obj = getattr(bill, name)
            if field_obj.level in (ConfidenceLevel.LOW, ConfidenceLevel.MISSING):
                needed.append(name)
                continue
            if getattr(field_obj, "parse_status", ParseStatus.OK) in {
                ParseStatus.PARSE_FAILED,
                ParseStatus.OUT_OF_RANGE,
                ParseStatus.MISSING,
            }:
                needed.append(name)

        for issue in issues:
            if (
                issue.severity in (ValidationSeverity.ERROR, ValidationSeverity.WARNING)
                and issue.field
                and issue.field in REQUIRED_CONFIRMATION_FIELDS
                and issue.field not in needed
            ):
                # Only add field-scoped issues that imply user should look again
                if issue.code.endswith("_FAILED") or issue.code.endswith("_OUT_OF_RANGE"):
                    needed.append(issue.field)

        return needed
