"""
Load versioned Gruha Jyothi scheme rules from YAML.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LowBaselineUplift(BaseModel):
    enabled: bool = False
    baseline_below_units: float = 90
    flat_extra_units: float = 10


class EntitlementConfig(BaseModel):
    model: str
    percent_uplift: float = 10.0
    hard_cap_units: float = 200
    low_baseline_flat_uplift: LowBaselineUplift = Field(
        default_factory=LowBaselineUplift
    )


class BaselineConfig(BaseModel):
    type: str
    financial_year: str
    description: str = ""


class GruhaJyothiRule(BaseModel):
    rule_version: str
    state: str
    scheme_name: str
    effective_from: date
    effective_to: date | None = None
    verification_status: str
    source: str
    source_notes: str = ""
    eligible_categories: list[str]
    baseline: BaselineConfig
    entitlement: EntitlementConfig
    required_inputs_for_entitlement: list[str] = Field(default_factory=list)
    optional_inputs: list[str] = Field(default_factory=list)
    user_messages: dict[str, str] = Field(default_factory=dict)

    def applies_on(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of > self.effective_to:
            return False
        return True


DEFAULT_RULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "karnataka"
    / "bescom"
    / "schemes"
    / "gruha_jyothi_v1.yaml"
)


def load_gruha_jyothi_rule(path: Path | None = None) -> GruhaJyothiRule:
    rules_path = path or DEFAULT_RULE_PATH
    with rules_path.open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    payload["effective_from"] = date.fromisoformat(str(payload["effective_from"]))
    if payload.get("effective_to"):
        payload["effective_to"] = date.fromisoformat(str(payload["effective_to"]))
    return GruhaJyothiRule.model_validate(payload)


@lru_cache
def get_default_gruha_jyothi_rule() -> GruhaJyothiRule:
    return load_gruha_jyothi_rule()
