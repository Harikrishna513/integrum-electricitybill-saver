"""
Unit tests for Settings — no Gemini API call required.

Run:
  pytest -q
"""

import pytest
from pydantic import ValidationError


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("APP_ENV", "development")

    # Clear cached settings between tests
    from app.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    assert settings.gemini_model == "gemini-2.5-flash"
    assert settings.gemini_api_key.get_secret_value() == "test-key-not-real"
    assert settings.is_development is True

    get_settings.cache_clear()


def test_settings_requires_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    from app.config.settings import Settings, get_settings

    get_settings.cache_clear()

    with pytest.raises(ValidationError):
        Settings(_env_file=None)

    get_settings.cache_clear()


def test_secret_str_not_leaked_in_repr(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    from app.config.settings import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    # SecretStr should not expose the raw key via normal string conversion of the field
    assert "super-secret-key" not in repr(settings.gemini_api_key)

    get_settings.cache_clear()
