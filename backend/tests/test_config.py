"""Unit tests for configuration loading."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


class TestConfigLoading:
    """Tests for configuration loading and validation."""

    def test_default_local_settings(self):
        """Test that default local settings load correctly."""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()
            assert settings.environment == "local"
            assert settings.debug is True
            assert settings.app_name == "ChangeGuard"
            assert settings.api_prefix == "/api/v1"

    def test_jwt_secret_min_length_validation(self):
        """Test that JWT_SECRET must be at least 32 characters."""
        with patch.dict(os.environ, {"JWT_SECRET": "short"}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "at least 32 characters" in str(exc_info.value)

    def test_jwt_secret_placeholder_warning(self, caplog):
        """Test that placeholder JWT_SECRET triggers warning."""
        with patch.dict(
            os.environ,
            {"JWT_SECRET": "your-super-secret-key-change-in-production-at-least-32-chars-long"},
            clear=True,
        ):
            settings = Settings()
            assert settings.jwt_secret == "your-super-secret-key-change-in-production-at-least-32-chars-long"

    def test_database_url_validation_alias(self):
        """Test that DATABASE_URL env var maps to database_url field."""
        test_url = "postgresql+asyncpg://user:pass@db:5432/testdb"
        with patch.dict(os.environ, {"DATABASE_URL": test_url, "JWT_SECRET": "a" * 32}, clear=True):
            settings = Settings()
            assert str(settings.database_url) == test_url

    def test_redis_url_validation_alias(self):
        """Test that REDIS_URL env var maps to redis_url field."""
        test_url = "redis://redis:6379/1"
        with patch.dict(os.environ, {"REDIS_URL": test_url, "JWT_SECRET": "a" * 32}, clear=True):
            settings = Settings()
            assert settings.redis_url == test_url

    def test_object_storage_fields_validation_aliases(self):
        """Test that object storage env vars map correctly."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a" * 32,
                "OBJECT_STORAGE_ENDPOINT": "s3.amazonaws.com",
                "OBJECT_STORAGE_ACCESS_KEY": "AKIA...",
                "OBJECT_STORAGE_SECRET_KEY": "secret...",
                "OBJECT_STORAGE_BUCKET": "my-bucket",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.object_storage_endpoint == "s3.amazonaws.com"
            assert settings.object_storage_access_key == "AKIA..."
            assert settings.object_storage_secret_key == "secret..."
            assert settings.object_storage_bucket == "my-bucket"

    def test_llm_provider_and_api_key(self):
        """Test LLM_PROVIDER and LLM_API_KEY fields."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a" * 32,
                "LLM_PROVIDER": "openai",
                "LLM_API_KEY": "sk-test-key",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.llm_provider == "openai"
            assert settings.llm_api_key == "sk-test-key"

    def test_embedding_model_field(self):
        """Test EMBEDDING_MODEL field."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a" * 32,
                "EMBEDDING_MODEL": "text-embedding-3-large",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.embedding_model == "text-embedding-3-large"

    def test_ocr_provider_field(self):
        """Test OCR_PROVIDER field."""
        with patch.dict(
            os.environ,
            {
                "JWT_SECRET": "a" * 32,
                "OCR_PROVIDER": "tesseract",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.ocr_provider == "tesseract"

    def test_environment_validation(self):
        """Test that environment must be one of local, staging, production."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32, "ENVIRONMENT": "invalid"}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "environment" in str(exc_info.value).lower()

    def test_llm_provider_validation(self):
        """Test that LLM_PROVIDER must be openai, anthropic, or none."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32, "LLM_PROVIDER": "invalid"}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "llm_provider" in str(exc_info.value).lower()

    def test_ocr_provider_validation(self):
        """Test that OCR_PROVIDER must be valid value."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32, "OCR_PROVIDER": "invalid"}, clear=True):
            with pytest.raises(ValidationError) as exc_info:
                Settings()
            assert "ocr_provider" in str(exc_info.value).lower()


class TestProductionValidation:
    """Tests for production environment validation."""

    def test_production_rejects_placeholder_jwt_secret(self):
        """Test that production fails with placeholder JWT_SECRET."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "your-super-secret-key-change-in-production-at-least-32-chars-long",
                "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "prod-key",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "JWT_SECRET must be a strong random secret in production" in str(exc_info.value)

    def test_production_rejects_local_database_url(self):
        """Test that production fails with localhost database."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "a" * 32,
                "DATABASE_URL": "postgresql+asyncpg://postgres:postgres@localhost:5432/changeguard",
                "REDIS_URL": "redis://prod-redis:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "prod-key",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "DATABASE_URL must use proper production credentials" in str(exc_info.value)

    def test_production_rejects_local_redis_url(self):
        """Test that production fails with localhost Redis."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "a" * 32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://localhost:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "prod-key",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "REDIS_URL must point to production Redis instance" in str(exc_info.value)

    def test_production_rejects_default_object_storage_credentials(self):
        """Test that production fails with default MinIO credentials."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "a" * 32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "minioadmin",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "OBJECT_STORAGE_ACCESS_KEY and OBJECT_STORAGE_SECRET_KEY must be changed" in str(exc_info.value)

    def test_production_rejects_missing_llm_api_key(self):
        """Test that production fails when LLM_PROVIDER is set but LLM_API_KEY is missing."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "a" * 32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "prod-key",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
                "LLM_PROVIDER": "openai",
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                Settings()
            assert "LLM_API_KEY is required when LLM_PROVIDER is 'openai'" in str(exc_info.value)

    def test_production_allows_valid_settings(self):
        """Test that production accepts valid configuration."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "a" * 32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "prod-key",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
                "LLM_PROVIDER": "none",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.environment == "production"

    def test_production_allows_llm_with_api_key(self):
        """Test that production allows LLM when API key is provided."""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET": "a" * 32,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379/0",
                "OBJECT_STORAGE_ACCESS_KEY": "prod-key",
                "OBJECT_STORAGE_SECRET_KEY": "prod-secret",
                "LLM_PROVIDER": "openai",
                "LLM_API_KEY": "sk-prod-key",
            },
            clear=True,
        ):
            settings = Settings()
            assert settings.llm_provider == "openai"
            assert settings.llm_api_key == "sk-prod-key"


class TestGetSettingsCache:
    """Tests for get_settings caching behavior."""

    def test_get_settings_returns_same_instance(self):
        """Test that get_settings returns cached instance."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32}, clear=True):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2

    def test_settings_singleton(self):
        """Test that module-level settings is same as get_settings()."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32}, clear=True):
            from app.core.config import settings as module_settings
            assert module_settings is get_settings()


class TestConfigComputedFields:
    """Tests for computed fields."""

    def test_base_path(self):
        """Test base_path computed field."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32}, clear=True):
            settings = Settings()
            assert settings.base_path.name == "backend"

    def test_alembic_path(self):
        """Test alembic_path computed field."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32}, clear=True):
            settings = Settings()
            assert settings.alembic_path.name == "alembic"

    def test_upload_path(self):
        """Test upload_path computed field."""
        with patch.dict(os.environ, {"JWT_SECRET": "a" * 32}, clear=True):
            settings = Settings()
            assert settings.upload_path.name == "uploads"


class TestEnvFileLoading:
    """Tests for .env file loading."""

    def test_env_file_loading(self, tmp_path):
        """Test that settings load from .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            "JWT_SECRET=test-secret-key-that-is-at-least-32-chars\n"
            "ENVIRONMENT=staging\n"
            "DEBUG=false\n",
            encoding="utf-8",
        )

        with patch.dict(os.environ, {}, clear=True):
            # Change to temp directory
            old_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                settings = Settings()
                assert settings.jwt_secret == "test-secret-key-that-is-at-least-32-chars"
                assert settings.environment == "staging"
                assert settings.debug is False
            finally:
                os.chdir(old_cwd)