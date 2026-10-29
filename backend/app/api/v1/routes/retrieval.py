"""Authenticated hybrid chunk search."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_authenticated_user
from app.core.config import get_settings
from app.core.database import get_session
from app.domain.models import User
from app.retrieval.adapters import KeywordCoverageReranker, ProcessingEmbedder
from app.retrieval.schemas import SearchRequest, SearchResponse
from app.retrieval.service import HybridRetrieval

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def get_query_embedder():
    settings = get_settings()
    if settings.llm_provider == "openai" and settings.llm_api_key:
        return ProcessingEmbedder()
    return None


def get_retrieval(
    user: Annotated[User, Depends(require_authenticated_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    embedder: Annotated[object, Depends(get_query_embedder)],
):
    return HybridRetrieval(
        session,
        user,
        embedder=embedder,
        reranker=KeywordCoverageReranker(),
        min_similarity=get_settings().min_similarity_threshold,
    )


@router.post("/search", response_model=SearchResponse)
async def search_chunks(
    payload: SearchRequest, retrieval: Annotated[HybridRetrieval, Depends(get_retrieval)]
):
    return await retrieval.search(payload)
