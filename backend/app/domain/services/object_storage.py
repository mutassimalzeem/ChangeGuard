"""Object storage service for S3-compatible storage (MinIO, AWS S3, etc.)."""

import mimetypes
import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()

# Allowed file extensions and their corresponding MIME types
ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".webp": "image/webp",
}

# Magic bytes for file type validation
MAGIC_BYTES = {
    "application/pdf": [b"%PDF"],
    "application/msword": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [b"PK\x03\x04"],
    "application/vnd.ms-excel": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [b"PK\x03\x04"],
    "application/vnd.ms-powerpoint": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": [b"PK\x03\x04"],
    "text/plain": [],
    "text/csv": [],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/gif": [b"GIF87a", b"GIF89a"],
    "image/bmp": [b"BM"],
    "image/tiff": [b"II\x2a\x00", b"MM\x00\x2a"],
    "image/webp": [b"RIFF", b"WEBP"],
}

# Maximum file size (50 MB)
MAX_FILE_SIZE = 50 * 1024 * 1024

# Presigned URL expiry (1 hour)
PRESIGNED_URL_EXPIRY = 3600


class ObjectStorageError(Exception):
    """Base exception for object storage errors."""

    pass


class ValidationError(ObjectStorageError):
    """Raised when file validation fails."""

    pass


class StorageError(ObjectStorageError):
    """Raised when storage operation fails."""

    pass


class ObjectStorageService:
    """Service for managing object storage operations."""

    def __init__(self):
        self._client = None
        self._bucket = settings.object_storage_bucket

    def store_original(self, object_key: str, stream: BinaryIO, mime_type: str) -> None:
        """Create once; an existing original must never be overwritten."""
        try:
            self.client.put_object(
                Bucket=self._bucket, Key=object_key, Body=stream,
                ContentType=mime_type, IfNoneMatch="*",
            )
        except ClientError as exc:
            raise StorageError("Failed to preserve original") from exc

    @property
    def client(self):
        """Get or create S3 client."""
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=f"{'https' if settings.object_storage_secure else 'http'}://{settings.object_storage_endpoint}",
                aws_access_key_id=settings.object_storage_access_key,
                aws_secret_access_key=settings.object_storage_secret_key,
                region_name=settings.object_storage_region,
                config=BotoConfig(
                    signature_version="s3v4",
                    retries={"max_attempts": 3, "mode": "standard"},
                ),
            )
        return self._client

    def _validate_file(self, filename: str, content: bytes) -> tuple[str, str]:
        """Validate file extension, MIME type, magic bytes, and size.

        Returns:
            Tuple of (extension, mime_type)
        """
        # Check file size
        if len(content) > MAX_FILE_SIZE:
            raise ValidationError(
                f"File size exceeds maximum allowed size of {MAX_FILE_SIZE / (1024 * 1024)} MB"
            )

        # Get extension
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"File extension '{ext}' is not allowed. "
                f"Allowed extensions: {', '.join(sorted(ALLOWED_EXTENSIONS.keys()))}"
            )

        # Get expected MIME type
        expected_mime = ALLOWED_EXTENSIONS[ext]

        # Detect MIME type from content
        detected_mime = mimetypes.guess_type(filename)[0]
        if detected_mime and detected_mime != expected_mime:
            # For some formats like .docx/.xlsx/.pptx, they all share the same magic bytes (PK\x03\x04)
            # So we allow the extension-based MIME type to take precedence
            pass

        # Validate magic bytes
        magic_patterns = MAGIC_BYTES.get(expected_mime, [])
        if magic_patterns:
            matched = False
            for pattern in magic_patterns:
                if content.startswith(pattern):
                    matched = True
                    break
            if not matched:
                raise ValidationError(
                    f"File content does not match expected type '{expected_mime}'. "
                    "File may be corrupted or have incorrect extension."
                )

        return ext, expected_mime

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal and other issues."""
        # Get just the filename (no path components)
        filename = os.path.basename(filename)

        # Remove any null bytes
        filename = filename.replace("\x00", "")

        # Replace potentially dangerous characters
        filename = re.sub(r'[<>:"/\\|?*@\x00-\x1f]', "_", filename)

        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[: 255 - len(ext)] + ext

        # Ensure it's not empty
        if not filename or filename in (".", ".."):
            filename = "file"

        return filename

    def _build_object_key(
        self, tenant_id: str, project_id: str, document_id: str, extension: str
    ) -> str:
        """Build the object key with the required path structure.

        Path format: /{tenant_id}/{project_id}/documents/{document_id}/original.{ext}
        """
        # Validate UUIDs to prevent path traversal
        for name, value in [
            ("tenant_id", tenant_id),
            ("project_id", project_id),
            ("document_id", document_id),
        ]:
            try:
                uuid.UUID(value)
            except ValueError:
                raise ValidationError(f"Invalid {name}: must be a valid UUID")

        # Validate extension
        if not extension.startswith("."):
            extension = "." + extension
        if extension not in ALLOWED_EXTENSIONS:
            raise ValidationError(f"Invalid extension: {extension}")

        return f"{tenant_id}/{project_id}/documents/{document_id}/original{extension}"

    def upload_file(
        self,
        tenant_id: str,
        project_id: str,
        document_id: str,
        filename: str,
        content: bytes,
    ) -> str:
        """Upload a file to object storage."""
        # Sanitize filename
        filename = self._sanitize_filename(filename)

        # Validate file
        ext, mime_type = self._validate_file(filename, content)

        # Build object key
        object_key = self._build_object_key(tenant_id, project_id, document_id, ext)

        try:
            self.client.put_object(
                Bucket=self._bucket,
                Key=object_key,
                Body=content,
                ContentType=mime_type,
                Metadata={
                    "original_filename": filename,
                    "tenant_id": tenant_id,
                    "project_id": project_id,
                    "document_id": document_id,
                },
                ACL="private",
            )
            return object_key
        except ClientError as e:
            raise StorageError(f"Failed to upload file: {e}") from e

    def download_file(self, object_key: str) -> bytes:
        """Download a file from object storage."""
        try:
            response = self.client.get_object(Bucket=self._bucket, Key=object_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise StorageError(f"File not found: {object_key}") from e
            raise StorageError(f"Failed to download file: {e}") from e

    def delete_file(self, object_key: str) -> None:
        """Delete a file from object storage."""
        try:
            self.client.delete_object(Bucket=self._bucket, Key=object_key)
        except ClientError as e:
            raise StorageError(f"Failed to delete file: {e}") from e

    def generate_presigned_url(
        self, object_key: str, expiry_seconds: int = PRESIGNED_URL_EXPIRY
    ) -> str:
        """Generate a presigned download URL for a file."""
        if expiry_seconds > 604800:  # 7 days max
            expiry_seconds = 604800

        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expiry_seconds,
            )
            return url
        except ClientError as e:
            raise StorageError(f"Failed to generate presigned URL: {e}") from e

    def file_exists(self, object_key: str) -> bool:
        """Check if a file exists in object storage."""
        try:
            self.client.head_object(Bucket=self._bucket, Key=object_key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise StorageError(f"Failed to check file existence: {e}") from e

    def get_file_metadata(self, object_key: str) -> dict:
        """Get file metadata from object storage."""
        try:
            response = self.client.head_object(Bucket=self._bucket, Key=object_key)
            return {
                "content_type": response.get("ContentType"),
                "content_length": response.get("ContentLength"),
                "last_modified": response.get("LastModified"),
                "etag": response.get("ETag"),
                "metadata": response.get("Metadata", {}),
            }
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise StorageError(f"File not found: {object_key}") from e
            raise StorageError(f"Failed to get file metadata: {e}") from e

    def ensure_bucket_exists(self) -> None:
        """Ensure the bucket exists, create if it doesn't."""
        try:
            self.client.head_bucket(Bucket=self._bucket)
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                try:
                    if settings.object_storage_region == "us-east-1":
                        self.client.create_bucket(Bucket=self._bucket)
                    else:
                        self.client.create_bucket(
                            Bucket=self._bucket,
                            CreateBucketConfiguration={
                                "LocationConstraint": settings.object_storage_region
                            },
                        )
                    # Set bucket policy to private (no public access)
                    self.client.put_public_access_block(
                        Bucket=self._bucket,
                        PublicAccessBlockConfiguration={
                            "BlockPublicAcls": True,
                            "IgnorePublicAcls": True,
                            "BlockPublicPolicy": True,
                            "RestrictPublicBuckets": True,
                        },
                    )
                except ClientError as create_error:
                    raise StorageError(
                        f"Failed to create bucket: {create_error}"
                    ) from create_error
            else:
                raise StorageError(f"Failed to check bucket: {e}") from e


# Singleton instance
_object_storage_service = None


def get_object_storage_service() -> ObjectStorageService:
    """Get the object storage service singleton."""
    global _object_storage_service
    if _object_storage_service is None:
        _object_storage_service = ObjectStorageService()
    return _object_storage_service
