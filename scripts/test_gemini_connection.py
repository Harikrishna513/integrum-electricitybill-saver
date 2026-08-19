from __future__ import annotations

import sys
from pathlib import Path

# Allow running as: python scripts/test_gemini_connection.py
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    print("=" * 60)
    print("MILESTONE 1 — GEMINI CONNECTION TEST")
    print("=" * 60)

    try:
        from app.config.settings import get_settings

        settings = get_settings()
    except Exception as exc:  # noqa: BLE001
        print("\nFAILED to load settings.")
        print("Make sure you copied .env.example → .env and set GEMINI_API_KEY.")
        print(f"Error: {type(exc).__name__}: {exc}")
        return 1

    print("\n--- SETTINGS (safe) ---")
    print(f"APP_ENV       : {settings.app_env}")
    print(f"GEMINI_MODEL  : {settings.gemini_model}")
    print(f"API key set   : {'yes' if settings.gemini_api_key.get_secret_value() else 'no'}")
    print(f"API key length: {len(settings.gemini_api_key.get_secret_value())}")
    # Never print the actual key

    print("\n--- CALLING GEMINI ---")
    try:
        from app.infrastructure.llm.gemini_client import ping_gemini

        result = ping_gemini(settings)
    except Exception as exc:  # noqa: BLE001
        print("\nFAILED calling Gemini.")
        print(f"Error type: {type(exc).__name__}")
        print(f"Error     : {exc}")
        print("\nCommon fixes:")
        print("  1. Invalid/expired key → recreate at https://aistudio.google.com/apikey")
        print("  2. Wrong GEMINI_MODEL name → try gemini-2.5-flash")
        print("  3. No network / firewall blocking Google APIs")
        return 1

    print("OK — Gemini responded.")
    print(f"Model            : {result['model']}")
    print(f"Response preview : {result['response_preview']}")
    print("\n" + "=" * 60)
    print("Milestone 1 connection check PASSED")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
