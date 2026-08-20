"""Load Integrum Energy VNM provider assumptions."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

DEFAULT_PATH = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "karnataka"
    / "bescom"
    / "providers"
    / "integrum_vnm_v1.yaml"
)


class IntegrumVNMRule(BaseModel):
    rule_version: str
    provider_name: str
    provider_website: str | None = None
    provider_contact_url: str | None = None
    effective_from: date
    effective_to: date | None = None
    verification_status: str
    source: str
    source_notes: str = ""
    subscription: dict[str, Any] = Field(default_factory=dict)
    one_time: dict[str, Any] = Field(default_factory=dict)
    individual_scenario: dict[str, Any] = Field(default_factory=dict)
    seasonal_model: dict[str, Any] = Field(default_factory=dict)
    apartment_assumptions: dict[str, Any] = Field(default_factory=dict)
    generation: dict[str, Any] = Field(default_factory=dict)
    user_messages: dict[str, str] = Field(default_factory=dict)

    def applies_on(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of > self.effective_to:
            return False
        return True


def load_integrum_vnm_rule(path: Path | None = None) -> IntegrumVNMRule:
    with (path or DEFAULT_PATH).open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return IntegrumVNMRule.model_validate(payload)


@lru_cache
def get_default_integrum_vnm_rule() -> IntegrumVNMRule:
    return load_integrum_vnm_rule()
