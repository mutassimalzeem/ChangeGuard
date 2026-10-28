"""Unit tests for object storage service."""

import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from app.domain.services.object_storage import (
    ObjectStorageService,
    ValidationError,
    StorageError,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    MAGIC_BYTES,
)


class TestObjectStorageService:
    """Tests for ObjectStorageService."""

    @pytest.fixture
    def service(self):
        """Create a service instance with mocked client."""
        with patch("app.domain.services.object_storage.boto3.client") as mock_client:
            service = ObjectStorageService()
            service._client = MagicMock()
            yield service

    @pytest.fixture
    def valid_pdf_content(self):
        """Valid PDF content with correct magic bytes."""
        return b"%PDF-1.4\n%Test PDF content"

    @pytest.fixture
    def valid_jpeg_content(self):
        """Valid JPEG content with correct magic bytes."""
        return b"\xff\xd8\xff\xe0\x00\x10JFIF"

    @pytest.fixture
    def valid_png_content(self):
        """Valid PNG content with correct magic bytes."""
        return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"

    @pytest.fixture
    def valid_docx_content(self):
        """Valid DOCX content (ZIP-based) with correct magic bytes."""
        return b"PK\x03\x04\x14\x00\x00\x00\x08\x00"

    def test_sanitize_filename_basic(self, service):
        """Test basic filename sanitization."""
        assert service._sanitize_filename("test.pdf") == "test.pdf"
        assert service._sanitize_filename("test file.pdf") == "test file.pdf"
        assert service._sanitize_filename("test@file.pdf") == "test_file.pdf"

    def test_sanitize_filename_path_traversal(self, service):
        """Test path traversal prevention."""
        assert service._sanitize_filename("../../../etc/passwd") == "passwd"
        assert service._sanitize_filename("..\\..\\windows\\system32") == "system32"
        assert service._sanitize_filename("subdir/../file.pdf") == "file.pdf"

    def test_sanitize_filename_null_bytes(self, service):
        """Test null byte removal."""
        assert service._sanitize_filename("test\x00.pdf") == "test.pdf"

    def test_sanitize_filename_dangerous_chars(self, service):
        """Test dangerous character replacement."""
        assert service._sanitize_filename('test<>:"|?*.pdf') == "test_______.pdf"
        assert service._sanitize_filename("test\x01\x02.pdf") == "test__.pdf"

    def test_sanitize_filename_length_limit(self, service):
        """Test filename length limiting."""
        long_name = "a" * 300 + ".pdf"
        result = service._sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".pdf")

    def test_sanitize_filename_empty(self, service):
        """Test empty filename handling."""
        assert service._sanitize_filename("") == "file"
        assert service._sanitize_filename(".") == "file"
        assert service._sanitize_filename("..") == "file"

    def test_validate_file_valid_pdf(self, service, valid_pdf_content):
        """Test PDF validation passes."""
        ext, mime = service._validate_file("test.pdf", valid_pdf_content)
        assert ext == ".pdf"
        assert mime == "application/pdf"

    def test_validate_file_valid_jpeg(self, service, valid_jpeg_content):
        """Test JPEG validation passes."""
        ext, mime = service._validate_file("test.jpg", valid_jpeg_content)
        assert ext == ".jpg"
        assert mime == "image/jpeg"

    def test_validate_file_valid_png(self, service, valid_png_content):
        """Test PNG validation passes."""
        ext, mime = service._validate_file("test.png", valid_png_content)
        assert ext == ".png"
        assert mime == "image/png"

    def test_validate_file_valid_docx(self, service, valid_docx_content):
        """Test DOCX validation passes."""
        ext, mime = service._validate_file("test.docx", valid_docx_content)
        assert ext == ".docx"
        assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_validate_file_invalid_extension(self, service, valid_pdf_content):
        """Test invalid extension rejection."""
        with pytest.raises(ValidationError) as exc_info:
            service._validate_file("test.exe", valid_pdf_content)
        assert "not allowed" in str(exc_info.value)

    def test_validate_file_case_insensitive_extension(self, service, valid_pdf_content):
        """Test case insensitive extension handling."""
        ext, mime = service._validate_file("test.PDF", valid_pdf_content)
        assert ext == ".pdf"

    def test_validate_file_size_limit(self, service):
        """Test file size limit enforcement."""
        large_content = b"x" * (MAX_FILE_SIZE + 1)
        with pytest.raises(ValidationError) as exc_info:
            service._validate_file("test.pdf", large_content)
        assert "exceeds maximum allowed size" in str(exc_info.value)

    def test_validate_file_magic_bytes_pdf(self, service):
        """Test PDF magic bytes validation."""
        with pytest.raises(ValidationError) as exc_info:
            service._validate_file("test.pdf", b"not a pdf")
        assert "does not match expected type" in str(exc_info.value)

    def test_validate_file_magic_bytes_jpeg(self, service):
        """Test JPEG magic bytes validation."""
        with pytest.raises(ValidationError):
            service._validate_file("test.jpg", b"not a jpeg")

    def test_validate_file_no_magic_bytes_txt(self, service):
        """Test text files with no magic bytes."""
        ext, mime = service._validate_file("test.txt", b"plain text content")
        assert ext == ".txt"
        assert mime == "text/plain"

    def test_validate_file_no_magic_bytes_csv(self, service):
        """Test CSV files with no magic bytes."""
        ext, mime = service._validate_file("test.csv", b"col1,col2\n1,2")
        assert ext == ".csv"
        assert mime == "text/csv"

    def test_build_object_key_valid(self, service):
        """Test object key building with valid UUIDs."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174002"
        key = service._build_object_key(tenant_id, project_id, document_id, ".pdf")
        expected = f"{tenant_id}/{project_id}/documents/{document_id}/original.pdf"
        assert key == expected

    def test_build_object_key_invalid_tenant_uuid(self, service):
        """Test object key building with invalid tenant UUID."""
        with pytest.raises(ValidationError) as exc_info:
            service._build_object_key("invalid", "123e4567-e89b-12d3-a456-426614174001", "123e4567-e89b-12d3-a456-426614174002", ".pdf")
        assert "Invalid tenant_id" in str(exc_info.value)

    def test_build_object_key_invalid_project_uuid(self, service):
        """Test object key building with invalid project UUID."""
        with pytest.raises(ValidationError) as exc_info:
            service._build_object_key("123e4567-e89b-12d3-a456-426614174000", "invalid", "123e4567-e89b-12d3-a456-426614174002", ".pdf")
        assert "Invalid project_id" in str(exc_info.value)

    def test_build_object_key_invalid_document_uuid(self, service):
        """Test object key building with invalid document UUID."""
        with pytest.raises(ValidationError) as exc_info:
            service._build_object_key("123e4567-e89b-12d3-a456-426614174000", "123e4567-e89b-12d3-a456-426614174001", "invalid", ".pdf")
        assert "Invalid document_id" in str(exc_info.value)

    def test_build_object_key_invalid_extension(self, service):
        """Test object key building with invalid extension."""
        with pytest.raises(ValidationError) as exc_info:
            service._build_object_key(
                "123e4567-e89b-12d3-a456-426614174000",
                "123e4567-e89b-12d3-a456-426614174001",
                "123e4567-e89b-12d3-a456-426614174002",
                ".exe"
            )
        assert "Invalid extension" in str(exc_info.value)

    def test_upload_file_success(self, service, valid_pdf_content):
        """Test successful file upload."""
        tenant_id = "123e4567-e89b-12d3-a456-426614174000"
        project_id = "123e4567-e89b-12d3-a456-426614174001"
        document_id = "123e4567-e89b-12d3-a456-426614174002"

        result = service.upload_file(tenant_id, project_id, document_id, "test.pdf", valid_pdf_content)

        assert result == f"{tenant_id}/{project_id}/documents/{document_id}/original.pdf"
        service._client.put_object.assert_called_once()
        call_args = service._client.put_object.call_args
        assert call_args.kwargs["Bucket"] == service._bucket
        assert call_args.kwargs["Key"] == result
        assert call_args.kwargs["ACL"] == "private"

    def test_upload_file_validation_error(self, service):
        """Test upload with validation error."""
        with pytest.raises(ValidationError):
            service.upload_file(
                "123e4567-e89b-12d3-a456-426614174000",
                "123e4567-e89b-12d3-a456-426614174001",
                "123e4567-e89b-12d3-a456-426614174002",
                "test.exe",
                b"content"
            )

    def test_upload_file_storage_error(self, service, valid_pdf_content):
        """Test upload with storage error."""
        service._client.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Server error"}},
            "PutObject"
        )
        with pytest.raises(StorageError):
            service.upload_file(
                "123e4567-e89b-12d3-a456-426614174000",
                "123e4567-e89b-12d3-a456-426614174001",
                "123e4567-e89b-12d3-a456-426614174002",
                "test.pdf",
                valid_pdf_content
            )

    def test_download_file_success(self, service):
        """Test successful file download."""
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        service._client.get_object.return_value = {"Body": mock_body}

        result = service.download_file("test/key.pdf")

        assert result == b"file content"
        service._client.get_object.assert_called_once_with(Bucket=service._bucket, Key="test/key.pdf")

    def test_download_file_not_found(self, service):
        """Test download of non-existent file."""
        service._client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject"
        )
        with pytest.raises(StorageError) as exc_info:
            service.download_file("test/key.pdf")
        assert "File not found" in str(exc_info.value)

    def test_download_file_storage_error(self, service):
        """Test download with storage error."""
        service._client.get_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Server error"}},
            "GetObject"
        )
        with pytest.raises(StorageError):
            service.download_file("test/key.pdf")

    def test_delete_file_success(self, service):
        """Test successful file deletion."""
        service.delete_file("test/key.pdf")
        service._client.delete_object.assert_called_once_with(Bucket=service._bucket, Key="test/key.pdf")

    def test_delete_file_storage_error(self, service):
        """Test deletion with storage error."""
        service._client.delete_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Server error"}},
            "DeleteObject"
        )
        with pytest.raises(StorageError):
            service.delete_file("test/key.pdf")

    def test_generate_presigned_url_success(self, service):
        """Test successful presigned URL generation."""
        service._client.generate_presigned_url.return_value = "https://example.com/presigned-url"

        url = service.generate_presigned_url("test/key.pdf", 3600)

        assert url == "https://example.com/presigned-url"
        service._client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": service._bucket, "Key": "test/key.pdf"},
            ExpiresIn=3600
        )

    def test_generate_presigned_url_max_expiry(self, service):
        """Test presigned URL with max expiry (7 days)."""
        service._client.generate_presigned_url.return_value = "https://example.com/presigned-url"

        url = service.generate_presigned_url("test/key.pdf", 1000000)  # More than 7 days

        # Should be capped at 7 days (604800 seconds)
        service._client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": service._bucket, "Key": "test/key.pdf"},
            ExpiresIn=604800
        )

    def test_generate_presigned_url_storage_error(self, service):
        """Test presigned URL generation with storage error."""
        service._client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Server error"}},
            "GeneratePresignedUrl"
        )
        with pytest.raises(StorageError):
            service.generate_presigned_url("test/key.pdf")

    def test_file_exists_true(self, service):
        """Test file exists check - file exists."""
        service._client.head_object.return_value = {}
        assert service.file_exists("test/key.pdf") is True

    def test_file_exists_false(self, service):
        """Test file exists check - file not found."""
        service._client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject"
        )
        assert service.file_exists("test/key.pdf") is False

    def test_file_exists_storage_error(self, service):
        """Test file exists check with storage error."""
        service._client.head_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Server error"}},
            "HeadObject"
        )
        with pytest.raises(StorageError):
            service.file_exists("test/key.pdf")

    def test_get_file_metadata_success(self, service):
        """Test successful metadata retrieval."""
        service._client.head_object.return_value = {
            "ContentType": "application/pdf",
            "ContentLength": 1024,
            "LastModified": "2024-01-01T00:00:00Z",
            "ETag": '"abc123"',
            "Metadata": {"original_filename": "test.pdf"}
        }

        metadata = service.get_file_metadata("test/key.pdf")

        assert metadata["content_type"] == "application/pdf"
        assert metadata["content_length"] == 1024
        assert metadata["metadata"]["original_filename"] == "test.pdf"

    def test_get_file_metadata_not_found(self, service):
        """Test metadata retrieval for non-existent file."""
        service._client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject"
        )
        with pytest.raises(StorageError) as exc_info:
            service.get_file_metadata("test/key.pdf")
        assert "File not found" in str(exc_info.value)

    def test_ensure_bucket_exists_already_exists(self, service):
        """Test ensure_bucket_exists when bucket already exists."""
        service._client.head_bucket.return_value = {}
        service.ensure_bucket_exists()
        service._client.head_bucket.assert_called_once_with(Bucket=service._bucket)
        service._client.create_bucket.assert_not_called()

    def test_ensure_bucket_exists_create_new_us_east_1(self, service):
        """Test ensure_bucket_exists creates bucket in us-east-1."""
        service._client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadBucket"
        )
        service._client.create_bucket.return_value = {}
        service._client.put_public_access_block.return_value = {}

        with patch("app.domain.services.object_storage.settings.object_storage_region", "us-east-1"):
            service.ensure_bucket_exists()

        service._client.create_bucket.assert_called_once_with(Bucket=service._bucket)
        service._client.put_public_access_block.assert_called_once()

    def test_ensure_bucket_exists_create_new_other_region(self, service):
        """Test ensure_bucket_exists creates bucket in non-us-east-1 region."""
        service._client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadBucket"
        )
        service._client.create_bucket.return_value = {}
        service._client.put_public_access_block.return_value = {}

        with patch("app.domain.services.object_storage.settings.object_storage_region", "eu-west-1"):
            service.ensure_bucket_exists()

        service._client.create_bucket.assert_called_once_with(
            Bucket=service._bucket,
            CreateBucketConfiguration={"LocationConstraint": "eu-west-1"}
        )

    def test_ensure_bucket_exists_create_fails(self, service):
        """Test ensure_bucket_exists when creation fails."""
        service._client.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadBucket"
        )
        service._client.create_bucket.side_effect = ClientError(
            {"Error": {"Code": "BucketAlreadyExists", "Message": "Bucket exists"}},
            "CreateBucket"
        )
        with pytest.raises(StorageError) as exc_info:
            service.ensure_bucket_exists()
        assert "Failed to create bucket" in str(exc_info.value)


class TestAllowedExtensions:
    """Tests for allowed extensions constant."""

    def test_allowed_extensions_not_empty(self):
        """Test that allowed extensions is not empty."""
        assert len(ALLOWED_EXTENSIONS) > 0

    def test_allowed_extensions_has_common_types(self):
        """Test that common file types are allowed."""
        assert ".pdf" in ALLOWED_EXTENSIONS
        assert ".docx" in ALLOWED_EXTENSIONS
        assert ".xlsx" in ALLOWED_EXTENSIONS
        assert ".png" in ALLOWED_EXTENSIONS
        assert ".jpg" in ALLOWED_EXTENSIONS

    def test_magic_bytes_for_all_allowed(self):
        """Test that magic bytes defined for all allowed types with patterns."""
        for ext, mime in ALLOWED_EXTENSIONS.items():
            if mime in ["text/plain", "text/csv"]:
                continue  # These don't have magic bytes
            assert mime in MAGIC_BYTES, f"Missing magic bytes for {mime} ({ext})"
            assert len(MAGIC_BYTES[mime]) > 0, f"Empty magic bytes for {mime}"