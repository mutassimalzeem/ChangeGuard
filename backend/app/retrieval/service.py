"""Permission-first PostgreSQL FTS + exact pgvector search with reciprocal rank fusion."""

import math
import re

from fastapi import HTTPException
from sqlalchemy import and_, case, false, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.gateway.context import model_scope
from app.domain.models import Document, DocumentChunk, User
from app.domain.services.project_access import ProjectAccessService
from app.policy.permissions import TENANT_WIDE_ROLES, Action, has_permission
from app.retrieval.adapters import (
    EmbeddingUnavailableError,
    QueryEmbedder,
    Reranker,
    validate_embedding,
)
from app.retrieval.schemas import (
    SearchFilters,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceMetadata,
)

RRF_CONSTANT = 60
MIN_SIMILARITY = 0.65


class HybridRetrieval:
    def __init__(
        self,
        session: AsyncSession,
        user: User,
        *,
        embedder: QueryEmbedder | None = None,
        reranker: Reranker | None = None,
        min_similarity: float = MIN_SIMILARITY,
    ):
        if not math.isfinite(min_similarity) or not 0 <= min_similarity <= 1:
            raise ValueError("Invalid semantic similarity threshold")  # noqa: TRY003
        self.session, self.user = session, user
        self.access = ProjectAccessService(session, user)
        self.embedder, self.reranker = embedder, reranker
        self.min_similarity = min_similarity

    def eligible(self, filters: SearchFilters):
        """All permission and metadata predicates belong in BOTH candidate queries."""
        chunk, document = DocumentChunk, Document
        effective_access = case(
            (
                or_(chunk.access_level == "restricted", document.access_level == "restricted"),
                "restricted",
            ),
            else_="project",
        )
        query = (
            select(
                chunk.id.label("chunk_id"),
                chunk.text,
                chunk.document_id,
                chunk.page_number,
                chunk.tenant_id,
                chunk.project_id,
                document.filename,
                document.document_type,
                chunk.date,
                document.status,
                effective_access.label("access_level"),
                document.access_level.label("document_access_level"),
                chunk.access_level.label("chunk_access_level"),
                chunk.revision,
                chunk.section,
                chunk.author,
                chunk.language,
                chunk.embedding_model,
                chunk.chunk_hash,
            )
            .join(
                document,
                and_(
                    chunk.document_id == document.id,
                    chunk.tenant_id == document.tenant_id,
                    chunk.project_id == document.project_id,
                ),
            )
            .where(
                chunk.tenant_id == self.user.tenant_id,
                document.tenant_id == self.user.tenant_id,
                document.deleted_at.is_(None),
                document.status.not_in(["failed", "quarantined"]),
            )
        )
        if self.access.principal.role not in TENANT_WIDE_ROLES:
            query = query.where(
                or_(document.access_level == "project", document.uploaded_by_id == self.user.id),
                or_(chunk.access_level == "project", document.uploaded_by_id == self.user.id),
            )
        for field, column in [
            ("project_id", chunk.project_id),
            ("document_type", document.document_type),
            ("status", document.status),
            ("access_level", effective_access),
            ("revision", chunk.revision),
        ]:
            value = getattr(filters, field)
            if value is not None:
                query = query.where(column == value)
        if filters.date_from is not None:
            query = query.where(chunk.date >= filters.date_from)
        if filters.date_to is not None:
            query = query.where(chunk.date <= filters.date_to)
        return query

    async def keywords(self, base, query, count):
        simple = func.to_tsvector("simple", DocumentChunk.text)
        english = func.to_tsvector("english", DocumentChunk.text)
        simple_query, english_query = (
            func.plainto_tsquery("simple", query),
            func.plainto_tsquery("english", query),
        )
        match = or_(simple.op("@@")(simple_query), english.op("@@")(english_query))
        rank = func.greatest(
            func.ts_rank_cd(simple, simple_query), func.ts_rank_cd(english, english_query)
        )
        literal = false()
        # Literal identifiers retain punctuation and exact token boundaries. They
        # are still searched through FTS, with a bound regex rescuing parser splits.
        if re.fullmatch(r"[\w./-]+", query) and any(c.isdigit() for c in query):
            literal = DocumentChunk.text.op("~*")(
                "(^|[^[:alnum:]_])" + re.escape(query) + "([^[:alnum:]_]|$)"
            )
            match = or_(match, literal)
            rank = rank + case((literal, 1.0), else_=0.0)
        result = await self.session.execute(
            base.add_columns(rank.label("keyword_score"), literal.label("exact_identifier_match"))
            .where(match)
            .order_by(rank.desc(), DocumentChunk.id)
            .limit(count)
        )
        return list(result.mappings())

    async def vectors(self, base, query, count, project_id=None):
        with model_scope(self.user.tenant_id, project_id):
            vector = validate_embedding(await self.embedder.embed(query))
        distance = DocumentChunk.embedding.cosine_distance(vector)
        result = await self.session.execute(
            base.add_columns((1 - distance).label("vector_similarity"))
            .where(
                DocumentChunk.embedding.is_not(None),
                DocumentChunk.embedding_model == self.embedder.model,
                distance <= 1 - self.min_similarity,
            )
            # +0 deliberately uses exact search, so permission/metadata filters
            # cannot underfill results through an approximate index's candidate cap.
            .order_by(distance + 0, DocumentChunk.id)
            .limit(count)
        )
        return list(result.mappings())

    @staticmethod
    def fuse(keyword_rows, vector_rows):
        hits = {}
        for rows, metric in [(keyword_rows, "keyword_score"), (vector_rows, "vector_similarity")]:
            for rank, row in enumerate(rows, 1):
                key = row["chunk_id"]
                if key not in hits:
                    hits[key] = SearchHit(
                        chunk_id=key,
                        text=row["text"],
                        document_id=row["document_id"],
                        page_number=row["page_number"],
                        score=0,
                        fusion_score=0,
                        source_metadata=SourceMetadata.model_validate(dict(row)),
                    )
                hit = hits[key]
                hit.fusion_score += 1 / (RRF_CONSTANT + rank)
                setattr(hit, metric, float(row[metric]))
                if metric == "keyword_score":
                    hit.exact_identifier_match = bool(row["exact_identifier_match"])
        for hit in hits.values():
            # An exact construction identifier must beat a semantic-only rank tie.
            hit.score = hit.fusion_score + (
                1 / (RRF_CONSTANT + 1) if hit.exact_identifier_match else 0
            )
        return sorted(hits.values(), key=lambda hit: (-hit.score, str(hit.chunk_id)))

    async def search(self, request: SearchRequest) -> SearchResponse:
        if not has_permission(self.user.role, Action.DOCUMENT_READ):
            raise HTTPException(403, "Access denied")
        if request.filters.tenant_id not in (None, self.user.tenant_id):
            raise HTTPException(403, "Tenant filter does not match authenticated tenant")
        if request.filters.project_id is not None:
            await self.access.project(request.filters.project_id)
        if request.rerank and self.reranker is None:
            raise HTTPException(503, "Reranker is unavailable")
        base = self.eligible(request.filters)
        count = max(50, request.limit * 4)
        keywords = await self.keywords(base, request.query, count)
        vectors, semantic_status = [], "disabled"
        if request.semantic:
            semantic_status = "unavailable"
            if self.embedder is not None:
                try:
                    vectors = await self.vectors(base, request.query, count, request.filters.project_id)
                    semantic_status = "used"
                except EmbeddingUnavailableError:
                    pass
        hits = self.fuse(keywords, vectors)
        reranked = False
        if request.rerank and hits:
            scores = await self.reranker.scores(request.query, tuple(hit.text for hit in hits))
            if len(scores) != len(hits) or not all(math.isfinite(score) for score in scores):
                raise HTTPException(503, "Invalid reranker response")
            for hit, score in zip(hits, scores, strict=True):
                hit.score = float(score)
            hits.sort(key=lambda hit: (-hit.score, -hit.fusion_score, str(hit.chunk_id)))
            reranked = True
        return SearchResponse(
            status="matched" if hits else "insufficient_evidence",
            results=hits[: request.limit],
            semantic_status=semantic_status,
            reranked=reranked,
        )
