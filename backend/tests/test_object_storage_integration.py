"""Integration tests for object storage service with real MinIO.

These tests require a running MinIO instance. See INTEGRATION_TESTS_MINIO.md
for setup instructions. They are marked with @pytest.mark.integration and
can be skipped with `-m "not integration"`.
"""

import os

import pytest

from app.domain.services.object_storage import (
    ObjectStorageService,
    ValidationError,
)


# Skip if MinIO not available
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def minio_service():
    """Create service with real MinIO connection."""
    required_vars = [
        "OBJECT_STORAGE_ENDPOINT",
        "OBJECT_STORAGE_ACCESS_KEY",
        "OBJECT_STORAGE_SECRET_KEY",
        "OBJECT_STORAGE_BUCKET",
    ]
    for var in required_vars:
        if not os.environ.get(var):
            pytest.skip(f"{var} not set, skipping integration tests")

    service = ObjectStorageService()
    # Ensure bucket exists
    service.ensure_bucket_exists()
    yield service


@pytest.fixture
def valid_pdf():
    """Valid PDF content for testing."""
    return b"%PDF-1.4\n%Test PDF content for integration test"


@pytest.fixture
def valid_jpeg():
    """Valid JPEG content for testing."""
    return b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"


class TestObjectStorageIntegration:
    """Integration tests with real MinIO."""

    def test_upload_and_download(self, minio_service, valid_pdf):
        """Test upload and download cycle."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174002"

        # Upload
        object_key = minio_service.upload_file(
            tenant_id, project_id, document_id, "test.pdf", valid_pdf
        )

        assert (
            object_key
            == f"{tenant_id}/{project_id}/documents/{document_id}/original.pdf"
        )

        # Download
        downloaded = minio_service.download_file(object_key)
        assert downloaded == valid_pdf

    def test_generate_presigned_url(self, minio_service, valid_pdf):
        """Test presigned URL generation and access."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174003"

        object_key = minio_service.upload_file(
            tenant_id, project_id, document_id, "test.pdf", valid_pdf
        )

        # Generate presigned URL
        url = minio_service.generate_presigned_url(object_key, expiry_seconds=3600)

        assert url.startswith("http")
        assert "localhost:9000" in url or "127.0.0.1:9000" in url
        assert "changeguard" in url  # bucket name
        assert object_key in url

    def test_file_exists(self, minio_service, valid_pdf):
        """Test file existence check."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174004"

        object_key = minio_service.upload_file(
            tenant_id, project_id, document_id, "test.pdf", valid_pdf
        )

        assert minio_service.file_exists(object_key) is True
        assert minio_service.file_exists("nonexistent/key.pdf") is False

    def test_get_metadata(self, minio_service, valid_pdf):
        """Test metadata retrieval."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174005"

        object_key = minio_service.upload_file(
            tenant_id, project_id, document_id, "test.pdf", valid_pdf
        )

        metadata = minio_service.get_file_metadata(object_key)

        assert metadata["content_type"] == "application/pdf"
        assert metadata["content_length"] == len(valid_pdf)
        assert metadata["metadata"]["original_filename"] == "test.pdf"
        assert metadata["metadata"]["tenant_id"] == tenant_id
        assert metadata["metadata"]["project_id"] == project_id
        assert metadata["metadata"]["document_id"] == document_id

    def test_delete_file(self, minio_service, valid_pdf):
        """Test file deletion."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174006"

        object_key = minio_service.upload_file(
            tenant_id, project_id, document_id, "test.pdf", valid_pdf
        )

        assert minio_service.file_exists(object_key) is True

        minio_service.delete_file(object_key)

        assert minio_service.file_exists(object_key) is False

    def test_validation_rejects_invalid_extension(self, minio_service):
        """Test that invalid extensions are rejected."""
        with pytest.raises(ValidationError):
            minio_service.upload_file(
                "123e4567-e89b-12d3-a456-426614174000",
                "123e4567-e89b-12d3-a456-426614174001",
                "123e4567-e89b-12d3-a456-426614174002",
                "test.exe",
                b"content",
            )

    def test_validation_rejects_wrong_magic_bytes(self, minio_service):
        """Test that wrong magic bytes are rejected."""
        with pytest.raises(ValidationError):
            minio_service.upload_file(
                "123e4567-e89b-12d3-a456-426614174000",
                "123e4567-e89b-12d3-a456-426614174001",
                "123e4567-e89b-12d3-a456-426614174002",
                "test.pdf",
                b"not a pdf file",
            )

    def test_path_traversal_prevention(self, minio_service, valid_pdf):
        """Test that path traversal attempts are blocked."""
        with pytest.raises(ValidationError):
            minio_service.upload_file(
                "123e4567-e89b-12d3-a456-426614174000",
                "123e4567-e89b-12d3-a456-426614174001",
                "../../../etc/passwd",
                "test.pdf",
                valid_pdf,
            )

    def test_filename_sanitization(self, minio_service, valid_pdf):
        """Test that filenames are sanitized."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174008"

        object_key = minio_service.upload_file(
            tenant_id, project_id, document_id, "test<>file.pdf", valid_pdf
        )

        assert "<" not in object_key
        assert ">" not in object_key

        metadata = minio_service.get_file_metadata(object_key)
        assert metadata["metadata"]["original_filename"] == "test<>file.pdf"

    def test_multiple_file_types(self, minio_service, valid_jpeg):
        """Test uploading different file types."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174007"

        key = minio_service.upload_file(
            tenant_id, project_id, document_id, "image.jpg", valid_jpeg
        )
        assert key.endswith(".jpg")

        downloaded = minio_service.download_file(key)
        assert downloaded == valid_jpeg
