"""Scoped registry and immutable originals. Rejected bytes remain quarantined."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.domain.models import Document
from app.domain.services.document_files import MAX_SIZE, TYPES, validate_document
from app.domain.services.project_access import ProjectAccessService
from app.policy.permissions import Action, has_permission


class DocumentService:
    def __init__(self, session, user, storage):
        self.session, self.user, self.storage = session, user, storage
        self.access = ProjectAccessService(session, user)

    def permission(self, write=False):
        if not has_permission(
            self.user.role, Action.DOCUMENT_WRITE if write else Action.DOCUMENT_READ
        ):
            raise HTTPException(403, "Access denied")

    def visible(self, query):
        query = query.where(
            Document.tenant_id == self.user.tenant_id, Document.deleted_at.is_(None)
        )
        if self.user.role not in {"owner", "admin"}:
            query = query.where(
                (Document.access_level == "project") | (Document.uploaded_by_id == self.user.id)
            )
        return query

    async def get(self, document_id: UUID, write=False):
        self.permission(write)
        document = await self.session.scalar(
            self.visible(select(Document).where(Document.id == document_id))
        )
        if document is None:
            raise HTTPException(404, "Document not found")
        await self.access.project(document.project_id)
        return document

    async def list(self, project_id, offset=0, limit=50):
        self.permission()
        await self.access.project(project_id)
        rows = await self.session.scalars(
            self.visible(select(Document).where(Document.project_id == project_id))
            .order_by(Document.created_at.desc(), Document.id)
            .offset(offset)
            .limit(limit)
        )
        return list(rows)

    async def upload(self, project_id, file: UploadFile, source, document_type, access_level):
        self.permission(True)
        await self.access.project(project_id)
        digest, size = hashlib.sha256(), 0
        while chunk := await file.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
        await file.seek(0)
        checksum = digest.hexdigest()
        # Include soft-deleted and restricted rows without disclosing their IDs.
        duplicate = await self.session.scalar(
            select(Document).where(
                Document.tenant_id == self.user.tenant_id,
                Document.project_id == project_id,
                Document.checksum == checksum,
            )
        )
        if duplicate:
            raise HTTPException(409, "Duplicate document in this project")
        filename = self.storage._sanitize_filename((file.filename or "file").replace("\\", "/"))
        error = None
        extension = Path(filename).suffix.lower().lstrip(".")[:32] or "unknown"
        mime = TYPES.get(extension, "application/octet-stream")
        if size > MAX_SIZE:
            error = "File exceeds 50 MiB upload limit"
        else:
            content = await file.read()
            await file.seek(0)
            try:
                extension, mime = await run_in_threadpool(validate_document, filename, content)
            except ValueError as exc:
                error = str(exc)
        document_id = uuid4()
        namespace = "quarantine" if error else "documents"
        key = f"{self.user.tenant_id}/{project_id}/{namespace}/{document_id}/original"
        document = Document(
            id=document_id,
            tenant_id=self.user.tenant_id,
            project_id=project_id,
            filename=filename,
            storage_key=key,
            mime_type=mime,
            size_bytes=size,
            checksum=checksum,
            file_type=extension,
            uploaded_by_id=self.user.id,
            status="received",
            source=source,
            document_type=document_type,
            document_version=1,
            access_level=access_level,
            error_message=error,
        )
        self.session.add(document)
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if "uq_documents_tenant_id_project_id_checksum" in str(exc.orig):
                raise HTTPException(409, "Duplicate document in this project") from None
            raise
        try:
            document.status = "validating"
            await self.session.commit()
            await run_in_threadpool(self.storage.store_original, key, file.file, mime)
        except Exception:
            document.status = "failed"
            document.error_message = (
                "Original storage failed; upload must be retried by an operator"
            )
            await self.session.commit()
            raise HTTPException(
                503, "Original storage unavailable; failed registry entry retained"
            ) from None
        document.status = "quarantined" if error else "stored"
        await self.session.commit()
        if not error:
            document.status = "queued"
            await self.session.commit()
            from app.ingestion.tasks import process_uploaded_file

            try:
                await run_in_threadpool(
                    process_uploaded_file.delay, str(document.id), str(document.tenant_id)
                )
            except Exception:
                # Recovery task republishes queued rows. Never discard stored bytes.
                document.error_message = "Queue unavailable; awaiting automatic retry"
                await self.session.commit()
        return document, (413 if size > MAX_SIZE else 422) if error else 201

    async def delete(self, document_id):
        document = await self.get(document_id, write=True)
        document.deleted_at = datetime.now(UTC)
        await self.session.commit()

    async def download_url(self, document_id):
        document = await self.get(document_id)
        if document.status in {"quarantined", "failed", "received", "validating"}:
            raise HTTPException(409, "Document is not available for download")
        try:
            url = await run_in_threadpool(self.storage.generate_presigned_url, document.storage_key)
        except Exception:
            raise HTTPException(503, "Object storage unavailable") from None
        return {"url": url, "expires_in": 3600}
