"""
Consumer category classification models — Milestone 5.

CONCEPT
  Decide DOMESTIC / COMMERCIAL / … from bill signals.
  Do NOT silently treat a commercial bill as residential.

SPRING ANALOGY
  Like a domain Policy / Classifier service returning a ClassificationResult DTO.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, computed_field


class ConsumerCategory(str, Enum):
    DOMESTIC = "DOMESTIC"
    COMMERCIAL = "COMMERCIAL"
    AGRICULTURE = "AGRICULTURE"
    EDUCATIONAL = "EDUCATIONAL"
    INDUSTRIAL = "INDUSTRIAL"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


class ClassificationStatus(str, Enum):
    CLASSIFIED = "CLASSIFIED"
    CATEGORY_CONFLICT = "CATEGORY_CONFLICT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CategorySignal(BaseModel):
    source: str
    evidence: str
    mapped_category: ConsumerCategory
    weight: float = Field(ge=0.0, le=1.0)


class CategoryClassificationResult(BaseModel):
    category: ConsumerCategory
    status: ClassificationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    signals: list[CategorySignal] = Field(default_factory=list)
    conflicting_categories: list[ConsumerCategory] = Field(default_factory=list)
    supported_by_app_v1: bool
    user_message: str
    rule_version: str
    verification_status: str
    requires_user_confirmation: bool = False

    @computed_field  # type: ignore[prop-decorator]
    @property
    def can_continue_domestic_pipeline(self) -> bool:
        """v1 pipeline may continue only for clear domestic classification."""
        return (
            self.supported_by_app_v1
            and self.status == ClassificationStatus.CLASSIFIED
            and self.category == ConsumerCategory.DOMESTIC
            and not self.requires_user_confirmation
        )
