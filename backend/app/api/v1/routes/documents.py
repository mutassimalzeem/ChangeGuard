"""Document upload, registry and retained-original access."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user
from app.core.database import get_session
from app.domain.models import User
from app.domain.schemas.document import DocumentRead
from app.domain.services.document_service import DocumentService
from app.domain.services.object_storage import get_object_storage_service

router = APIRouter(tags=["documents"])


def get_document_service(
    session: AsyncSession = Depends(get_session),
    user: User = Depends(require_authenticated_user),
    storage=Depends(get_object_storage_service),
):
    return DocumentService(session, user, storage)


@router.post(
    "/projects/{project_id}/documents",
    response_model=DocumentRead,
    status_code=201,
    responses={
        409: {"description": "Duplicate document"},
        413: {"model": DocumentRead},
        422: {"description": "Quarantined document or invalid request"},
    },
)
async def upload_document(
    project_id: UUID,
    response: Response,
    file: UploadFile = File(...),
    source: str = Form("upload", min_length=1, max_length=64),
    document_type: str | None = Form(None, max_length=100),
    access_level: Literal["project", "restricted"] = Form("project"),
    service: DocumentService = Depends(get_document_service),
):
    document, response.status_code = await service.upload(
        project_id, file, source, document_type, access_level
    )
    return DocumentRead.model_validate(document)


@router.get("/projects/{project_id}/documents", response_model=list[DocumentRead])
async def list_documents(
    project_id: UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    service=Depends(get_document_service),
):
    return [
        DocumentRead.model_validate(row) for row in await service.list(project_id, offset, limit)
    ]


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, service=Depends(get_document_service)):
    return DocumentRead.model_validate(await service.get(document_id))


@router.get("/documents/{document_id}/download-url")
async def download_url(document_id: UUID, service=Depends(get_document_service)):
    return await service.download_url(document_id)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: UUID, service=Depends(get_document_service)):
    await service.delete(document_id)
