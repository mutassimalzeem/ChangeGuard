"""Project management endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user, require_permission, require_project_access
from app.api.pagination import PageParams
from app.core.database import get_session
from app.domain.models import Project, User
from app.domain.schemas.project import (
    PaginatedProjectResponse,
    ProjectCreate,
    ProjectListParams,
    ProjectRead,
    ProjectUpdate,
)
from app.domain.services import ProjectService


router = APIRouter(prefix="/projects", tags=["projects"])


def get_project_service(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> ProjectService:
    return ProjectService(session, request)


@router.post(
    "",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("project.create"))],
)
async def create_project(
    payload: ProjectCreate,
    user: User = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    """Create a new project."""
    try:
        return await service.create_project(payload, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get(
    "",
    response_model=PaginatedProjectResponse,
    dependencies=[Depends(require_permission("project.read"))],
)
async def list_projects(
    params: ProjectListParams = Depends(),
    page_params: PageParams = Depends(),
    user: User = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> PaginatedProjectResponse:
    """List projects with pagination, filtering, and search."""
    return await service.list_projects(params, user)


@router.get(
    "/{project_id}",
    response_model=ProjectRead,
    dependencies=[Depends(require_permission("project.read"))],
)
async def get_project(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    """Get a single project by ID."""
    try:
        return await service.get_project(project_id, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch(
    "/{project_id}",
    response_model=ProjectRead,
    dependencies=[Depends(require_permission("project.update"))],
)
async def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    user: User = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    """Update a project."""
    try:
        return await service.update_project(project_id, payload, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST if "Invalid" in str(e) else status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("project.delete"))],
)
async def delete_project(
    project_id: UUID,
    user: User = Depends(require_authenticated_user),
    service: ProjectService = Depends(get_project_service),
) -> None:
    """Delete a project."""
    try:
        await service.delete_project(project_id, user)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))