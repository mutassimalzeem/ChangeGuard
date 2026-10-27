"""Pagination utilities for API responses."""

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field
from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class PageParams(BaseModel):
    """Pagination request parameters."""
    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(default=20, ge=1, le=100, description="Items per page")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


class PageMetadata(BaseModel):
    """Pagination metadata."""
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_previous: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    items: list[T]
    metadata: PageMetadata

    @classmethod
    def create(
        cls,
        items: list[T],
        total_items: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        total_pages = (total_items + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            metadata=PageMetadata(
                page=page,
                page_size=page_size,
                total_items=total_items,
                total_pages=total_pages,
                has_next=page < total_pages,
                has_previous=page > 1,
            ),
        )


async def paginate_query(
    session: AsyncSession,
    query: Select,
    page_params: PageParams,
) -> tuple[list[Any], int]:
    """Execute paginated query and return items with total count."""
    from sqlalchemy import func, select

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = await session.scalar(count_query) or 0

    # Get paginated items
    paginated_query = query.offset(page_params.offset).limit(page_params.limit)
    result = await session.execute(paginated_query)
    items = result.scalars().all()

    return list(items), total