from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Callable

from app.application.services.rag_service import OfficialSourceRetriever
from app.domain.engines.gnm import GNMAnalysisEngine
from app.domain.engines.tariff import TariffEngine
from app.domain.engines.vnm import VNMAnalysisEngine
from app.domain.models.gnm import GNMInstallationInput, GNMPlantInput, GNMStatus
from app.domain.models.vnm import VNMParticipantInput, VNMPlantInput, VNMStatus


@dataclass
class EvalCase:
    case_id: str
    category: str  # tariff | vnm | gnm | rag
    description: str
    check: Callable[[], tuple[bool, str]]


@dataclass
class EvalResult:
    case_id: str
    category: str
    passed: bool
    detail: str


@dataclass
class EvalReport:
    total: int
    passed: int
    failed: int
    results: list[EvalResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return 0.0 if self.total == 0 else round(self.passed / self.total, 4)


def _tariff_cases() -> list[EvalCase]:
    def check_120() -> tuple[bool, str]:
        r = TariffEngine().calculate(
            category="DOMESTIC",
            as_of=date(2025, 6, 15),
            units=120,
            sanctioned_load_kw=2,
            tariff_code="LT-1",
        )
        ok = r.estimated_total == 1035.55
        return ok, f"estimated_total={r.estimated_total} rule={r.rule_version}"

    return [
        EvalCase(
            case_id="tariff_lt1_120_units_2025",
            category="tariff",
            description="Bootstrap LT-1 bill for 120 units matches golden total",
            check=check_120,
        )
    ]


def _vnm_cases() -> list[EvalCase]:
    def check_min_plant() -> tuple[bool, str]:
        result = VNMAnalysisEngine().analyze(
            participants=[
                VNMParticipantInput(
                    connection_id="A",
                    sanctioned_load_kw=3,
                    monthly_units=200,
                    procurement_share_percent=50,
                ),
                VNMParticipantInput(
                    connection_id="B",
                    sanctioned_load_kw=3,
                    monthly_units=200,
                    procurement_share_percent=50,
                ),
            ],
            plant=VNMPlantInput(proposed_kwp=3.0, same_discom_area=True),
            as_of=date(2025, 8, 1),
        )
        ok = result.status == VNMStatus.POTENTIALLY_UNSUITABLE
        return ok, f"status={result.status.value}"

    def check_suitable() -> tuple[bool, str]:
        result = VNMAnalysisEngine().analyze(
            participants=[
                VNMParticipantInput(
                    connection_id="A",
                    sanctioned_load_kw=4,
                    monthly_units=200,
                    procurement_share_percent=50,
                ),
                VNMParticipantInput(
                    connection_id="B",
                    sanctioned_load_kw=4,
                    monthly_units=200,
                    procurement_share_percent=50,
                ),
            ],
            plant=VNMPlantInput(
                proposed_kwp=6.0,
                same_discom_area=True,
                estimated_monthly_generation_kwh=600,
                grid_topology_hint="same_dt",
            ),
            as_of=date(2025, 8, 1),
        )
        ok = result.status == VNMStatus.POTENTIALLY_SUITABLE
        return ok, f"status={result.status.value} msg={result.message[:80]}"

    return [
        EvalCase(
            case_id="vnm_below_min_5kw",
            category="vnm",
            description="Plant < 5 kWp must be POTENTIALLY_UNSUITABLE",
            check=check_min_plant,
        ),
        EvalCase(
            case_id="vnm_apartment_pre_screen_ok",
            category="vnm",
            description="Valid 2-flat VNM pre-screen passes",
            check=check_suitable,
        ),
    ]


def _gnm_cases() -> list[EvalCase]:
    def check_lapse() -> tuple[bool, str]:
        result = GNMAnalysisEngine().analyze(
            installations=[
                GNMInstallationInput(
                    connection_id="HOST",
                    sanctioned_load_kw=5,
                    monthly_units=50,
                    priority=1,
                    is_host=True,
                ),
                GNMInstallationInput(
                    connection_id="RR2",
                    sanctioned_load_kw=3,
                    monthly_units=200,
                    priority=2,
                    is_host=False,
                ),
            ],
            plant=GNMPlantInput(
                proposed_kwp=6,
                same_discom_area=True,
                same_consumer_name=True,
                estimated_monthly_generation_kwh=1000,
                grid_topology_hint="same_dt",
            ),
            as_of=date(2025, 8, 1),
        )
        ok = (
            result.status == GNMStatus.POTENTIALLY_SUITABLE
            and result.lapsed_kwh == 150.0
        )
        return ok, f"status={result.status.value} lapsed={result.lapsed_kwh}"

    return [
        EvalCase(
            case_id="gnm_host_20pct_lapse",
            category="gnm",
            description="Unused host 20% reserve lapses (150 kWh on 1000 gen)",
            check=check_lapse,
        )
    ]


def _rag_cases() -> list[EvalCase]:
    def check_vnm_docs() -> tuple[bool, str]:
        r = OfficialSourceRetriever().search("VNM minimum plant size", top_k=3)
        ok = r["hit_count"] >= 1
        return ok, f"hits={r['hit_count']}"

    def check_75pct() -> tuple[bool, str]:
        r = OfficialSourceRetriever().search(
            "surplus energy 75% of generic tariff VNM", top_k=5
        )
        blob = " ".join(h["text"] for h in r["hits"]).lower()
        ok = r["hit_count"] >= 1 and ("75" in blob or "generic" in blob)
        return ok, f"hits={r['hit_count']} has_75_or_generic={ok}"

    return [
        EvalCase(
            case_id="rag_vnm_min_size",
            category="rag",
            description="data/Docs retrieves VNM min plant wording",
            check=check_vnm_docs,
        ),
        EvalCase(
            case_id="rag_surplus_75pct",
            category="rag",
            description="data/Docs retrieves 75% generic surplus concept",
            check=check_75pct,
        ),
    ]


def all_eval_cases() -> list[EvalCase]:
    return _tariff_cases() + _vnm_cases() + _gnm_cases() + _rag_cases()


def run_evaluation() -> EvalReport:
    results: list[EvalResult] = []
    for case in all_eval_cases():
        try:
            passed, detail = case.check()
        except Exception as exc:  # noqa: BLE001
            passed, detail = False, f"ERROR: {exc}"
        results.append(
            EvalResult(
                case_id=case.case_id,
                category=case.category,
                passed=passed,
                detail=detail,
            )
        )
    passed_n = sum(1 for r in results if r.passed)
    return EvalReport(
        total=len(results),
        passed=passed_n,
        failed=len(results) - passed_n,
        results=results,
    )


def report_as_dict(report: EvalReport) -> dict[str, Any]:
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "pass_rate": report.pass_rate,
        "results": [asdict(r) for r in report.results],
    }


if __name__ == "__main__":
    rep = run_evaluation()
    print(report_as_dict(rep))
    raise SystemExit(0 if rep.failed == 0 else 1)
