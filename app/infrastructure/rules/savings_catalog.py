"""Load savings recommendation catalog YAML."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from app.domain.models.savings import RecommendationTemplate

DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parents[3]
    / "rules"
    / "karnataka"
    / "bescom"
    / "savings"
    / "catalog_v1.yaml"
)


class SavingsCatalog(BaseModel):
    catalog_version: str
    discom: str
    category: str
    verification_status: str
    notes: str = ""
    recommendations: list[RecommendationTemplate] = Field(default_factory=list)

    def get(self, recommendation_id: str) -> RecommendationTemplate | None:
        for item in self.recommendations:
            if item.id == recommendation_id:
                return item
        return None


def load_savings_catalog(path: Path | None = None) -> SavingsCatalog:
    catalog_path = path or DEFAULT_CATALOG_PATH
    with catalog_path.open(encoding="utf-8") as fh:
        payload = yaml.safe_load(fh)
    return SavingsCatalog.model_validate(payload)


@lru_cache
def get_default_savings_catalog() -> SavingsCatalog:
    return load_savings_catalog()
