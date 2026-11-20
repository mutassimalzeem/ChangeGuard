"""Opt-in HTTP benchmarks against a migrated disposable PostgreSQL/pgvector database."""

import json
import math
import os
from collections import Counter
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from sqlalchemy import event, insert, text

from app.core.config import get_settings
from app.core.database import ScopedAsyncSession, get_session
from app.core.security import create_access_token
from app.domain.models import (
    Approval,
    AuditEvent,
    ChangeOrder,
    Document,
    DocumentChunk,
    DocumentReviewTask,
    EvidenceLink,
    ProjectMembership,
    Risk,
)
from app.main import app
from tests.test_risk_engine import co_doc


async def seed(session, tenant, project, user, size):
    scope = {"tenant_id": tenant.id, "project_id": project.id}
    user.role = "project_manager"
    session.add(ProjectMembership(**scope, user_id=user.id))
    await session.flush()
    docs = [uuid4() for _ in range(size * 2)]
    chunks = [uuid4() for _ in docs]
    now = datetime.now(UTC)
    extraction = co_doc().structured_extraction
    await session.execute(
        insert(Document),
        [
            dict(
                scope,
                id=d,
                filename=f"Daily report {i}.pdf",
                storage_key=f"reports/{i}",
                size_bytes=24000,
                mime_type="application/pdf",
                extraction_confidence=0.65,
                access_level="restricted" if i % 13 == 0 else "project",
                deleted_at=now if i % 37 == 0 else None,
                structured_extraction=extraction,
            )
            for i, d in enumerate(docs)
        ],
    )
    await session.execute(
        insert(DocumentChunk),
        [
            dict(
                scope,
                id=c,
                document_id=d,
                chunk_index=0,
                text="Delivery delayed awaiting inspection.",
                access_level="restricted" if i % 17 == 0 else "project",
            )
            for i, (d, c) in enumerate(zip(docs, chunks, strict=True))
        ],
    )
    risks, tasks, orders, approvals, links, audit = [], [], [], [], [], []
    sample_risk = None
    for i in range(size):
        record = uuid4()
        common = dict(scope, id=record, created_at=now - timedelta(minutes=i // 3))
        if i % 10 < 6:
            risks.append(
                dict(
                    common,
                    title=f"Late delivery {i}",
                    document_id=docs[2 * i],
                    status="open",
                    risk_type="conflicting_information",
                    severity="high" if i % 2 else "critical",
                    confidence=0.85,
                )
            )
            subject = "risk"
            if i == 1:
                sample_risk = record
        elif i % 10 < 8:
            tasks.append(dict(common, document_id=docs[2 * i], reason="low_confidence"))
            continue
        elif i % 10 == 8:
            orders.append(
                dict(
                    common,
                    title=f"Change {i}",
                    reference=f"CO-{i}",
                    status="submitted",
                    currency="USD",
                    amount=20000,
                )
            )
            subject = "change_order"
        else:
            approvals.append(
                dict(common, change_order_id=orders[-1]["id"], due_at=now + timedelta(days=2))
            )
            continue
        for source, source_id in [("document", docs[2 * i]), ("document_chunk", chunks[2 * i + 1])]:
            links.append(
                dict(
                    scope,
                    subject_type=subject,
                    subject_id=record,
                    source_type=source,
                    source_id=source_id,
                    source_page=2,
                    source_text_snippet="Delivery delayed awaiting inspection.",
                )
            )
        audit.append(
            dict(
                scope,
                entity_type=subject,
                entity_id=record,
                actor_id=user.id,
                action="review.add_note",
                details={"reason": "Verify the signed report."},
            )
        )
    for model, rows in [
        (Risk, risks),
        (DocumentReviewTask, tasks),
        (ChangeOrder, orders),
        (Approval, approvals),
        (EvidenceLink, links),
        (AuditEvent, audit),
    ]:
        await session.execute(insert(model), rows)
    for model in (
        Document,
        DocumentChunk,
        Risk,
        ChangeOrder,
        Approval,
        DocumentReviewTask,
        EvidenceLink,
        AuditEvent,
    ):
        await session.execute(text(f"ANALYZE {model.__tablename__}"))
    return sample_risk


@pytest.mark.skipif(
    not os.getenv("REVIEW_BENCHMARK"), reason="Opt-in PostgreSQL performance benchmark"
)
async def test_review_queue_latency(client, test_session, tenant, project, user, monkeypatch):
    size = int(os.getenv("REVIEW_ITEMS", "500"))
    repeats = int(os.getenv("REVIEW_SAMPLES", "20"))
    baseline = os.getenv("REVIEW_BASELINE") == "1"
    risk = await seed(test_session, tenant, project, user, size)
    project_id = project.id
    token = create_access_token(str(user.id), str(tenant.id), [user.role])
    monkeypatch.setattr(get_settings(), "review_high_value_thresholds", {"USD": Decimal("10000")})

    def visible_doc(index):
        return index % 13 != 0 and index % 37 != 0

    def visible_item(index):
        kind = index % 10
        if kind in (6, 7):
            return visible_doc(2 * index)
        # Approval inherits the two sources of its preceding change order.
        subject = index - 1 if kind == 9 else index
        chunk_doc = 2 * subject + 1
        return visible_doc(2 * subject) and visible_doc(chunk_doc) and chunk_doc % 17 != 0

    expected = {
        "first": sum(visible_item(i) for i in range(size)),
        "filtered": sum(visible_item(i) for i in range(size) if i % 10 in (1, 3, 5)),
    }
    connection = await test_session.connection()

    async def fresh_session():
        async with ScopedAsyncSession(
            bind=connection, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as session:
            yield session

    app.dependency_overrides[get_session] = fresh_session
    queries = Counter()
    projection = None

    def count(conn, cursor, statement, params, context, executemany):
        nonlocal projection
        if "WITH access AS MATERIALIZED" in statement:
            projection = (statement, params)
        if not statement.startswith(("SAVEPOINT", "ROLLBACK", "RELEASE")):
            queries[statement.split(" ", 1)[0].strip()] += 1

    prefix = f"/api/v1/projects/{project_id}"
    page = f"{prefix}/review-queue/workspace"
    inspection = f"{prefix}/risks/{risk}" if baseline else f"{page}/risk/{risk}"
    event.listen(connection.sync_connection, "before_cursor_execute", count)
    try:
        for name, path, target in [
            ("first", page, 500),
            ("filtered", page + "?severity=high&min_confidence=0.8&sort=confidence", 750),
            ("inspect", inspection, 750),
        ]:
            timings = []
            counts = []
            for iteration in range(repeats + 1):
                queries.clear()
                start = perf_counter()
                response = await client.get(path, headers={"Authorization": f"Bearer {token}"})
                elapsed = (perf_counter() - start) * 1000
                assert response.status_code == 200, response.text[:500]
                data = response.json()
                if name == "inspect":
                    assert len(data["evidence_details"]) == 2
                else:
                    assert len(data["items"]) == 25 and data["total"] == expected[name]
                if iteration:
                    timings.append(elapsed)
                    counts.append(sum(queries.values()))
            p95 = sorted(timings)[math.ceil(0.95 * repeats) - 1]
            print(
                f"REVIEW_BENCH {size=} {name=} {repeats=} p95_ms={p95:.2f} queries={max(counts)}",
                flush=True,
            )
            if (directory := os.getenv("REVIEW_EXPLAIN_DIR")) and projection:
                statement, parameters = projection
                plan = await connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
                )
                Path(directory, f"review-plan-{size}-{name}.json").write_text(
                    json.dumps(plan.scalar_one(), indent=2), encoding="utf-8"
                )
            if not baseline:
                assert max(counts) <= 2
                if size == 500:
                    assert p95 < target
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", count)
