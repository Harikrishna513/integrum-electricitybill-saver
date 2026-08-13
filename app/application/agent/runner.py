"""
Agent runner — Milestone 18.

CONCEPT
  mode=rules  → IntentRouter picks a tool (no Gemini) — great for tests/offline
  mode=llm    → Gemini bind_tools loop chooses tools, then explains tool JSON

Never let the LLM be the source of truth for ₹ / eligibility / approval.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.application.agent.intents import route_question
from app.application.agent.memory import ConversationMemory, StoredTurn
from app.application.agent.rewriter import rewrite_question
from app.application.agent.tools import build_agent_tools, get_tool_map
from app.infrastructure.llm.gemini_client import build_chat_model

AgentMode = Literal["rules", "llm"]

SYSTEM_PROMPT = """You are the BESCOM Bill Saver AI assistant for Karnataka residential consumers.

HARD RULES:
1. You MUST call tools for any money, tariff, savings, solar economics, Gruha Jyothi,
   metering settlement, VNM, or GNM answer. Never invent ₹ amounts or eligibility approvals.
2. For latest policy / SOP / KERC regulation questions, call search_official_docs
   (local data/Docs corpus). Do not invent current VNM/GNM rules from memory alone.
3. Never say the user is "approved" for Gruha Jyothi, VNM, GNM, CFA, or BESCOM sanction.
4. If a tool result has verification_status REQUIRES_VERIFICATION / UNVERIFIED, say so clearly.
5. Prefer Estimated / Approximate / Based on assumptions language for estimates.
6. Explain tool results in plain English for a Bengaluru home consumer.
7. If required inputs are missing, ask for them or call list_agent_tools.
"""


@dataclass
class AgentTurnResult:
    mode: AgentMode
    question: str
    rewritten_question: str | None
    answer: str
    tools_called: list[str] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    routed_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


class AgentRunner:
    def __init__(self, *, max_llm_iters: int = 4) -> None:
        self._max_llm_iters = max_llm_iters
        self._tools = build_agent_tools()
        self._tool_map = get_tool_map()

    def ask(
        self,
        question: str,
        *,
        mode: AgentMode = "rules",
        session_id: str = "default",
    ) -> AgentTurnResult:
        # Milestone 19: contextual rewriting + simple session memory.
        memory = _SESSION_STORE.setdefault(session_id, ConversationMemory())
        rewritten = rewrite_question(
            question=question,
            memory=memory,
            default_as_of=date.today().isoformat(),
        )
        rewritten_question = rewritten.rewritten_question

        if mode == "rules":
            result = self._ask_rules(rewritten_question)
        else:
            result = self._ask_llm(rewritten_question)

        result.rewritten_question = rewritten_question

        memory.add(
            StoredTurn(
                source=result.mode,
                question=question,
                rewritten_question=rewritten_question,
                answer=result.answer,
                tools_called=result.tools_called,
                tool_results=result.tool_results,
            )
        )

        return result

    def _ask_rules(self, question: str) -> AgentTurnResult:
        routed = route_question(question)
        tool = self._tool_map[routed.tool_name]
        raw = tool.invoke(routed.args)
        parsed = _safe_json(raw)
        answer = _format_rules_answer(routed.tool_name, parsed)
        return AgentTurnResult(
            mode="rules",
            question=question,
            rewritten_question=None,
            answer=answer,
            tools_called=[routed.tool_name],
            tool_results=[{"tool": routed.tool_name, "args": routed.args, "result": parsed}],
            routed_reason=routed.reason,
            warnings=[
                "Answer produced in rules mode (deterministic tool routing — no Gemini).",
                "Numbers come from engines inside the tool, not from the router.",
            ],
        )

    def _ask_llm(self, question: str) -> AgentTurnResult:
        model = build_chat_model().bind_tools(self._tools)
        messages: list[Any] = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=question),
        ]
        tools_called: list[str] = []
        tool_results: list[dict[str, Any]] = []
        warnings = [
            "LLM mode: Gemini selects tools; engines inside tools compute money/facts."
        ]

        for _ in range(self._max_llm_iters):
            ai: AIMessage = model.invoke(messages)  # type: ignore[assignment]
            messages.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                text = _message_text(ai)
                return AgentTurnResult(
                    mode="llm",
                    question=question,
                    rewritten_question=None,
                    answer=text or "I could not produce an answer.",
                    tools_called=tools_called,
                    tool_results=tool_results,
                    warnings=warnings,
                )

            for call in tool_calls:
                name = call["name"]
                args = call.get("args") or {}
                call_id = call.get("id") or name
                tools_called.append(name)
                tool = self._tool_map.get(name)
                if tool is None:
                    payload = json.dumps({"error": f"Unknown tool: {name}"})
                else:
                    payload = tool.invoke(args)
                parsed = _safe_json(payload)
                tool_results.append({"tool": name, "args": args, "result": parsed})
                messages.append(
                    ToolMessage(content=str(payload), tool_call_id=call_id, name=name)
                )

        # Final pass without forcing tools
        final: AIMessage = model.invoke(messages)  # type: ignore[assignment]
        return AgentTurnResult(
            mode="llm",
            question=question,
            rewritten_question=None,
            answer=_message_text(final) or "Reached tool-call iteration limit.",
            tools_called=tools_called,
            tool_results=tool_results,
            warnings=warnings + ["Stopped after max tool-calling iterations."],
        )


_SESSION_STORE: dict[str, ConversationMemory] = {}


def _message_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(str(block["text"]))
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _safe_json(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except json.JSONDecodeError:
        return {"raw": str(raw)}


def _format_rules_answer(tool_name: str, parsed: Any) -> str:
    """Plain-English summary from tool JSON for rules mode."""
    if not isinstance(parsed, dict):
        return f"Tool `{tool_name}` returned: {parsed}"

    result = parsed.get("result", parsed)

    if tool_name == "calculate_tariff" and isinstance(result, dict):
        return (
            f"Estimated bill ≈ ₹{result.get('estimated_total')} "
            f"(rule {result.get('rule_version')}, "
            f"verification={result.get('verification_status')}). "
            f"Status: {result.get('status')}. "
            "This is an engine calculation — not an official BESCOM recomputation."
        )

    if tool_name == "estimate_savings" and isinstance(result, dict):
        return (
            f"Estimated saving ≈ ₹{result.get('estimated_monthly_saving')}/month "
            f"(₹{result.get('estimated_annual_saving')}/year) under stated kWh assumptions. "
            f"Tariff rule: {result.get('tariff_rule_version')}."
        )

    if tool_name == "check_gruha_jyothi" and isinstance(result, dict):
        return (
            f"Gruha Jyothi preliminary status: {result.get('status')}. "
            f"{result.get('user_message')} "
            "This is not an approval."
        )

    if tool_name == "analyze_solar" and isinstance(result, dict):
        sizing = result.get("sizing") or {}
        eco = result.get("economics") or {}
        return (
            f"Solar analysis status: {result.get('status')}. "
            f"Analyzed ≈ {sizing.get('analyzed_kwp')} kWp. "
            f"Estimated monthly saving ≈ ₹{eco.get('estimated_monthly_saving_inr')}. "
            f"{result.get('message')}"
        )

    if tool_name == "settle_metering" and isinstance(result, dict):
        return (
            f"Metering ({result.get('arrangement')}) status: {result.get('status')}. "
            f"Estimated monthly saving ≈ ₹{result.get('estimated_monthly_saving_inr')}. "
            f"{result.get('message')}"
        )

    if tool_name in {"analyze_vnm", "analyze_gnm"} and isinstance(result, dict):
        return (
            f"{tool_name} status: {result.get('status')}. "
            f"{result.get('message')} "
            "Not BESCOM approval — confirm via SRTPV portal."
        )

    if tool_name == "analyze_appliances" and isinstance(result, dict):
        return (
            f"Appliance estimate status: {result.get('status')}. "
            f"Model total ≈ {result.get('estimated_total_kwh')} kWh/month. "
            f"{result.get('message')}"
        )

    if tool_name == "list_metering_concepts":
        concepts = parsed.get("concepts") or []
        lines = [
            f"- {c.get('arrangement')}: {c.get('label')} "
            f"[{c.get('implementation_status')}]"
            for c in concepts
        ]
        return "Metering arrangements:\n" + "\n".join(lines)

    if tool_name == "list_agent_tools":
        tools = parsed.get("tools") or []
        return (
            "I can route to these deterministic tools: "
            + ", ".join(tools)
            + ". "
            + str(parsed.get("rule", ""))
        )

    if tool_name == "search_official_docs":
        payload = parsed.get("result", parsed)
        hits = payload.get("hits") or []
        if not hits:
            return (
                "No matching snippets found in data/Docs. "
                "Add BESCOM/KERC PDFs or digests and retry."
            )
        lines = [
            f"Official-source snippets for: {payload.get('query')}",
            str(payload.get("disclaimer", "")),
        ]
        for h in hits[:3]:
            lines.append(
                f"- [{h.get('source_name')} / {h.get('page_or_section')}] "
                f"{str(h.get('text', ''))[:280]}..."
            )
        return "\n".join(lines)

    return f"Tool `{tool_name}` result: {json.dumps(parsed)[:1200]}"
