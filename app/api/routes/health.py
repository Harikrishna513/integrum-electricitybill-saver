from fastapi import APIRouter, HTTPException

from app.config.settings import get_settings
from app.infrastructure.llm.gemini_client import ping_gemini
from app.infrastructure.llm.mistral_ocr_client import ping_mistral_ocr

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
        "bill_extraction_provider": settings.bill_extraction_provider,
        "bill_extraction_fallback": settings.bill_extraction_fallback,
        "gemini_model": settings.gemini_model,
        "mistral_ocr_model": settings.mistral_ocr_model,
        "mistral_model": settings.mistral_model,
        # Never return API keys
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


@router.get("/health/mistral-ocr")
def health_mistral_ocr() -> dict:
    """
    Live Mistral Document AI OCR smoke test — costs ~1 OCR page.
  """
    try:
        result = ping_mistral_ocr()
        return {"status": "ok", **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=503,
            detail={
                "status": "error",
                "message": "Mistral OCR connection failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        ) from exc
