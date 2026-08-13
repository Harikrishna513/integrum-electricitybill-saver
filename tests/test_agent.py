"""
Tests for Milestone 18 — agent tools + rules routing.
"""

from __future__ import annotations

import json

from app.application.agent.intents import route_question
from app.application.agent.runner import AgentRunner
from app.application.agent.tools import (
    build_agent_tools,
    calculate_tariff,
    check_gruha_jyothi,
    estimate_savings,
)


def test_tool_catalog_not_empty():
    tools = build_agent_tools()
    names = {t.name for t in tools}
    assert "calculate_tariff" in names
    assert "check_gruha_jyothi" in names
    assert "analyze_vnm" in names
    assert "analyze_gnm" in names
    assert "estimate_savings" in names


def test_calculate_tariff_tool_is_deterministic():
    raw = calculate_tariff(units=120, as_of="2025-06-15", sanctioned_load_kw=2)
    payload = json.loads(raw)
    result = payload["result"]
    assert result["estimated_total"] == 1035.55
    assert result["rule_version"] == "BESCOM_LT1_DOMESTIC_BOOTSTRAP_2025_04"


def test_savings_tool_uses_engine():
    raw = estimate_savings(
        current_units=200,
        units_saved=60,
        as_of="2025-06-15",
        sanctioned_load_kw=2,
    )
    payload = json.loads(raw)
    assert payload["result"]["estimated_monthly_saving"] is not None
    assert payload["result"]["estimated_monthly_saving"] > 0


def test_gruha_tool_never_says_approved_in_status():
    raw = check_gruha_jyothi(
        category="DOMESTIC",
        as_of="2025-06-15",
        baseline_fy_2022_23_avg_units=150,
        current_units=140,
    )
    payload = json.loads(raw)
    status = str(payload["result"]["status"])
    assert "APPROVED" not in status.upper()


def test_intent_routes_tariff():
    routed = route_question("How much is my bill for 120 units on 2025 tariff?")
    assert routed.tool_name == "calculate_tariff"
    assert routed.args["units"] == 120.0


def test_intent_routes_gruha():
    routed = route_question("Am I eligible for Gruha Jyothi?")
    assert routed.tool_name == "check_gruha_jyothi"


def test_intent_routes_vnm():
    routed = route_question("Can our apartment do VNM with 6 kWp?")
    assert routed.tool_name == "analyze_vnm"
    assert routed.args["proposed_kwp"] == 6.0


def test_rules_agent_answers_via_tool():
    result = AgentRunner().ask(
        "Estimate my BESCOM bill for 120 units with 2 kW load",
        mode="rules",
    )
    assert result.mode == "rules"
    assert result.tools_called == ["calculate_tariff"]
    assert "1035.55" in result.answer or "₹" in result.answer
    assert result.tool_results[0]["result"]["result"]["estimated_total"] == 1035.55
