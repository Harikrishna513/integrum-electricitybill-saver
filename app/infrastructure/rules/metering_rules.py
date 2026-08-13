"""Load versioned metering arrangement / settlement assumptions."""

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
    / "metering_arrangements_v1.yaml"
)


class MeteringArrangementsRule(BaseModel):
    rule_version: str
    discom: str
    effective_from: date
    effective_to: date | None = None
    verification_status: str
    source: str
    source_notes: str = ""
    concepts: dict[str, dict[str, Any]] = Field(default_factory=dict)
    settlement: dict[str, Any] = Field(default_factory=dict)
    export_tariffs_inr_per_kwh: dict[str, Any] = Field(default_factory=dict)
    user_messages: dict[str, str] = Field(default_factory=dict)

    def applies_on(self, as_of: date) -> bool:
        if as_of < self.effective_from:
            return False
        if self.effective_to is not None and as_of > self.effective_to:
            return False
        return True


def load_metering_arrangements_rule(path: Path | None = None) -> MeteringArrangementsRule:
    with (path or DEFAULT_PATH).open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return MeteringArrangementsRule.model_validate(payload)


@lru_cache
def get_default_metering_arrangements_rule() -> MeteringArrangementsRule:
    return load_metering_arrangements_rule()
