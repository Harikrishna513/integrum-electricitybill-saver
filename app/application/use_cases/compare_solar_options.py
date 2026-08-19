from __future__ import annotations

from dataclasses import dataclass

from app.api.middleware import build_support_gate
from app.application.services.bill_to_solar_inputs import bill_prefill_from_stored
from app.application.services.solar_intelligence_report import build_solar_intelligence_report
from app.application.services.vnm_bill_comparison import build_vnm_comparison
from app.domain.engines.gnm import GNMAnalysisEngine
from app.domain.engines.solar import SolarAnalysisEngine
from app.domain.engines.vnm import VNMAnalysisEngine
from app.domain.models.category import CategoryClassificationResult
from app.domain.models.solar import SolarProfile
from app.domain.models.solar_options import (
    CompareSolarOptionsRequest,
    SolarOptionCard,
    SolarOptionsComparisonView,
    build_assumed_vnm_participants,
    build_gnm_installations,
    build_gnm_plant,
    build_vnm_participants,
    build_vnm_plant,
)
from app.domain.models.validated_bill import BillValidationResult
from app.domain.models.consistency import BillConsistencyResult
from app.domain.services.bill_confirmation_needs import (
    attested_fields_from_stored_validation,
    compute_needs_confirmation,
)
from app.infrastructure.persistence.repository import BillAnalysisRepository, StoredBillAnalysis


class SolarOptionsError(Exception):
    pass


@dataclass(frozen=True)
class CompareSolarOptionsResult:
    view: SolarOptionsComparisonView
    stored: StoredBillAnalysis


class CompareSolarOptionsUseCase:
    def __init__(
        self,
        repository: BillAnalysisRepository,
        *,
        solar_engine: SolarAnalysisEngine | None = None,
        vnm_engine: VNMAnalysisEngine | None = None,
        gnm_engine: GNMAnalysisEngine | None = None,
    ) -> None:
        self._repository = repository
        self._solar = solar_engine or SolarAnalysisEngine()
        self._vnm = vnm_engine or VNMAnalysisEngine()
        self._gnm = gnm_engine or GNMAnalysisEngine()

    def prefill(self, analysis_id: str) -> SolarOptionsComparisonView:
        stored = self._load_ready_analysis(analysis_id)
        prefill = bill_prefill_from_stored(stored)
        return SolarOptionsComparisonView(
            analysis_id=analysis_id,
            prefill=prefill,
            options=[],
            disclaimer=_DISCLAIMER,
            message=(
                "Your bill is confirmed. Compare your current BESCOM bill with "
                "Virtual Net Metering (VNM) via Integrum Energy — based only on "
                "your confirmed consumption and sanctioned load."
            ),
        )

    def compare(
        self,
        analysis_id: str,
        request: CompareSolarOptionsRequest,
    ) -> CompareSolarOptionsResult:
        stored = self._load_ready_analysis(analysis_id)
        prefill = bill_prefill_from_stored(stored)
        proposed_kwp = request.plant.proposed_kwp or prefill.suggested_plant_kwp or 5.0

        options: list[SolarOptionCard] = []

        if request.include_individual_solar:
            options.append(self._individual_solar(prefill, request, proposed_kwp))
        if request.include_vnm:
            options.append(
                self._run_vnm(prefill, request, proposed_kwp, request.vnm_participants)
            )
        if request.include_gnm:
            options.append(
                self._run_gnm(prefill, request, proposed_kwp, request.gnm_installations)
            )

        best = _pick_best_option(options)
        message = _comparison_message(options, best)

        vnm_comparison = None
        if request.include_vnm:
            vnm_comparison = build_vnm_comparison(
                stored,
                prefill,
                expected_vnm_solar_credit_kwh=request.expected_vnm_solar_credit_kwh,
            )

        options = _attach_intelligence_reports(
            options, prefill, vnm_comparison=vnm_comparison
        )

        view = SolarOptionsComparisonView(
            analysis_id=analysis_id,
            prefill=prefill,
            options=options,
            best_option=best,
            vnm_comparison=vnm_comparison,
            disclaimer=_DISCLAIMER,
            message=message,
        )
        return CompareSolarOptionsResult(view=view, stored=stored)

    def _load_ready_analysis(self, analysis_id: str) -> StoredBillAnalysis:
        stored = self._repository.get_by_id(analysis_id)
        if stored is None:
            raise LookupError(f"Analysis not found: {analysis_id}")

        validation = BillValidationResult.model_validate(stored.validation)
        classification = CategoryClassificationResult.model_validate(stored.classification)
        consistency = BillConsistencyResult.model_validate(stored.consistency)
        gate = build_support_gate(validation=validation, classification=classification)

        if not gate["supported_for_money_engines"]:
            raise SolarOptionsError(
                gate.get("user_guidance")
                or "This bill is outside supported Karnataka / BESCOM domestic scope."
            )

        attested = attested_fields_from_stored_validation(stored.validation)
        needs = compute_needs_confirmation(validation, consistency, attested=attested)
        if needs:
            raise SolarOptionsError(
                "Complete bill review and confirm all required fields before "
                f"comparing solar options. Still needed: {', '.join(needs)}."
            )
        return stored

    def _individual_solar(
        self,
        prefill,
        request: CompareSolarOptionsRequest,
        proposed_kwp: float,
    ) -> SolarOptionCard:
        profile = SolarProfile(
            monthly_units=prefill.monthly_units,
            as_of=prefill.as_of,
            sanctioned_load_kw=prefill.sanctioned_load_kw,
            roof_area_m2=request.plant.roof_area_m2,
            proposed_kwp=proposed_kwp,
            discom=prefill.discom,
            category=prefill.category,
            tariff_code=prefill.tariff_code,
        )
        result = self._solar.analyze(profile)
        saving = None
        if result.economics and result.economics.estimated_monthly_saving_inr is not None:
            saving = result.economics.estimated_monthly_saving_inr
        plant_kwp = result.sizing.analyzed_kwp if result.sizing else proposed_kwp
        return SolarOptionCard(
            option="individual_solar",
            title="Individual rooftop solar",
            status=result.status.value,
            monthly_saving_inr=saving,
            plant_kwp=plant_kwp,
            message=result.message,
            official_next_step="Apply via BESCOM SRTPV (DSPV) portal after installer quote.",
            missing_inputs=_missing_for_solar(result.status.value, request.plant.roof_area_m2),
            warnings=list(result.warnings),
            result=result.model_dump(mode="json"),
        )

    def _run_vnm(self, prefill, request, proposed_kwp, extras) -> SolarOptionCard:
        if extras:
            participants = build_vnm_participants(prefill, extras)
        else:
            participants = build_assumed_vnm_participants(prefill)
        plant = build_vnm_plant(request.plant, proposed_kwp)
        result = self._vnm.analyze(
            participants=participants,
            plant=plant,
            as_of=prefill.as_of,
            discom=prefill.discom,
            tariff_code=prefill.tariff_code,
        )
        return SolarOptionCard(
            option="vnm",
            title="Virtual Net Metering (VNM)",
            status=result.status.value,
            monthly_saving_inr=result.estimated_group_monthly_saving_inr,
            plant_kwp=result.proposed_kwp,
            message=result.message,
            official_next_step=result.official_next_step,
            missing_inputs=list(result.missing_inputs),
            warnings=list(result.warnings),
            result=result.model_dump(mode="json"),
        )

    def _run_gnm(self, prefill, request, proposed_kwp, extras) -> SolarOptionCard:
        installations = build_gnm_installations(prefill, extras)
        plant = build_gnm_plant(request.plant, proposed_kwp)
        result = self._gnm.analyze(
            installations=installations,
            plant=plant,
            as_of=prefill.as_of,
            discom=prefill.discom,
            tariff_code=prefill.tariff_code,
        )
        return SolarOptionCard(
            option="gnm",
            title="Group Net Metering (GNM)",
            status=result.status.value,
            monthly_saving_inr=result.estimated_group_monthly_saving_inr,
            plant_kwp=result.proposed_kwp,
            message=result.message,
            official_next_step=result.official_next_step,
            missing_inputs=list(result.missing_inputs),
            warnings=list(result.warnings),
            result=result.model_dump(mode="json"),
        )


_DISCLAIMER = (
    "Preliminary solar comparison only — not BESCOM approval, technical clearance, "
    "or an installer quote. Confirm against the latest KERC orders and BESCOM SRTPV "
    "portal before acting."
)


def _missing_for_solar(status: str, roof_area: float | None) -> list[str]:
    if status == "NO_ROOF" and (roof_area is None or roof_area <= 0):
        return ["roof_area_m2"]
    return []


def _pick_best_option(options: list[SolarOptionCard]) -> str | None:
    suitable = [
        o
        for o in options
        if o.status in {"ESTIMATED", "POTENTIALLY_SUITABLE"}
        and o.monthly_saving_inr is not None
    ]
    if not suitable:
        return None
    best = max(suitable, key=lambda o: o.monthly_saving_inr or 0)
    return best.option


def _attach_intelligence_reports(
    options: list[SolarOptionCard],
    prefill,
    *,
    vnm_comparison=None,
) -> list[SolarOptionCard]:
    updated: list[SolarOptionCard] = []
    for opt in options:
        report = build_solar_intelligence_report(
            opt,
            prefill,
            address=prefill.address,
            vnm_comparison=vnm_comparison if opt.option == "vnm" else None,
        )
        updated.append(opt.model_copy(update={"intelligence_report": report}))
    return updated


def _comparison_message(options: list[SolarOptionCard], best: str | None) -> str:
    if not options:
        return "No options were analyzed."
    if best is None:
        return (
            "Comparison complete. Some options need more information or are not "
            "suitable with current inputs — see details below."
        )
    titles = {o.option: o.title for o in options}
    return (
        f"Comparison complete. Based on preliminary estimates, "
        f"{titles.get(best, best)} shows the highest monthly saving among "
        f"options that passed pre-screen checks."
    )
