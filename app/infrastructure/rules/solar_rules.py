"""Load versioned rooftop solar planning assumptions."""

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
    / "solar"
    / "rooftop_domestic_v1.yaml"
)


class SolarRooftopRule(BaseModel):
    rule_version: str
    discom: str
    category: str
    effective_from: date
    effective_to: date | None = None
    verification_status: str
    source: str
    source_notes: str = ""
    generation: dict[str, Any] = Field(default_factory=dict)
    sizing: dict[str, Any] = Field(default_factory=dict)
    economics: dict[str, Any] = Field(default_factory=dict)
    cfa_pm_surya_ghar: dict[str, Any] = Field(default_factory=dict)
    user_messages: dict[str, str] = Field(default_factory=dict)

    def applies_on(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of > self.effective_to:
            return False
        return True


def load_solar_rooftop_rule(path: Path | None = None) -> SolarRooftopRule:
    with (path or DEFAULT_PATH).open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return SolarRooftopRule.model_validate(payload)


@lru_cache
def get_default_solar_rooftop_rule() -> SolarRooftopRule:
    return load_solar_rooftop_rule()
