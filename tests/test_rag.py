"""
Tests for Milestone 20 — official-source RAG (data/Docs).
"""

from __future__ import annotations

import json

from app.application.agent.intents import route_question
from app.application.agent.tools import search_official_docs
from app.application.services.rag_service import OfficialSourceRetriever
from app.infrastructure.rag.corpus import OfficialDocsCorpus


def test_corpus_indexes_docs_folder():
    corpus = OfficialDocsCorpus()
    assert len(corpus.chunks) > 0
    names = {s["source_name"] for s in corpus.list_sources()}
    assert any("VNM" in n or "GNM" in n or "net_metering" in n or "KSEC" in n for n in names)


def test_rag_finds_vnm_minimum_plant_size():
    result = OfficialSourceRetriever().search("VNM minimum plant size 5 kW", top_k=5)
    assert result["hit_count"] >= 1
    blob = " ".join(h["text"].lower() for h in result["hits"])
    assert "5" in blob and ("kw" in blob or "minimum" in blob or "vnm" in blob)


def test_rag_finds_gnm_host_20_percent():
    result = OfficialSourceRetriever().search("GNM host 20% lapsed energy", top_k=5)
    assert result["hit_count"] >= 1
    blob = " ".join(h["text"].lower() for h in result["hits"])
    assert "20" in blob or "lapse" in blob or "gnm" in blob


def test_agent_routes_policy_question_to_rag():
    routed = route_question("What is the latest VNM rule for minimum plant size?")
    assert routed.tool_name == "search_official_docs"


def test_search_official_docs_tool_json():
    raw = search_official_docs("net metering surplus 75% generic tariff", top_k=3)
    payload = json.loads(raw)
    assert payload["tool"] == "search_official_docs"
    assert payload["result"]["hit_count"] >= 1
