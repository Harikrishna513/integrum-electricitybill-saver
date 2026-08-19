"""Mistral chat model factory — vision OCR via Pixtral."""

from langchain_mistralai import ChatMistralAI

from app.config.settings import Settings, get_settings


def build_mistral_chat_model(settings: Settings | None = None) -> ChatMistralAI:
    settings = settings or get_settings()
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY is required when BILL_EXTRACTION_PROVIDER=mistral")

    return ChatMistralAI(
        model=settings.mistral_model,
        api_key=settings.mistral_api_key.get_secret_value(),
        temperature=0,
    )


def ping_mistral(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    model = build_mistral_chat_model(settings)
    from langchain_core.messages import HumanMessage

    response = model.invoke(
        [
            HumanMessage(
                content='Reply with exactly: {"status":"ok","service":"bescom-bill-saver-ai"}'
            )
        ]
    )
    text = response.content
    if isinstance(text, list):
        text = "".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in text
        )
    return {
        "ok": True,
        "model": settings.mistral_model,
        "response_preview": str(text)[:500],
    }
