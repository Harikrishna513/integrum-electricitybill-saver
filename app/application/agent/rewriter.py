"""
Contextual question rewriter — Milestone 19.

Goal:
  Convert follow-up questions into standalone queries so intent routing can
  extract missing parameters (units/load/as_of/etc.) from conversation context.

This is rule-based on purpose (no LLM calls inside rewriter).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.application.agent.memory import ConversationMemory


@dataclass
class RewriteResult:
    rewritten_question: str
    reason: str


def rewrite_question(
    *,
    question: str,
    memory: ConversationMemory,
    default_as_of: str | None = None,
) -> RewriteResult:
    q = question.strip()
    ql = q.lower()

    # Only rewrite follow-ups (short / indirect) where user likely relies on context.
    if len(ql) > 30 and not any(k in ql for k in ("why", "explain", "high", "increase", "decrease")):
        return RewriteResult(rewritten_question=q, reason="No follow-up pattern detected.")

    # Find last tariff/bill tool result to extract known inputs.
    last = memory.last_tool_call("calculate_tariff")
    if not last:
        return RewriteResult(rewritten_question=q, reason="No prior calculate_tariff context.")

    # Stored tool_result item shape (from AgentRunner):
    #   {"tool": <name>, "args": {...}, "result": <parsed tool JSON>}
    tool_call_args = last.get("args") or {}

    # Extract known inputs if present.
    units = _maybe_float(tool_call_args.get("units"))
    load = _maybe_float(tool_call_args.get("sanctioned_load_kw"))
    as_of = tool_call_args.get("as_of")
    if not as_of:
        as_of = default_as_of

    # If we cannot find any parameters, just return original.
    if units is None and load is None and not as_of:
        return RewriteResult(rewritten_question=q, reason="Context exists but missing bill inputs.")

    parts: list[str] = [q]
    if units is not None:
        parts.append(f"for {units:g} units")
    if load is not None:
        parts.append(f"and {load:g} kW load")
    if as_of:
        parts.append(f"on {as_of}")

    rewritten = " ".join(parts)
    return RewriteResult(rewritten_question=rewritten, reason="Injected last known bill inputs into follow-up.")


def _maybe_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None

