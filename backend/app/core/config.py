"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.ai.gateway.config import ModelPricing, TaskPolicy, TaskType


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "ChangeGuard"
    app_version: str = "0.1.0"
    environment: Literal["local", "staging", "production"] = "local"
    debug: bool = True
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"

    # Security (JWT)
    jwt_secret: str = Field(
        default="local-development-secret-key-change-in-production-32-chars-min",
        min_length=32,
        validation_alias="JWT_SECRET",
    )
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(default=15, ge=1, le=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=7, ge=1, le=90)
    password_reset_expire_minutes: int = Field(default=30, ge=1, le=60)
    login_max_failures: int = Field(default=5, ge=1, le=100)
    login_window_seconds: int = Field(default=900, ge=1)
    auth_request_limit: int = Field(default=10, ge=1)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_from_email: str = "noreply@changeguard.invalid"
    smtp_starttls: bool = True
    password_hash_rounds: int = 12

    # Database
    database_url: PostgresDsn = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/changeguard",
        validation_alias="DATABASE_URL",
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30

    # Redis
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        validation_alias="REDIS_URL",
    )
    redis_max_connections: int = 50

    # Celery
    celery_broker_url: str = Field(
        default="redis://localhost:6379/1",
        validation_alias="CELERY_BROKER_URL",
    )
    celery_result_backend: str = Field(
        default="redis://localhost:6379/2",
        validation_alias="CELERY_RESULT_BACKEND",
    )
    celery_task_serializer: str = "json"
    celery_result_serializer: str = "json"
    celery_accept_content: list[str] = ["json"]
    celery_timezone: str = "UTC"
    celery_enable_utc: bool = True
    celery_task_track_started: bool = True
    celery_task_time_limit: int = 300
    celery_task_soft_time_limit: int = 240
    celery_worker_prefetch_multiplier: int = 4
    celery_worker_max_tasks_per_child: int = 1000

    # Object Storage (S3/MinIO)
    object_storage_endpoint: str = Field(
        default="localhost:9000",
        validation_alias="OBJECT_STORAGE_ENDPOINT",
    )
    object_storage_access_key: str = Field(
        default="minioadmin",
        validation_alias="OBJECT_STORAGE_ACCESS_KEY",
    )
    object_storage_secret_key: str = Field(
        default="minioadmin",
        validation_alias="OBJECT_STORAGE_SECRET_KEY",
    )
    object_storage_bucket: str = Field(
        default="changeguard",
        validation_alias="OBJECT_STORAGE_BUCKET",
    )
    object_storage_secure: bool = False
    object_storage_region: str = "us-east-1"

    # LLM / AI
    llm_provider: Literal["openai", "anthropic", "none"] = Field(
        default="none",
        validation_alias="LLM_PROVIDER",
    )
    llm_api_key: str | None = Field(default=None, validation_alias="LLM_API_KEY")
    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="EMBEDDING_MODEL")
    default_classification_model: str = "gpt-4o-mini"
    default_extraction_model: str = "gpt-4o-mini"
    default_reasoning_model: str = "gpt-4o"
    default_drafting_model: str = "gpt-4o"
    max_tokens_per_request: int = 8192
    ai_request_timeout: int = 120
    ai_max_retries: int = 3
    model_gateway_tasks: dict[TaskType, TaskPolicy] = Field(default_factory=dict)
    model_gateway_prices: dict[str, ModelPricing] = Field(default_factory=dict)

    # OCR
    ocr_provider: Literal["tesseract", "aws_textract", "azure_form_recognizer", "none"] = Field(
        default="none",
        validation_alias="OCR_PROVIDER",
    )
    ocr_languages: list[str] = ["eng"]
    ocr_dpi: int = 300

    # Email Ingestion (optional)
    email_imap_host: str | None = Field(default=None, validation_alias="EMAIL_IMAP_HOST")
    email_imap_port: int = 993
    email_imap_user: str | None = Field(default=None, validation_alias="EMAIL_IMAP_USER")
    email_imap_password: str | None = Field(default=None, validation_alias="EMAIL_IMAP_PASSWORD")
    email_graph_client_id: str | None = Field(default=None, validation_alias="EMAIL_GRAPH_CLIENT_ID")
    email_graph_client_secret: str | None = Field(default=None, validation_alias="EMAIL_GRAPH_CLIENT_SECRET")
    email_graph_tenant_id: str | None = Field(default=None, validation_alias="EMAIL_GRAPH_TENANT_ID")

    # Observability
    otel_endpoint: str | None = Field(default=None, validation_alias="OTEL_ENDPOINT")
    otel_service_name: str = "changeguard"
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")
    log_format: Literal["json", "console"] = "json"

    # Frontend
    frontend_url: str = "http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    # File Processing
    max_file_size_mb: int = 100
    allowed_mime_types: list[str] = [
        "application/pdf",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "text/plain",
        "application/zip",
    ]

    # Search & Retrieval
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_chunks_per_document: int = 500
    logical_chunk_max_chars: int = Field(default=8000, ge=256, le=24000)
    processing_review_threshold: float = Field(default=0.8, ge=0, le=1)
    classification_review_threshold: float = Field(default=0.8, ge=0, le=1)
    classification_rule_threshold: float = Field(default=0.85, ge=0, le=1)
    classification_rule_margin: float = Field(default=0.12, ge=0, le=1)
    structured_extraction_repair_retries: int = Field(default=1, ge=0, le=2)
    vector_dimension: int = 1536
    search_top_k: int = 20
    rerank_top_k: int = 10
    bm25_weight: float = 0.3
    vector_weight: float = 0.7
    min_similarity_threshold: float = 0.65

    # Workflow
    approval_timeout_hours: int = 72
    escalation_timeout_hours: int = 24
    max_approval_levels: int = 3

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # Paths
    @computed_field
    @property
    def base_path(self) -> Path:
        return Path(__file__).parent.parent.parent

    @computed_field
    @property
    def alembic_path(self) -> Path:
        return self.base_path / "alembic"

    @computed_field
    @property
    def upload_path(self) -> Path:
        return self.base_path / "uploads"

    # Validators
    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        if v in ("your-super-secret-key-change-in-production-at-least-32-chars-long", "changeme", "secret"):
            import warnings
            warnings.warn(
                "JWT_SECRET appears to be a placeholder value. "
                "Use a strong random secret in production!",
                UserWarning,
                stacklevel=2,
            )
        return v

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, v: PostgresDsn) -> PostgresDsn:
        url_str = str(v)
        if "localhost" in url_str and "postgres:postgres" in url_str:
            import warnings
            warnings.warn(
                "DATABASE_URL appears to use default local credentials. "
                "Use proper credentials in production!",
                UserWarning,
                stacklevel=2,
            )
        return v

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        """Fail fast if required production settings are missing."""
        if self.environment == "production":
            errors = []

            if self.jwt_secret in ("your-super-secret-key-change-in-production-at-least-32-chars-long", "local-development-secret-key-change-in-production-32-chars-min", "changeme", "secret"):
                errors.append("JWT_SECRET must be a strong random secret in production")

            db_url = str(self.database_url)
            if "localhost" in db_url and "postgres:postgres" in db_url:
                errors.append("DATABASE_URL must use proper production credentials (not default local)")

            if "localhost" in self.redis_url:
                errors.append("REDIS_URL must point to production Redis instance (not localhost)")

            if self.object_storage_access_key == "minioadmin" or self.object_storage_secret_key == "minioadmin":
                errors.append("OBJECT_STORAGE_ACCESS_KEY and OBJECT_STORAGE_SECRET_KEY must be changed from defaults in production")

            if self.llm_provider != "none" and not self.llm_api_key:
                errors.append(f"LLM_API_KEY is required when LLM_PROVIDER is '{self.llm_provider}'")

            if self.smtp_host and (not self.smtp_starttls or not self.frontend_url.startswith("https://")):
                errors.append("Password reset delivery in production requires STARTTLS and an HTTPS FRONTEND_URL")

            if errors:
                raise ValueError(
                    "Production configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
                )

        return self


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
