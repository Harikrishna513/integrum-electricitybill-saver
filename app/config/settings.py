"""
Settings — single place for environment configuration.

CONCEPT
  Central config object loaded from .env / OS environment.

WHY IT EXISTS
  So we never hardcode GEMINI_API_KEY or GEMINI_MODEL in business code.
  Changing the model = edit .env, not rewrite Python.

SPRING ANALOGY
  Like @ConfigurationProperties + application.yml.
  settings.gemini_model  ≈  @Value("${gemini.model}")

COMMON MISTAKE
  Writing ChatGoogleGenerativeAI(model="gemini-2.5-flash") inside services.
  That locks the model into code and makes A/B testing painful.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed settings validated at startup.

    If the active bill extraction provider's API key is missing, the app fails fast
    instead of crashing later inside LangChain with a vague message.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    bill_extraction_provider: Literal["gemini", "mistral", "mistral_ocr"] = Field(
        default="gemini",
        alias="BILL_EXTRACTION_PROVIDER",
        description="gemini=vision | mistral_ocr=Mistral OCR 3 + Gemini parse (recommended) | mistral=legacy Pixtral vision",
    )

    bill_extraction_fallback: bool = Field(
        default=True,
        alias="BILL_EXTRACTION_FALLBACK",
        description="If primary OCR fails, retry with Gemini vision.",
    )

    gemini_api_key: SecretStr | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        alias="GEMINI_MODEL",
        description="Structured field parsing, summaries, and agent chat.",
    )

    mistral_api_key: SecretStr | None = Field(default=None, alias="MISTRAL_API_KEY")
    mistral_ocr_model: str = Field(
        default="mistral-ocr-latest",
        alias="MISTRAL_OCR_MODEL",
        description="Mistral Document AI OCR — aliases: mistral-ocr-3.0, mistral-ocr-2512.",
    )
    mistral_model: str = Field(
        default="pixtral-large-latest",
        alias="MISTRAL_MODEL",
        description="Legacy Pixtral vision when BILL_EXTRACTION_PROVIDER=mistral.",
    )

    database_url: str = Field(
        default="sqlite:///./data/bescom_bill_saver.db",
        alias="DATABASE_URL",
    )

    # Milestone 2 — bill upload / local file storage
    upload_dir: str = Field(default="./data/uploads", alias="UPLOAD_DIR")
    max_upload_bytes: int = Field(
        default=10 * 1024 * 1024,  # 10 MB
        alias="MAX_UPLOAD_BYTES",
    )

    # Milestone 20 — official docs RAG
    docs_dir: str = Field(default="./data/Docs", alias="DOCS_DIR")

    # Milestone 23 — production
    cors_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
        alias="CORS_ORIGINS",
    )
    api_public_url: str = Field(
        default="http://127.0.0.1:8000",
        alias="API_PUBLIC_URL",
    )

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() == "development"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_bill_content_types(self) -> frozenset[str]:
        """MIME types we accept for bill uploads in Milestone 2."""
        return frozenset(
            {
                "image/jpeg",
                "image/png",
                "image/webp",
                "application/pdf",
            }
        )

    @model_validator(mode="after")
    def _require_provider_api_key(self) -> "Settings":
        if self.bill_extraction_provider == "gemini" and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when BILL_EXTRACTION_PROVIDER=gemini"
            )
        if self.bill_extraction_provider in ("mistral", "mistral_ocr") and not self.mistral_api_key:
            raise ValueError(
                "MISTRAL_API_KEY is required when BILL_EXTRACTION_PROVIDER is mistral or mistral_ocr"
            )
        if self.bill_extraction_provider == "mistral_ocr" and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when BILL_EXTRACTION_PROVIDER=mistral_ocr "
                "(Gemini parses OCR text into bill fields; also used for summaries)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.

    Spring analogy: like a @Bean Settings that is created once.
    lru_cache = create once, reuse (until process restarts).
    """
    return Settings()
