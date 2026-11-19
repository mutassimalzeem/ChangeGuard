"""Project manager workspace projected from authorized workflow records and audit events."""

from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.core.config import get_settings
from app.domain.models import (
    Approval,
    AuditEvent,
    ChangeOrder,
    Contract,
    DocumentReviewTask,
    ProjectMembership,
    Risk,
    User,
)
from app.domain.schemas.change_order import ChangeOrderDraftFromRisk, DecisionInput
from app.domain.services.audit import record_user_action
from app.domain.services.change_orders import ChangeOrderService
from app.domain.services.review_queue import ReviewQueueService
from app.domain.services.risks import RiskDecision
from app.policy.permissions import TENANT_WIDE_ROLES, Action, has_permission

ENTITIES = {
    "risk": "risk",
    "extraction": "document_review_task",
    "change_order": "change_order",
    "approval": "approval",
}
MODELS = {
    "risk": Risk,
    "extraction": DocumentReviewTask,
    "change_order": ChangeOrder,
    "approval": Approval,
}
RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def review_state(item):
    if item["status"] == "resolved":
        return "resolved"
    if item["kind"] == "risk" and item["change_order_id"]:
        return "converted_to_change_order"
    status = item["status"]
    if status in {"approved", "closed", "rejected", "disputed"}:
        return "resolved"
    if status == "converted":
        return "converted_to_change_order"
    if status in {"accepted", "dismissed", "resolved", "evidence_requested"}:
        return status
    if item["kind"] == "risk" and not item["evidence_supported"]:
        return "insufficient_evidence"
    return "review_required"


def page_items(items, filters):
    def matches(item):
        created = item["created_at"].date()
        confidence = item.get("confidence")
        return (
            (not filters.category or filters.category in item["categories"])
            and (not filters.severity or filters.severity == item.get("severity"))
            and (not filters.owner_id or str(filters.owner_id) == str(item.get("owner_id")))
            and (not filters.created_from or created >= filters.created_from)
            and (not filters.created_to or created <= filters.created_to)
            and (
                filters.min_confidence is None
                or (confidence is not None and confidence >= filters.min_confidence)
            )
            and (
                filters.max_confidence is None
                or (confidence is not None and confidence <= filters.max_confidence)
            )
            and (
                filters.status == "all"
                or filters.status == item["review_state"]
                or (
                    filters.status == "actionable"
                    and item["reviewable"]
                    and item["review_state"] != "accepted"
                )
            )
        )

    visible = sorted(
        (item for item in items if matches(item)), key=lambda item: (item["kind"], str(item["id"]))
    )

    def key(item):
        return (
            RANK.get(item.get("severity")) if filters.sort == "severity" else item.get(filters.sort)
        )

    ranked = sorted(
        (item for item in visible if key(item) is not None),
        key=key,
        reverse=filters.direction == "desc",
    )
    ranked.extend(item for item in visible if key(item) is None)
    start = (filters.page - 1) * filters.page_size
    return {"items": ranked[start : start + filters.page_size], "total": len(visible)}


class ReviewWorkspace(ReviewQueueService):
    def __init__(self, session, user):
        super().__init__(session, user)
        self.orders = ChangeOrderService(session, user)

    async def checked_query(self, name, statement):
        # The scope listener recognizes this exact ORM projection only.
        self.session.info[name] = statement
        try:
            return (await self.session.execute(statement)).all()
        finally:
            self.session.info.pop(name, None)

    async def roster(self, project_id):
        await self.evidence.access.project(project_id)
        members = (
            self.scoped(ProjectMembership, project_id)
            .with_only_columns(ProjectMembership.user_id)
            .where(ProjectMembership.is_active)
        )
        query = (
            select(User.id, User.full_name)
            .where(
                User.tenant_id == self.user.tenant_id,
                User.is_active,
                User.role.in_(["owner", "admin", "commercial_manager", "project_manager"]),
                or_(User.id.in_(members), User.role.in_(TENANT_WIDE_ROLES)),
            )
            .order_by(User.full_name, User.id)
        )
        return [
            dict(row._mapping) for row in await self.checked_query("review_roster_query", query)
        ]

    async def events(self, project_id, items):
        by_entity = defaultdict(list)
        for item in items:
            by_entity[ENTITIES[item["kind"]]].append(item["id"])
            if item["kind"] == "approval" and item["change_order_id"]:
                by_entity["change_order"].append(item["change_order_id"])
        grouped = defaultdict(list)
        for entity, ids in by_entity.items():
            query = (
                select(
                    AuditEvent.entity_id,
                    AuditEvent.action,
                    AuditEvent.actor_id,
                    AuditEvent.created_at,
                    AuditEvent.details,
                )
                .where(
                    AuditEvent.tenant_id == self.user.tenant_id,
                    AuditEvent.project_id == project_id,
                    AuditEvent.entity_type == entity,
                    AuditEvent.entity_id.in_(ids),
                )
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
            for row in await self.checked_query("review_history_query", query):
                grouped[entity, str(row.entity_id)].append(row)
        return grouped

    async def visible_order(self, project_id, order_id):
        order = await self.orders.load(order_id)
        if order.project_id != project_id:
            raise HTTPException(404, "Change order not found")
        if order.rfi_id:
            from app.domain.services.event_links import visible_entity

            await visible_entity(self.session, self.user, project_id, "rfi", order.rfi_id)
        if order.contract_id:
            contract = await self.evidence.record(Contract, project_id, order.contract_id)
            if contract.document_id:
                await self.evidence.source(project_id, "document", contract.document_id)
        return order

    async def commercial_item(self, project_id, row, kind):
        approval = row if kind == "approval" else None
        order_id = approval.change_order_id if approval else row.id
        order = None
        if order_id:
            order = await self.visible_order(project_id, order_id)
            links = await self.orders.links(order)
            evidence = await self.risks.evidence_details(project_id, links)
            title, description = order.title, order.description
        else:
            risk = await self.risks.read(project_id, approval.risk_id)
            evidence, title, description = (
                risk["evidence_details"],
                risk["title"],
                risk["description"],
            )
        return {
            "amount": str(order.amount) if order and order.amount is not None else None,
            "currency": order.currency if order and order.amount is not None else None,
            "kind": kind,
            "id": row.id,
            "title": title,
            "description": description,
            "status": row.status,
            "created_at": row.created_at,
            "confidence": None,
            "severity": None,
            "categories": ["approval_request" if approval else "high_value_change"],
            "risk_type": "approval_request" if approval else "high_value_change",
            "change_order_id": order_id,
            "document_id": next((e["document_id"] for e in evidence if e["document_id"]), None),
            "evidence_details": evidence,
            "evidence_supported": bool(evidence),
            "owner_id": approval.assigned_to_id if approval else None,
            "deadline": approval.due_at if approval else None,
            "reviewable": row.status == "pending"
            if approval
            else row.status in {"potential", "under_review", "drafted", "submitted"},
            "can_decide": bool(
                approval
                and order
                and order.status == "submitted"
                and approval.status == "pending"
                and self.user.id not in {order.created_by_id, order.submitted_by_id}
                and has_permission(self.user.role, Action.APPROVAL_DECIDE)
            ),
            "recommended_action": "Review the approval request."
            if approval
            else "Verify the change and its supporting documents.",
        }

    async def items(self, project_id, kind=None, item_id=None, filters=None):
        await self.evidence.access.project(project_id)
        items = []
        since = (
            datetime.combine(filters.created_from, time.min, UTC)
            if filters and filters.created_from
            else None
        )
        before = (
            datetime.combine(filters.created_to, time.min, UTC) + timedelta(days=1)
            if filters and filters.created_to and filters.created_to.year < 9999
            else None
        )
        if kind in {None, "risk", "extraction"}:
            previous = (
                self.scoped(AuditEvent, project_id)
                .with_only_columns(AuditEvent.entity_id)
                .where(
                    AuditEvent.entity_type == "risk",
                    AuditEvent.action == "risk.override",
                    AuditEvent.details["before"]["severity"].as_string().in_(("high", "critical")),
                )
            )
            if item_id:
                previous = previous.where(AuditEvent.entity_id == item_id)
            previous_high = {
                r[0] for r in await self.checked_query("review_history_query", previous)
            }
            for item in await super().list(
                project_id,
                item_id=item_id,
                previous_high=previous_high,
                kind=kind,
                severity=filters.severity if filters else None,
                actionable=bool(filters and filters.status == "actionable"),
                created_since=since,
                created_before=before,
            ):
                if kind and kind != item["kind"]:
                    continue
                if item["change_order_id"]:
                    try:
                        await self.visible_order(project_id, item["change_order_id"])
                    except HTTPException as exc:
                        if exc.status_code != 404:
                            raise
                        continue
                items.append(item)
        for candidate in ("change_order", "approval"):
            if (kind and kind != candidate) or (filters and filters.severity):
                continue
            model = MODELS[candidate]
            query = self.scoped(model, project_id)
            if filters and filters.status == "actionable":
                statuses = (
                    ("pending",)
                    if candidate == "approval"
                    else ("potential", "under_review", "drafted", "submitted")
                )
                query = query.where(model.status.in_(statuses))
            if since:
                query = query.where(model.created_at >= since)
            if before:
                query = query.where(model.created_at < before)
            if item_id:
                query = query.where(model.id == item_id)
            if candidate == "change_order":
                thresholds = get_settings().review_high_value_thresholds
                if not thresholds:
                    continue
                query = query.where(
                    or_(
                        *[
                            (ChangeOrder.currency == currency) & (ChangeOrder.amount >= threshold)
                            for currency, threshold in thresholds.items()
                        ]
                    )
                )
            for row in await self.session.scalars(query):
                try:
                    items.append(await self.commercial_item(project_id, row, candidate))
                except HTTPException as exc:
                    if exc.status_code != 404:
                        raise
        return items

    async def page(self, project_id, filters):
        kind = {
            "approval_request": "approval",
            "high_value_change": "change_order",
            "low_confidence_extraction": "extraction",
        }.get(filters.category, "risk" if filters.category else None)
        items = await self.items(project_id, kind, filters=filters)
        owners = {}
        if items:
            assignments = (
                self.scoped(AuditEvent, project_id)
                .with_only_columns(
                    AuditEvent.entity_type,
                    AuditEvent.entity_id,
                    AuditEvent.details["owner_id"].as_string(),
                )
                .where(AuditEvent.action == "review.assign_owner")
                .order_by(AuditEvent.created_at, AuditEvent.id)
            )
            owners = {
                (entity, item_id): owner
                for entity, item_id, owner in await self.checked_query(
                    "review_history_query", assignments
                )
            }
        for item in items:
            item["owner_id"] = owners.get(
                (ENTITIES[item["kind"]], item["id"]), item.get("owner_id")
            )
            item["review_state"] = review_state(item)
        page = page_items(items, filters)
        history = await self.events(project_id, page["items"])
        for item in page["items"]:
            events = history[ENTITIES[item["kind"]], str(item["id"])]
            if item["kind"] == "approval" and item["change_order_id"]:
                decisions = [
                    e
                    for e in history["change_order", str(item["change_order_id"])]
                    if e.details.get("approval_id") == str(item["id"])
                ]
                events = sorted([*events, *decisions], key=lambda e: e.created_at)
            item["history"] = [
                {
                    "action": e.action,
                    "actor_id": e.actor_id,
                    "at": e.created_at,
                    "reason": e.details.get("reason"),
                    "owner_id": e.details.get("owner_id"),
                }
                for e in events
                if e.action != "review.command"
            ]
        return page

    async def command(self, project_id, kind, item_id, payload, request_id):
        await self.evidence.access.project(project_id)
        model = MODELS[kind]
        if kind == "approval" and payload.action in {"approve", "reject"}:
            # Match submission, dispute and approval lock order.
            order_id = await self.session.scalar(
                self.scoped(Approval, project_id)
                .with_only_columns(Approval.change_order_id)
                .where(Approval.id == item_id)
            )
            if order_id:
                await self.orders.load(order_id, lock=True)
        row = await self.session.scalar(
            self.scoped(model, project_id)
            .where(model.id == item_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise HTTPException(404, "Review item not found")
        items = await self.items(project_id, kind, item_id)
        if not items:
            raise HTTPException(404, "Review item not found")
        item = items[0]
        entity = ENTITIES[kind]
        events = (await self.events(project_id, items))[entity, str(item_id)]
        args = payload.model_dump(mode="json")
        for event in events:
            if event.actor_id == self.user.id and event.details.get("key") == str(payload.key):
                if any(event.details.get(k) != v for k, v in args.items()):
                    raise HTTPException(409, "This command key was used with different inputs")
                return {"change_order_id": event.details.get("change_order_id")}
        if not item["reviewable"]:
            raise HTTPException(409, "This review item is closed")
        action = payload.action
        if (
            (action == "accept" and item["status"] == "accepted")
            or (action == "request_evidence" and item["status"] == "evidence_requested")
            or (action == "override" and item.get("severity") == payload.severity)
        ):
            raise HTTPException(409, "This review already has the requested state")
        order_id = None
        audit_action = "review.command"
        if action == "assign_owner":
            if payload.owner_id not in {u["id"] for u in await self.roster(project_id)}:
                raise HTTPException(422, "Select an active reviewer for this project")
            audit_action = "review.assign_owner"
        elif action == "add_note":
            audit_action = "review.add_note"
        elif kind == "risk" and action == "convert_to_change_order":
            order = await self.orders.create_draft_from_risk(
                project_id, item_id, ChangeOrderDraftFromRisk(reason=payload.reason), request_id
            )
            order_id = str(order["id"])
        elif kind == "risk" and action in {"accept", "override", "dismiss", "request_evidence"}:
            await self.risks.decide(
                project_id,
                item_id,
                RiskDecision(action=action, reason=payload.reason, severity=payload.severity),
                request_id,
            )
        elif kind == "extraction" and action in {"dismiss", "request_evidence"}:
            await self.decide_extraction(project_id, item_id, action, payload.reason, request_id)
        elif kind == "approval" and action in {"approve", "reject"} and item["change_order_id"]:
            if not item["can_decide"]:
                raise HTTPException(403, "Approval requires an independent authorized reviewer")
            await self.orders.decide(
                item["change_order_id"],
                "approved" if action == "approve" else "rejected",
                DecisionInput(reason=payload.reason),
                request_id,
                approval_id=item_id,
            )
        else:
            raise HTTPException(409, "Action unavailable for this review item")
        await record_user_action(
            self.session,
            self.user,
            project_id,
            audit_action,
            entity,
            item_id,
            request_id,
            {**args, "change_order_id": order_id},
        )
        return {"change_order_id": order_id}
