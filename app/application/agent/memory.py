"""
In-memory conversation memory — Milestone 19.

We keep it intentionally simple:
- rule-based contextual rewriting (no external calls)
- store last few agent turns per `session_id`

Later milestones (20+) can replace this with DB-backed memory + RAG.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


TurnSource = Literal["rules", "llm"]


@dataclass
class StoredTurn:
    source: TurnSource
    question: str
    rewritten_question: str | None
    answer: str
    tools_called: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)


class ConversationMemory:
    def __init__(self, *, max_turns: int = 12) -> None:
        self._max_turns = max_turns
        self._turns: list[StoredTurn] = []

    def add(self, turn: StoredTurn) -> None:
        self._turns.append(turn)
        if len(self._turns) > self._max_turns:
            self._turns = self._turns[-self._max_turns :]

    @property
    def turns(self) -> list[StoredTurn]:
        return list(self._turns)

    def last_tool_call(self, tool_name: str) -> dict[str, Any] | None:
        for t in reversed(self._turns):
            for item in t.tool_results:
                if item.get("tool") == tool_name:
                    return item
        return None

