"""Load appliance default assumptions YAML."""

from __future__ import annotations

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
    / "appliances"
    / "defaults_v1.yaml"
)


class ApplianceDefaultsCatalog(BaseModel):
    catalog_version: str
    verification_status: str
    notes: str = ""
    defaults: dict[str, Any] = Field(default_factory=dict)
    appliances: dict[str, dict[str, Any]] = Field(default_factory=dict)


def load_appliance_defaults(path: Path | None = None) -> ApplianceDefaultsCatalog:
    with (path or DEFAULT_PATH).open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return ApplianceDefaultsCatalog.model_validate(payload)


@lru_cache
def get_default_appliance_defaults() -> ApplianceDefaultsCatalog:
    return load_appliance_defaults()
