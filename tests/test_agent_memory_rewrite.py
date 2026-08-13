"""
Milestone 19 — contextual rewriting + session memory.
"""

from __future__ import annotations

from app.application.agent.runner import AgentRunner


def test_why_followup_injects_last_bill_inputs():
    session = "m19-test-1"
    runner = AgentRunner()

    first = runner.ask(
        "Estimate my BESCOM bill for 120 units with 2 kW load",
        mode="rules",
        session_id=session,
    )
    assert first.tools_called == ["calculate_tariff"]

    second = runner.ask(
        "Why is it high?",
        mode="rules",
        session_id=session,
    )

    # Rewriter should inject the last known bill inputs so routing extracts them.
    assert second.rewritten_question is not None
    assert "120" in second.rewritten_question
    assert "2" in second.rewritten_question

    # Routing should still call calculate_tariff using injected parameters.
    assert second.tools_called == ["calculate_tariff"]

