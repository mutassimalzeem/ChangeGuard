"""Real PostgreSQL FTS/vector retrieval, metadata and adversarial scope tests."""

# Fixture injection and literal HTTP status assertions keep integration cases readable.
# ruff: noqa: PLR0913, PLR2004
from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text

from app.api.dependencies import get_current_user
from app.api.exceptions import NotFoundError
from app.api.v1.routes.retrieval import get_query_embedder
from app.domain.models import Document, DocumentChunk, Project, ProjectMembership, Tenant
from app.main import app
from app.retrieval.adapters import (
    DIMENSIONS,
    EmbeddingUnavailableError,
    KeywordCoverageReranker,
    ProcessingEmbedder,
    validate_embedding,
)
from app.retrieval.schemas import SearchFilters, SearchRequest
from app.retrieval.service import HybridRetrieval


def vector(axis=0):
    result = [0.0] * DIMENSIONS
    result[axis] = 1.0
    return result


class FixtureEmbedder:
    """Fixed vectors isolate PostgreSQL ranking from live provider variability."""

    model = "fixture-embedding-v1"

    def __init__(self):
        self.queries = []

    async def embed(self, query):
        self.queries.append(query)
        return vector()


class RecordingReranker:
    def __init__(self):
        self.texts = ()

    async def scores(self, query, texts):
        self.texts = texts
        return [1.0 if "postponed" in value else 0.0 for value in texts]


@pytest.fixture
async def corpus(test_session, tenant, project, user):
    test_session.add(ProjectMembership(tenant_id=tenant.id, project_id=project.id, user_id=user.id))
    foreign = Tenant(name="Foreign", slug=f"foreign-{uuid4().hex}")
    test_session.add(foreign)
    await test_session.flush()
    foreign_project = Project(tenant_id=foreign.id, code="FOREIGN", name="Foreign")
    unassigned = Project(tenant_id=tenant.id, code="UNASSIGNED", name="Unassigned")
    test_session.add_all([foreign_project, unassigned])
    await test_session.flush()
    ids = {
        "tenant": tenant.id,
        "project": project.id,
        "foreign_tenant": foreign.id,
        "foreign_project": foreign_project.id,
        "unassigned": unassigned.id,
    }

    async def add(
        name,
        content,
        *,
        target=project,
        access="project",
        chunk_access="project",
        embedding=None,
        model=FixtureEmbedder.model,
        doc_type="drawing",
        status="indexed",
        revision="B",
        chunk_date=date(2026, 10, 20),
        deleted=False,
    ):
        document = Document(
            tenant_id=target.tenant_id,
            project_id=target.id,
            filename=name + ".pdf",
            storage_key=name,
            mime_type="application/pdf",
            size_bytes=1,
            document_type=doc_type,
            status=status,
            access_level=access,
            deleted_at=datetime.now(UTC) if deleted else None,
        )
        test_session.add(document)
        await test_session.flush()
        chunk = DocumentChunk(
            tenant_id=target.tenant_id,
            project_id=target.id,
            document_id=document.id,
            chunk_index=0,
            text=content,
            page_number=3,
            access_level=chunk_access,
            embedding=embedding,
            embedding_model=model,
            revision=revision,
            date=chunk_date,
            section="Construction",
        )
        test_session.add(chunk)
        await test_session.flush()
        ids[name] = chunk.id
        ids[name + "_document"] = document.id

    await add("drawing", "Drawing DRG-STR-001 specifies reinforced concrete foundations.")
    await add("near_drawing", "Drawing DRG-STR-001A supersedes the preliminary layout.")
    await add(
        "boq", "BOQ code CW.03.007 covers excavation and disposal.", doc_type="boq", revision="C"
    )
    await add(
        "delay",
        "Late delivery of steel postponed completion by fourteen days.",
        embedding=vector(),
        doc_type="daily_report",
    )
    await add("irrelevant", "The office paint colour is blue.", embedding=vector(1))
    await add(
        "old_model",
        "Programme slippage due to a road closure.",
        embedding=vector(),
        model="different-embedding-model",
    )
    await add(
        "restricted",
        "SECRET programme slippage DRG-STR-001",
        access="restricted",
        embedding=vector(),
    )
    await add(
        "restricted_chunk",
        "SECRET programme slippage DRG-STR-001",
        chunk_access="restricted",
        embedding=vector(),
    )
    await add(
        "foreign",
        "FOREIGN programme slippage DRG-STR-001",
        target=foreign_project,
        embedding=vector(),
    )
    await add(
        "unassigned_doc",
        "UNASSIGNED programme slippage DRG-STR-001",
        target=unassigned,
        embedding=vector(),
    )
    await add("deleted", "DELETED programme slippage DRG-STR-001", deleted=True, embedding=vector())
    await add(
        "quarantined",
        "QUARANTINED programme slippage DRG-STR-001",
        status="quarantined",
        embedding=vector(),
    )
    return ids


async def test_exact_drawing_number(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(query="DRG-STR-001", semantic=False)
    )
    assert result.results[0].chunk_id == corpus["drawing"]
    assert result.results[0].page_number == 3
    assert result.results[0].document_id == corpus["drawing_document"]
    assert result.results[0].source_metadata.revision == "B"
    assert result.semantic_status == "disabled"


async def test_exact_boq_code(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(query="CW.03.007", semantic=False)
    )
    assert [hit.chunk_id for hit in result.results] == [corpus["boq"]]
    assert result.results[0].source_metadata.document_type == "boq"


async def test_semantic_delay_without_shared_keywords(test_session, user, corpus):
    embedder = FixtureEmbedder()
    result = await HybridRetrieval(test_session, user, embedder=embedder).search(
        SearchRequest(query="schedule overrun")
    )
    assert result.status == "matched" and result.semantic_status == "used"
    assert [hit.chunk_id for hit in result.results] == [corpus["delay"]]
    assert result.results[0].keyword_score is None
    assert result.results[0].vector_similarity == pytest.approx(1)
    assert embedder.queries == ["schedule overrun"]


async def test_fusion_deduplicates_and_rewards_both_channels(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="steel")
    )
    assert result.results[0].chunk_id == corpus["delay"]
    assert len({hit.chunk_id for hit in result.results}) == len(result.results)
    assert result.results[0].keyword_score > 0
    assert result.results[0].fusion_score == pytest.approx(2 / 61)


@pytest.mark.parametrize(
    "filters,expected",
    [
        ({"document_type": "boq"}, ["boq"]),
        ({"revision": "C"}, ["boq"]),
        ({"date_from": "2026-10-20", "date_to": "2026-10-20"}, ["boq"]),
        ({"date_from": "2026-10-21"}, []),
        ({"date_to": "2026-10-19"}, []),
        ({"status": "classified"}, []),
        ({"status": "indexed", "access_level": "project"}, ["boq"]),
        ({"access_level": "restricted"}, []),
    ],
)
async def test_metadata_filters(test_session, user, corpus, filters, expected):
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(query="CW.03.007", semantic=False, filters=SearchFilters(**filters))
    )
    assert [hit.chunk_id for hit in result.results] == [corpus[name] for name in expected]
    if not expected:
        assert result.status == "insufficient_evidence"


async def test_matching_tenant_and_project_filters(test_session, user, corpus):
    request = SearchRequest(
        query="CW.03.007",
        semantic=False,
        filters=SearchFilters(tenant_id=corpus["tenant"], project_id=corpus["project"]),
    )
    result = await HybridRetrieval(test_session, user).search(request)
    assert [hit.chunk_id for hit in result.results] == [corpus["boq"]]


async def test_permission_filtered_before_both_candidate_limits_and_reranking(
    test_session, user, corpus
):
    # More inaccessible high-ranked rows than either candidate budget. Filtering
    # after LIMIT would discard the valid lower-ranked semantic match.
    delay = await test_session.get(DocumentChunk, corpus["delay"])
    delay.embedding = [0.8, 0.6] + [0.0] * (DIMENSIONS - 2)
    test_session.add_all(
        [
            DocumentChunk(
                tenant_id=corpus["tenant"],
                project_id=corpus["project"],
                document_id=corpus["restricted_document"],
                chunk_index=index,
                text="SECRET programme slippage " * 20,
                access_level="project",
                embedding=vector(),
                embedding_model=FixtureEmbedder.model,
            )
            for index in range(1, 61)
        ]
    )
    await test_session.flush()
    reranker = RecordingReranker()
    result = await HybridRetrieval(
        test_session, user, embedder=FixtureEmbedder(), reranker=reranker
    ).search(SearchRequest(query="programme slippage", rerank=True, limit=1))
    assert result.results[0].chunk_id == corpus["delay"]
    assert result.reranked
    assert all(
        not any(
            word in value for word in ["SECRET", "FOREIGN", "UNASSIGNED", "DELETED", "QUARANTINED"]
        )
        for value in reranker.texts
    )


async def test_cross_tenant_cannot_be_requested(test_session, user, corpus):
    embedder = FixtureEmbedder()
    with pytest.raises(HTTPException) as failure:
        await HybridRetrieval(test_session, user, embedder=embedder).search(
            SearchRequest(query="steel", filters=SearchFilters(tenant_id=corpus["foreign_tenant"]))
        )
    assert failure.value.status_code == 403
    assert not embedder.queries


@pytest.mark.parametrize("project_key", ["foreign_project", "unassigned"])
async def test_inaccessible_project_rejected_before_embedding(
    test_session, user, corpus, project_key
):
    embedder = FixtureEmbedder()
    with pytest.raises(NotFoundError) as failure:
        await HybridRetrieval(test_session, user, embedder=embedder).search(
            SearchRequest(query="steel", filters=SearchFilters(project_id=corpus[project_key]))
        )
    assert failure.value.status_code == 404
    assert not embedder.queries


async def test_no_relevant_evidence_is_explicit(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(query="nonexistent ZX-999-888", semantic=False)
    )
    assert result.status == "insufficient_evidence"
    assert result.results == []


async def test_low_similarity_and_wrong_model_are_not_returned(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="schedule overrun")
    )
    ids = {hit.chunk_id for hit in result.results}
    assert corpus["irrelevant"] not in ids and corpus["old_model"] not in ids
    assert all(hit.source_metadata.tenant_id == corpus["tenant"] for hit in result.results)


async def test_missing_embedder_reports_keyword_fallback(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user).search(SearchRequest(query="CW.03.007"))
    assert result.semantic_status == "unavailable"
    assert result.results[0].chunk_id == corpus["boq"]


async def test_embedder_outage_does_not_hide_lexical_results(test_session, user, corpus):
    class Down(FixtureEmbedder):
        async def embed(self, query):
            raise EmbeddingUnavailableError

    result = await HybridRetrieval(test_session, user, embedder=Down()).search(
        SearchRequest(query="CW.03.007")
    )
    assert result.semantic_status == "unavailable"
    assert result.results[0].chunk_id == corpus["boq"]


async def test_api_authenticated_search(client, user, corpus):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_query_embedder] = FixtureEmbedder
    result = await client.post("/api/v1/retrieval/search", json={"query": "schedule overrun"})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["status"] == "matched" and body["semantic_status"] == "used"
    assert body["results"][0]["chunk_id"] == str(corpus["delay"])
    assert body["results"][0]["source_metadata"]["tenant_id"] == str(corpus["tenant"])
    assert "embedding" not in body["results"][0]


async def test_api_requires_auth(client):
    assert (
        await client.post("/api/v1/retrieval/search", json={"query": "delay"})
    ).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"query": " "},
        {"query": "***"},
        {"query": "x", "limit": 101},
        {"query": "x", "filters": {"date_from": "2026-10-29", "date_to": "2026-10-20"}},
        {"query": "x", "filters": {"access_level": "all"}},
        {"query": "x", "vector": [1]},
    ],
)
def test_invalid_requests_rejected(payload):
    with pytest.raises(ValidationError):
        SearchRequest(**payload)


@pytest.mark.parametrize(
    "embedding", [[1], [0.0] * DIMENSIONS, [float("nan")] * DIMENSIONS, [float("inf")] * DIMENSIONS]
)
def test_invalid_embeddings_rejected(embedding):
    with pytest.raises(ValueError):
        validate_embedding(embedding)


async def test_local_reranker():
    scores = await KeywordCoverageReranker().scores(
        "steel delay", ("Paint is blue", "Steel delivery delay")
    )
    assert scores == [0, 1]


async def test_processing_embedder_reuses_ingestion_provider(monkeypatch):
    embedder = ProcessingEmbedder()
    calls = []

    def embed(texts):
        calls.append(texts)
        return [vector()]

    monkeypatch.setattr(embedder.services, "embed", embed)
    assert await embedder.embed("delay") == vector()
    assert calls == [["delay"]]


async def test_identifier_index_exists(test_engine):
    async with test_engine.connect() as connection:
        definition = await connection.scalar(
            text("SELECT indexdef FROM pg_indexes WHERE indexname='ix_document_chunks_identifiers'")
        )
        assert "to_tsvector('simple'::regconfig, text)" in definition


@pytest.mark.parametrize(
    "filters",
    [
        {"document_type": "drawing"},
        {"revision": "C"},
        {"date_from": "2026-10-21"},
        {"date_to": "2026-10-19"},
        {"status": "classified"},
        {"access_level": "restricted"},
    ],
)
async def test_vector_branch_applies_metadata(test_session, user, corpus, filters):
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="schedule overrun", filters=SearchFilters(**filters))
    )
    assert result.semantic_status == "used"
    assert result.status == "insufficient_evidence" and result.results == []


async def test_both_branches_apply_combined_filters(test_session, user, corpus):
    filters = SearchFilters(
        tenant_id=corpus["tenant"],
        project_id=corpus["project"],
        document_type="daily_report",
        revision="B",
        date_from=date(2026, 10, 20),
        date_to=date(2026, 10, 20),
        status="indexed",
        access_level="project",
    )
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="steel", filters=filters)
    )
    assert [hit.chunk_id for hit in result.results] == [corpus["delay"]]
    assert result.results[0].fusion_score == pytest.approx(2 / 61)


async def test_owner_still_cannot_retrieve_other_tenant(test_session, user, corpus):
    user.role = "owner"
    await test_session.flush()
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="programme slippage")
    )
    ids = {hit.chunk_id for hit in result.results}
    assert corpus["restricted"] in ids
    assert corpus["unassigned_doc"] in ids
    assert corpus["foreign"] not in ids
    assert all(hit.source_metadata.tenant_id == corpus["tenant"] for hit in result.results)


async def test_uploader_can_retrieve_own_restricted_source(test_session, user, corpus):
    doc = await test_session.get(Document, corpus["restricted_chunk_document"])
    doc.uploaded_by_id = user.id
    doc.access_level = "restricted"
    await test_session.flush()
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(
            query="DRG-STR-001", semantic=False, filters=SearchFilters(access_level="restricted")
        )
    )
    assert [hit.chunk_id for hit in result.results] == [corpus["restricted_chunk"]]
    assert result.results[0].source_metadata.access_level == "restricted"


async def test_inactive_membership_cannot_search(test_session, user, corpus):
    membership = await test_session.scalar(
        select(ProjectMembership).where(ProjectMembership.user_id == user.id)
    )
    membership.is_active = False
    await test_session.flush()
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="programme slippage")
    )
    assert result.status == "insufficient_evidence" and result.results == []


@pytest.mark.parametrize("scores", [[float("nan")], [], [float("inf")]])
async def test_invalid_reranker_response_is_rejected(test_session, user, corpus, scores):
    class BadReranker:
        async def scores(self, query, texts):
            return scores

    with pytest.raises(HTTPException) as failure:
        await HybridRetrieval(test_session, user, reranker=BadReranker()).search(
            SearchRequest(query="CW.03.007", semantic=False, rerank=True)
        )
    assert failure.value.status_code == 503


async def test_api_optional_local_reranker(client, user, corpus):
    app.dependency_overrides[get_current_user] = lambda: user
    result = await client.post(
        "/api/v1/retrieval/search", json={"query": "steel", "semantic": False, "rerank": True}
    )
    assert result.status_code == 200
    assert result.json()["reranked"] is True
    assert result.json()["results"][0]["chunk_id"] == str(corpus["delay"])


async def test_fts_english_stemming(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(query="foundation", semantic=False)
    )
    assert [hit.chunk_id for hit in result.results] == [corpus["drawing"]]


async def test_query_syntax_is_plain_text_not_sql(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user).search(
        SearchRequest(query="'; DROP TABLE documents; --", semantic=False)
    )
    assert result.status == "insufficient_evidence"
    assert result.results == []


async def test_semantic_no_match_is_explicit(test_session, user, corpus):
    class Unrelated(FixtureEmbedder):
        async def embed(self, query):
            return vector(2)

    result = await HybridRetrieval(test_session, user, embedder=Unrelated()).search(
        SearchRequest(query="unrelated zoning issue")
    )
    assert result.semantic_status == "used"
    assert result.status == "insufficient_evidence" and result.results == []


async def test_exact_identifier_beats_semantic_only_match(test_session, user, corpus):
    result = await HybridRetrieval(test_session, user, embedder=FixtureEmbedder()).search(
        SearchRequest(query="DRG-STR-001")
    )
    assert result.results[0].chunk_id == corpus["drawing"]
    assert result.results[0].exact_identifier_match
    assert result.results[0].score > result.results[0].fusion_score


@pytest.mark.parametrize(
    "response", [None, [], [[1]], [[0.0] * DIMENSIONS], [[float("nan")] * DIMENSIONS]]
)
async def test_malformed_provider_embeddings_are_unavailable(monkeypatch, response):
    embedder = ProcessingEmbedder()
    monkeypatch.setattr(embedder.services, "embed", lambda texts: response)
    with pytest.raises(EmbeddingUnavailableError):
        await embedder.embed("schedule")


async def test_api_rejects_foreign_tenant_filter(client, user, corpus):
    app.dependency_overrides[get_current_user] = lambda: user
    result = await client.post(
        "/api/v1/retrieval/search",
        json={"query": "steel", "filters": {"tenant_id": str(corpus["foreign_tenant"])}},
    )
    assert result.status_code == 403
