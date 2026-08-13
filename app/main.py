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
    title="Integrum Energy — Bill Analysis",
    description=(
        "AI-powered residential electricity bill analysis for Karnataka / BESCOM "
        "domestic consumers. Extraction is AI-assisted; validation, classification, "
        "and calculations are deterministic."
    ),
    version="1.0.0",
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
        "app": "Integrum Energy — Bill Analysis",
        "module": "bill-analysis",
        "message": "Karnataka / BESCOM domestic bill upload, extraction, review, and analysis.",
        "docs": "/docs",
        "bill_extract": "POST /bills/extract",
        "bill_extract_batch": "POST /bills/extract-batch",
        "bill_confirm": "POST /bills/{analysis_id}/confirm",
        "consumer_history": "GET /consumers/{consumer_id}/history",
        "scope": {
            "state": "Karnataka",
            "discom": "BESCOM",
            "category": "DOMESTIC",
        },
    }
