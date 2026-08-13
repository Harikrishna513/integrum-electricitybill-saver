"""
Load versioned category-signal rules from YAML.

CONCEPT
  Category mappings live in rules/ files, not hardcoded if-year blocks.

WHY
  When KERC/BESCOM schedules change, add a new versioned file.
  verification_status reminds us mappings may still need official confirmation.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class CategorySignalRules(BaseModel):
    rule_version: str
    state: str
    discom: str
    effective_from: str
    effective_to: str | None = None
    verification_status: str
    source: str
    notes: str = ""
    supported_categories_v1: list[str] = Field(default_factory=list)
    text_keywords: dict[str, list[str]] = Field(default_factory=dict)
    tariff_code_patterns: dict[str, list[str]] = Field(default_factory=dict)
    signal_weights: dict[str, float] = Field(default_factory=dict)


DEFAULT_RULES_PATH = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "karnataka"
    / "bescom"
    / "categories"
    / "consumer_category_signals_v1.yaml"
)


def load_category_signal_rules(path: Path | None = None) -> CategorySignalRules:
    rules_path = path or DEFAULT_RULES_PATH
    with rules_path.open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return CategorySignalRules.model_validate(payload)


@lru_cache
def get_default_category_signal_rules() -> CategorySignalRules:
    return load_category_signal_rules()
