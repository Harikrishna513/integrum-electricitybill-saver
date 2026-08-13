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

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Typed settings validated at startup.

    If GEMINI_API_KEY is missing, the app fails fast with a clear error
    instead of crashing later inside LangChain with a vague message.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    gemini_api_key: SecretStr = Field(..., alias="GEMINI_API_KEY")
    gemini_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_MODEL")

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


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.

    Spring analogy: like a @Bean Settings that is created once.
    lru_cache = create once, reuse (until process restarts).
    """
    return Settings()
