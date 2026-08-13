"""
Agent Q&A API — Milestone 18 (tool routing).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.application.agent.runner import AgentRunner
from app.application.agent.tools import build_agent_tools
from app.config.settings import get_settings

router = APIRouter(prefix="/agent", tags=["agent"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    session_id: str = Field(
        default="default",
        description="Client session id for contextual rewriting + memory.",
    )
    mode: Literal["rules", "llm"] = Field(
        default="rules",
        description=(
            "rules = deterministic intent→tool (offline/tests). "
            "llm = Gemini tool-calling loop."
        ),
    )


@router.get("/tools")
def list_tools() -> dict:
    tools = build_agent_tools()
    return {
        "milestone": 18,
        "message": (
            "Agent tools wrap deterministic engines. Gemini may select tools but "
            "must not invent ₹ or approvals."
        ),
        "tools": [
            {
                "name": t.name,
                "description": t.description,
            }
            for t in tools
        ],
    }


@router.post("/ask")
def ask_agent(body: AskRequest) -> dict:
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="question must not be empty")

    runner = AgentRunner()
    try:
        result = runner.ask(
            body.question.strip(),
            mode=body.mode,
            session_id=body.session_id,
        )
    except Exception as exc:  # noqa: BLE001 - surface LLM/config errors cleanly
        raise HTTPException(
            status_code=502,
            detail=f"Agent failed: {exc}",
        ) from exc

    if get_settings().is_development:
        print("=" * 60)
        print("MILESTONE 18 — AGENT")
        print("=" * 60)
        print(f"mode   : {result.mode}")
        print(f"tools  : {result.tools_called}")
        print(f"answer : {result.answer[:300]}")

    return {
        "milestone": 18,
        "mode": result.mode,
        "question": result.question,
        "rewritten_question": result.rewritten_question,
        "answer": result.answer,
        "tools_called": result.tools_called,
        "tool_results": result.tool_results,
        "routed_reason": result.routed_reason,
        "warnings": result.warnings,
    }
