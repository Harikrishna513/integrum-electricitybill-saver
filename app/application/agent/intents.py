"""
Deterministic intent router — Milestone 18 (rules mode).

WHY
  Tests and offline demos can route questions without calling Gemini.
  LLM mode still uses the same tools.

COMMON MISTAKE
  Letting the rules router invent ₹ amounts — it only picks a tool + args.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass
class RoutedCall:
    tool_name: str
    args: dict[str, Any]
    reason: str


def route_question(question: str, *, default_as_of: str | None = None) -> RoutedCall:
    q = question.lower().strip()
    as_of = default_as_of or date.today().isoformat()

    if any(k in q for k in ("what can you", "which tools", "list tools", "capabilities")):
        return RoutedCall("list_agent_tools", {}, "User asked for tool catalog.")

    # Policy / official-source questions → RAG (Milestone 20)
    if any(
        k in q
        for k in (
            "latest rule",
            "latest vnm",
            "latest gnm",
            "official",
            "sop",
            "kerc",
            "regulation",
            "what does the rule",
            "according to",
            "policy",
            "75%",
            "minimum plant",
            "min plant",
            "procurement ratio",
            "20%",
            "lapsed",
        )
    ):
        return RoutedCall(
            "search_official_docs",
            {"query": question.strip(), "top_k": 5},
            "Regulatory / official-source keywords → RAG.",
        )

    if any(k in q for k in ("net metering", "gross metering", "vnm vs", "gnm vs", "difference between net")):
        if "vnm" in q or "virtual" in q or "gnm" in q or "group net" in q:
            return RoutedCall(
                "list_metering_concepts",
                {},
                "User asked about metering arrangement concepts.",
            )
        return RoutedCall(
            "list_metering_concepts",
            {},
            "User asked about net/gross metering concepts.",
        )

    if "gruha" in q or "gruhajyothi" in q or "gruha jyothi" in q:
        baseline = _first_float(q, ("baseline", "fy", "average"))
        current = _first_float(q, ("current", "units", "kwh"))
        args: dict[str, Any] = {"category": "DOMESTIC", "as_of": as_of}
        if baseline is not None:
            args["baseline_fy_2022_23_avg_units"] = baseline
        if current is not None:
            args["current_units"] = current
        return RoutedCall("check_gruha_jyothi", args, "Gruha Jyothi keywords.")

    if "vnm" in q or "virtual net" in q:
        # Minimal demo apartment if user didn't supply JSON — still educational.
        participants = [
            {
                "connection_id": "Flat-A",
                "sanctioned_load_kw": 3,
                "monthly_units": 200,
                "procurement_share_percent": 50,
            },
            {
                "connection_id": "Flat-B",
                "sanctioned_load_kw": 3,
                "monthly_units": 200,
                "procurement_share_percent": 50,
            },
        ]
        import json

        return RoutedCall(
            "analyze_vnm",
            {
                "as_of": as_of,
                "proposed_kwp": _first_float(q, ("kwp", "kw", "capacity")) or 6.0,
                "participants_json": json.dumps(participants),
                "same_discom_area": True,
            },
            "VNM keywords — demo two-flat pre-screen if details omitted.",
        )

    if "gnm" in q or "group net" in q:
        import json

        installs = [
            {
                "connection_id": "RR-HOST",
                "sanctioned_load_kw": 5,
                "monthly_units": 100,
                "priority": 1,
                "is_host": True,
            },
            {
                "connection_id": "RR-2",
                "sanctioned_load_kw": 3,
                "monthly_units": 200,
                "priority": 2,
                "is_host": False,
            },
        ]
        return RoutedCall(
            "analyze_gnm",
            {
                "as_of": as_of,
                "proposed_kwp": _first_float(q, ("kwp", "kw", "capacity")) or 6.0,
                "installations_json": json.dumps(installs),
                "same_discom_area": True,
                "same_consumer_name": True,
            },
            "GNM keywords — demo two-RR pre-screen if details omitted.",
        )

    if any(k in q for k in ("solar", "rooftop", "kwp", "surya ghar")):
        units = _first_float(q, ("units", "kwh", "consume")) or 300.0
        roof = _first_float(q, ("roof", "m2", "sqm")) or 30.0
        return RoutedCall(
            "analyze_solar",
            {
                "monthly_units": units,
                "as_of": as_of,
                "roof_area_m2": roof,
                "sanctioned_load_kw": 3.0,
            },
            "Solar keywords.",
        )

    if any(k in q for k in ("appliance", "ac ", "geyser", "fridge", "fan")):
        return RoutedCall(
            "analyze_appliances",
            {
                "people_count": 4,
                "ac_count": 1 if "ac" in q else 0,
                "geyser": "geyser" in q,
                "refrigerator": True,
                "fan_count": 3,
                "bill_units": _first_float(q, ("bill", "units")) or 400.0,
            },
            "Appliance keywords.",
        )

    if any(k in q for k in ("saving", "save", "reduce")):
        current = _first_float(q, ("current", "from", "units")) or 300.0
        saved = _first_float(q, ("save", "saved", "reduce", "by")) or 50.0
        return RoutedCall(
            "estimate_savings",
            {
                "current_units": current,
                "units_saved": saved,
                "as_of": as_of,
                "title": "Routed savings estimate",
            },
            "Savings keywords.",
        )

    if any(k in q for k in ("metering", "net meter", "gross meter", "export", "import")):
        c = _first_float(q, ("consum", "import", "load")) or 400.0
        g = _first_float(q, ("generat", "export", "solar")) or 250.0
        arrangement = "GROSS_METERING" if "gross" in q else "NET_METERING"
        return RoutedCall(
            "settle_metering",
            {
                "consumption_kwh": c,
                "generation_kwh": g,
                "as_of": as_of,
                "arrangement": arrangement,
            },
            "Metering settlement keywords.",
        )

    if any(k in q for k in ("tariff", "bill", "charge", "how much", "units")):
        units = _first_float(q, ("units", "kwh", "for")) or 120.0
        load = _first_float(q, ("load", "kw")) or 2.0
        return RoutedCall(
            "calculate_tariff",
            {
                "units": units,
                "as_of": as_of,
                "sanctioned_load_kw": load,
            },
            "Tariff/bill keywords.",
        )

    return RoutedCall(
        "list_agent_tools",
        {},
        "No clear intent — return tool catalog.",
    )


def _first_float(text: str, hints: tuple[str, ...]) -> float | None:
    """Best-effort number extraction: prefer '<number> <hint>' over '<hint> ... <number>'."""
    for hint in hints:
        m = re.search(rf"(\d+(?:\.\d+)?)\s*{hint}", text)
        if m:
            return float(m.group(1))
    for hint in hints:
        m = re.search(rf"{hint}[^\d]{{0,8}}(\d+(?:\.\d+)?)", text)
        if m:
            return float(m.group(1))
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else None
