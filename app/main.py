"""
FastAPI application entrypoint.

Run:
  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.middleware import apply_production_middleware
from app.api.routes import (
    agent,
    appliances,
    bills,
    consumers,
    eval_routes,
    gnm,
    health,
    metering,
    rag,
    savings,
    schemes,
    solar,
    tariff,
    vnm,
)
from app.config.settings import get_settings
from app.infrastructure.persistence.db import init_db


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield


settings = get_settings()

app = FastAPI(
    title="BESCOM Bill Saver AI",
    description=(
        "Karnataka / BESCOM residential bill understanding and savings advisor. "
        "Milestone 24: user confirmation of extracted fields. "
        "VNM/GNM remain preliminary analysis only."
    ),
    version="0.24.0",
    lifespan=lifespan,
)

apply_production_middleware(app, settings)

app.include_router(health.router)
app.include_router(bills.router)
app.include_router(consumers.router)
app.include_router(tariff.router)
app.include_router(schemes.router)
app.include_router(savings.router)
app.include_router(appliances.router)
app.include_router(solar.router)
app.include_router(metering.router)
app.include_router(vnm.router)
app.include_router(gnm.router)
app.include_router(agent.router)
app.include_router(rag.router)
app.include_router(eval_routes.router)


@app.get("/")
def root() -> dict:
    return {
        "app": "BESCOM Bill Saver AI",
        "milestone": 24,
        "message": (
            "User field confirmation enabled. "
            "Engines own money; docs own policy text; user confirms OCR gaps."
        ),
        "docs": "/docs",
        "rag_sources": "GET /rag/sources",
        "rag_search": "POST /rag/search",
        "bill_confirm": "POST /bills/{analysis_id}/confirm",
        "vnm_analyze": "POST /vnm/analyze",
        "gnm_analyze": "POST /gnm/analyze",
        "eval_run": "GET /eval/run",
        "agent_ask": "POST /agent/ask",
        "frontend": "See /frontend (Next.js)",
        "app_v1_supports": ["DOMESTIC"],
        "discom_scope": ["BESCOM"],
        "state_scope": ["Karnataka"],
    }
