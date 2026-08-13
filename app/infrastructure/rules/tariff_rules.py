"""
Tariff rule repository — load versioned YAML, select by date.

CONCEPT
  rule_repository.get_rule(discom, category, as_of)
  Never: if year == 2026: ...
"""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

import yaml

from app.domain.models.tariff import TariffRule

DEFAULT_TARIFF_DIR = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "karnataka"
    / "bescom"
    / "tariff"
)


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value))


def load_tariff_rule_file(path: Path) -> TariffRule:
    with path.open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    payload["effective_from"] = _parse_date(payload["effective_from"])
    payload["effective_to"] = _parse_date(payload.get("effective_to"))
    return TariffRule.model_validate(payload)


class TariffRuleRepository:
    def __init__(self, rules_dir: Path | None = None) -> None:
        self._rules_dir = rules_dir or DEFAULT_TARIFF_DIR

    def list_rules(self) -> list[TariffRule]:
        rules: list[TariffRule] = []
        if not self._rules_dir.exists():
            return rules
        for path in sorted(self._rules_dir.glob("*.yaml")):
            rules.append(load_tariff_rule_file(path))
        return rules

    def get_rule(
        self,
        *,
        discom: str,
        category: str,
        as_of: date,
        tariff_code: str | None = None,
    ) -> TariffRule | None:
        discom_u = discom.upper()
        category_u = category.upper()
        code_u = tariff_code.upper().replace(" ", "") if tariff_code else None

        candidates: list[TariffRule] = []
        for rule in self.list_rules():
            if rule.discom.upper() != discom_u:
                continue
            if rule.category.upper() != category_u:
                continue
            if not rule.applies_on(as_of):
                continue
            if code_u and not self._code_matches(code_u, rule.tariff_codes):
                continue
            candidates.append(rule)

        if not candidates:
            return None

        # Prefer the most recently effective rule among matches
        candidates.sort(key=lambda r: r.effective_from, reverse=True)
        return candidates[0]

    @staticmethod
    def _code_matches(code_u: str, rule_codes: list[str]) -> bool:
        def norm(value: str) -> str:
            return value.upper().replace(" ", "").replace("-", "")

        target = norm(code_u)
        return any(norm(c) == target for c in rule_codes)


@lru_cache
def get_default_tariff_repository() -> TariffRuleRepository:
    return TariffRuleRepository()
