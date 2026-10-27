"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, PostgresDsn, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Security
    secret_key: str = Field(..., min_length=32)
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
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
    storage_endpoint: str = Field(
        default="localhost:9000",
        validation_alias="STORAGE_ENDPOINT",
    )
    storage_access_key: str = Field(
        default="minioadmin",
        validation_alias="STORAGE_ACCESS_KEY",
    )
    storage_secret_key: str = Field(
        default="minioadmin",
        validation_alias="STORAGE_SECRET_KEY",
    )
    storage_bucket: str = "changeguard"
    storage_secure: bool = False
    storage_region: str = "us-east-1"

    # AI Models
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")
    default_embedding_model: str = "text-embedding-3-small"
    default_classification_model: str = "gpt-4o-mini"
    default_extraction_model: str = "gpt-4o-mini"
    default_reasoning_model: str = "gpt-4o"
    default_drafting_model: str = "gpt-4o"
    max_tokens_per_request: int = 8192
    ai_request_timeout: int = 120
    ai_max_retries: int = 3

    # Email Ingestion
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
    ocr_languages: list[str] = ["eng"]
    ocr_dpi: int = 300

    # Search & Retrieval
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_chunks_per_document: int = 500
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


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()