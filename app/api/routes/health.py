"""
Health endpoints — prove the process is up and (optionally) Gemini works.

SPRING ANALOGY
  Like Actuator /health, plus a custom Gemini connectivity check.
"""

from fastapi import APIRouter, HTTPException

from app.config.settings import get_settings
from app.infrastructure.llm.gemini_client import ping_gemini

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """
    Liveness check — does NOT call Gemini (fast, free, safe for load balancers).
    """
    settings = get_settings()
    return {
        "status": "ok",
        "app": "bescom-bill-saver-ai",
        "env": settings.app_env,
        "gemini_model": settings.gemini_model,
        # Never return the API key
    }


@router.get("/health/gemini")
def health_gemini() -> dict:
    """
    Live Gemini smoke test — costs a tiny API call.

    Use this while learning. In production you might protect or remove it.
    """
    try:
        result = ping_gemini()
        return {"status": "ok", **result}
    except Exception as exc:  # noqa: BLE001 — surface any provider error clearly for learning
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "message": "Gemini connection failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc
