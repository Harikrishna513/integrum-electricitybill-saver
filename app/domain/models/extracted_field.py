"""
Extracted field with confidence — reusable building block.

CONCEPT
  Every important bill value is not just a number/string.
  It is: value + how sure we are + where it came from.

WHY
  OCR/vision can misread "286" as "288". Showing confidence lets the UI ask
  the user to confirm instead of silently trusting a wrong unit count.

SPRING ANALOGY
  Like a ValueObject wrapping a field — not a raw String/Double on the entity.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, computed_field


class ConfidenceLevel(str, Enum):
    HIGH = "HIGH"  # >= 0.85
    MEDIUM = "MEDIUM"  # >= 0.60
    LOW = "LOW"  # > 0 and < 0.60
    MISSING = "MISSING"  # value is null / not found


class ExtractedField(BaseModel):
    """
    One extracted bill field.

    value may be string or number depending on the parent field's meaning.
    Using a shared shape keeps the Gemini structured-output schema stable.
    """

    value: str | float | int | None = Field(
        default=None,
        description="Extracted value from the bill, or null if not found / unreadable.",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Model confidence from 0.0 to 1.0 that the value is correct.",
    )
    source: Literal["bill", "inferred", "unknown", "user"] = Field(
        default="bill",
        description=(
            "bill = explicitly visible on the document; "
            "inferred = deduced (avoid unless necessary); "
            "unknown = not determined; "
            "user = confirmed or corrected by the consumer (Milestone 24)."
        ),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def level(self) -> ConfidenceLevel:
        if self.value is None or self.value == "":
            return ConfidenceLevel.MISSING
        if self.confidence >= 0.85:
            return ConfidenceLevel.HIGH
        if self.confidence >= 0.60:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.LOW
