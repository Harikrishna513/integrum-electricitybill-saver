from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any


_CURRENCY_JUNK = re.compile(
    r"(?:rs\.?|inr|₹|\bu\b|\bunits?\b|\bkwh\b|\bkw\b)",
    re.IGNORECASE,
)
_MULTI_SPACE = re.compile(r"\s+")


def normalize_text(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-"}:
        return None
    return _MULTI_SPACE.sub(" ", text)


def normalize_tariff_code(raw: Any) -> str | None:
    text = normalize_text(raw)
    if text is None:
        return None
    upper = text.upper().replace(" ", "")
    # LT1 / LT-1 / LT–1 → LT-1
    upper = upper.replace("–", "-").replace("—", "-")
    match = re.fullmatch(r"LT-?(\d+[A-Z]?)", upper)
    if match:
        return f"LT-{match.group(1)}"
    return text.upper()


def parse_number(raw: Any) -> tuple[float | None, bool]:
    """
    Returns (number_or_none, coerced_flag).

    coerced=True when we transformed a non-plain-number string.
    """
    if raw is None or raw == "":
        return None, False

    if isinstance(raw, bool):
        return None, False

    if isinstance(raw, (int, float)):
        return float(raw), False

    text = normalize_text(raw)
    if text is None:
        return None, False

    original = text
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]

    text = text.replace(",", "")
    text = _CURRENCY_JUNK.sub("", text)
    text = text.replace(" ", "")

    # Keep leading minus
    if text.startswith("-"):
        negative = True
        text = text[1:]
    elif text.startswith("+"):
        text = text[1:]

    # Extract first number-like token
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None, True

    value = float(match.group(0))
    if negative:
        value = -value

    coerced = str(original) != str(value) and str(original) != str(int(value))
    return value, coerced or original != match.group(0)


def parse_bool(raw: Any) -> tuple[bool | None, bool]:
    if raw is None or raw == "":
        return None, False
    if isinstance(raw, bool):
        return raw, False
    if isinstance(raw, (int, float)) and raw in (0, 1):
        return bool(raw), True

    text = normalize_text(raw)
    if text is None:
        return None, False

    lowered = text.lower()
    if lowered in {"true", "yes", "y", "1"}:
        return True, lowered not in {"true"}
    if lowered in {"false", "no", "n", "0"}:
        return False, lowered not in {"false"}
    return None, True


_DATE_FORMATS = (
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y-%m-%d",
    "%d/%m/%y",
    "%d-%m-%y",
    "%d %b %Y",
    "%d %B %Y",
    "%b %d, %Y",
    "%d-%b-%Y",
    "%d/%b/%Y",
)


def parse_date(raw: Any) -> tuple[date | None, str | None, bool]:
    """
    Returns (date_or_none, raw_text, coerced).
    """
    text = normalize_text(raw)
    if text is None:
        return None, None, False

    # Already ISO date
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text), text, False
        except ValueError:
            return None, text, True

    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date(), text, True
        except ValueError:
            continue

    return None, text, True


def is_implausible_future_date(value: date, *, today: date | None = None) -> bool:
    """Flag dates more than 60 days in the future (possible OCR year error)."""
    today = today or datetime.now(timezone.utc).date()
    return value > today and (value - today).days > 60
