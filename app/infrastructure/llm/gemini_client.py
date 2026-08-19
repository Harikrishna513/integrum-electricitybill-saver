"""
Gemini client factory.

CONCEPT
  One function that builds a ChatGoogleGenerativeAI instance from Settings.

WHY IT EXISTS
  - Domain/application code should not know how to construct Gemini.
  - Model name and API key come from Settings (.env), not hardcoded strings.
  - Later milestones reuse the same factory for vision extraction and chat.

SPRING ANALOGY
  Like a @Bean ChatClient or a GeminiClientFactory.

WHAT MUST NOT LIVE HERE (yet)
  Bill extraction prompts, tariff math, savings — those come later.

LANGCHAIN (modern)
  Course material may show google.generativeai or old LLM wrappers.
  Current integration: langchain_google_genai.ChatGoogleGenerativeAI
  Auth: pass api_key=... OR set GOOGLE_API_KEY / GEMINI_API_KEY in env.
  We pass api_key explicitly from Settings so our .env field name stays GEMINI_API_KEY.
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from app.config.settings import Settings, get_settings


def build_chat_model(settings: Settings | None = None) -> ChatGoogleGenerativeAI:
    """
    Create a Gemini chat model using env-configured model + API key.

    Returns:
        ChatGoogleGenerativeAI ready for .invoke() / .ainvoke()
    """
    settings = settings or get_settings()

    return ChatGoogleGenerativeAI(
        model=settings.gemini_model,
        api_key=settings.gemini_api_key.get_secret_value() if settings.gemini_api_key else "",
        temperature=0,
    )


def ping_gemini(settings: Settings | None = None) -> dict:
    """
    Smoke-test the Gemini connection with a tiny prompt.

    Used by:
      - scripts/test_gemini_connection.py
      - GET /health/gemini (optional live check)

    Returns a small dict safe to print (no API key).
    """
    settings = settings or get_settings()
    model = build_chat_model(settings)

    # HumanMessage is the modern LangChain message type (replaces older string-only patterns).
    from langchain_core.messages import HumanMessage

    response = model.invoke(
        [
            HumanMessage(
                content=(
                    "Reply with exactly this JSON and nothing else: "
                    '{"status":"ok","service":"bescom-bill-saver-ai"}'
                )
            )
        ]
    )

    text = response.content
    if isinstance(text, list):
        # Some models return a list of content blocks; flatten for display.
        text = "".join(
            block.get("text", str(block)) if isinstance(block, dict) else str(block)
            for block in text
        )

    return {
        "ok": True,
        "model": settings.gemini_model,
        "response_preview": str(text)[:500],
    }
