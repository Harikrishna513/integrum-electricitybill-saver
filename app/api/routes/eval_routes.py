"""
Evaluation API — Milestone 21.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.evaluation.runner import report_as_dict, run_evaluation

router = APIRouter(prefix="/eval", tags=["evaluation"])


@router.get("/run")
def run_eval() -> dict:
    report = run_evaluation()
    return {"milestone": 21, **report_as_dict(report)}
