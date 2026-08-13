"""
ConsumerCategoryClassifier — Milestone 5.

CONCEPT
  Combine multiple bill signals (tariff code, category text) into one category
  decision. If signals conflict → CATEGORY_CONFLICT (do not guess).

WHY DETERMINISTIC
  Category gates the rest of the app (v1 = DOMESTIC only).
  An LLM guess here could silently analyze a commercial bill as residential.

BESCOM EXAMPLE
  tariff_code=LT-1 + text="Domestic" → DOMESTIC, high confidence
  tariff_code=LT-3 + text="Residential" → CATEGORY_CONFLICT
  tariff_code=LT-3 + text="Commercial" → COMMERCIAL, not supported in v1
"""

from __future__ import annotations

import re

from app.domain.models.category import (
    CategoryClassificationResult,
    CategorySignal,
    ClassificationStatus,
    ConsumerCategory,
)
from app.domain.models.validated_bill import CanonicalElectricityBill
from app.infrastructure.rules.category_rules import (
    CategorySignalRules,
    get_default_category_signal_rules,
)


class ConsumerCategoryClassifier:
    def __init__(self, rules: CategorySignalRules | None = None) -> None:
        self._rules = rules or get_default_category_signal_rules()

    def classify(self, bill: CanonicalElectricityBill) -> CategoryClassificationResult:
        signals: list[CategorySignal] = []

        tariff = bill.tariff_code.value
        if tariff:
            mapped = self._map_tariff_code(tariff)
            if mapped is not None:
                signals.append(
                    CategorySignal(
                        source="tariff_code",
                        evidence=tariff,
                        mapped_category=mapped,
                        weight=self._rules.signal_weights.get("tariff_code", 0.6),
                    )
                )

        category_text = bill.consumer_category.value
        if category_text:
            mapped = self._map_category_text(category_text)
            if mapped is not None:
                signals.append(
                    CategorySignal(
                        source="consumer_category_text",
                        evidence=category_text,
                        mapped_category=mapped,
                        weight=self._rules.signal_weights.get(
                            "consumer_category_text", 0.4
                        ),
                    )
                )

        if not signals:
            return CategoryClassificationResult(
                category=ConsumerCategory.UNKNOWN,
                status=ClassificationStatus.INSUFFICIENT_EVIDENCE,
                confidence=0.0,
                signals=[],
                conflicting_categories=[],
                supported_by_app_v1=False,
                requires_user_confirmation=True,
                rule_version=self._rules.rule_version,
                verification_status=self._rules.verification_status,
                user_message=(
                    "Could not determine consumer category from the bill. "
                    "Please confirm whether this is a Domestic / Residential BESCOM bill."
                ),
            )

        categories = {s.mapped_category for s in signals}
        if len(categories) > 1:
            conflicting = sorted(categories, key=lambda c: c.value)
            return CategoryClassificationResult(
                category=ConsumerCategory.UNKNOWN,
                status=ClassificationStatus.CATEGORY_CONFLICT,
                confidence=0.0,
                signals=signals,
                conflicting_categories=conflicting,
                supported_by_app_v1=False,
                requires_user_confirmation=True,
                rule_version=self._rules.rule_version,
                verification_status=self._rules.verification_status,
                user_message=(
                    "Category signals conflict on this bill "
                    f"({', '.join(c.value for c in conflicting)}). "
                    "Please confirm the correct category. "
                    "This version will not guess."
                ),
            )

        category = next(iter(categories))
        confidence = self._confidence(signals, bill)
        supported = (
            category.value in self._rules.supported_categories_v1
            and confidence >= 0.6
        )
        needs_confirm = confidence < 0.85

        if supported and not needs_confirm:
            user_message = (
                f"Detected category: {category.value} "
                f"(confidence {confidence:.0%}). "
                "Supported by this app version."
            )
        elif supported and needs_confirm:
            user_message = (
                f"Possible category: {category.value} "
                f"(confidence {confidence:.0%}). "
                "Please confirm Domestic / Residential before continuing."
            )
        else:
            user_message = (
                f"Detected category: {category.value} "
                f"(confidence {confidence:.0%}). "
                "This version currently supports Domestic / Residential bills only. "
                "Please upload a residential BESCOM bill."
            )

        return CategoryClassificationResult(
            category=category,
            status=ClassificationStatus.CLASSIFIED,
            confidence=confidence,
            signals=signals,
            conflicting_categories=[],
            supported_by_app_v1=supported,
            requires_user_confirmation=needs_confirm or not supported,
            rule_version=self._rules.rule_version,
            verification_status=self._rules.verification_status,
            user_message=user_message,
        )

    def _map_tariff_code(self, tariff_code: str) -> ConsumerCategory | None:
        code = tariff_code.strip().upper()
        for category_name, patterns in self._rules.tariff_code_patterns.items():
            for pattern in patterns:
                if re.search(pattern, code, flags=re.IGNORECASE):
                    return ConsumerCategory(category_name)
        return ConsumerCategory.OTHER

    def _map_category_text(self, text: str) -> ConsumerCategory | None:
        lowered = text.strip().lower()
        hits: list[ConsumerCategory] = []
        for category_name, keywords in self._rules.text_keywords.items():
            for keyword in keywords:
                if keyword.lower() in lowered:
                    hits.append(ConsumerCategory(category_name))
                    break
        unique = set(hits)
        if len(unique) == 1:
            return next(iter(unique))
        if len(unique) > 1:
            # Conflicting keywords inside one text field — treat as unresolved here;
            # outer layer may still conflict with tariff.
            return None
        return None

    def _confidence(
        self,
        signals: list[CategorySignal],
        bill: CanonicalElectricityBill,
    ) -> float:
        if not signals:
            return 0.0

        weighted = 0.0
        total_weight = 0.0
        for signal in signals:
            field_confidence = 1.0
            if signal.source == "tariff_code":
                field_confidence = bill.tariff_code.confidence or 0.0
            elif signal.source == "consumer_category_text":
                field_confidence = bill.consumer_category.confidence or 0.0
            weighted += signal.weight * field_confidence
            total_weight += signal.weight

        base = weighted / total_weight if total_weight else 0.0
        # Agreement bonus when multiple independent signals match
        if len(signals) >= 2:
            base = min(1.0, base + 0.05)
        return round(base, 4)
