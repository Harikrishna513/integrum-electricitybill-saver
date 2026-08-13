"""
Tests for Milestone 21 — evaluation framework.
"""

from __future__ import annotations

from app.evaluation.runner import run_evaluation


def test_evaluation_suite_passes():
    report = run_evaluation()
    assert report.total >= 6
    assert report.failed == 0, [
        (r.case_id, r.detail) for r in report.results if not r.passed
    ]
