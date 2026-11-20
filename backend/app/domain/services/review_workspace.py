"""Project manager workspace projected from authorized workflow records and audit events."""

from fastapi import HTTPException
from sqlalchemy import or_, select

from app.domain.models import (
    Approval,
    AuditEvent,
    ChangeOrder,
    DocumentReviewTask,
    ProjectMembership,
    Risk,
    User,
)
from app.domain.schemas.change_order import ChangeOrderDraftFromRisk, DecisionInput
from app.domain.schemas.review_workspace import QueueFilters
from app.domain.services.audit import record_user_action
from app.domain.services.change_orders import ChangeOrderService
from app.domain.services.review_queue import ReviewQueueService
from app.domain.services.review_read import read_review_page
from app.domain.services.risks import RiskDecision
from app.policy.permissions import TENANT_WIDE_ROLES

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

    async def page(self, project_id, filters, *, kind=None, item_id=None):
        return await read_review_page(self.session, project_id, filters, kind=kind, item_id=item_id)

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
        page = await self.page(
            project_id, QueueFilters(status="all", page_size=1), kind=kind, item_id=item_id
        )
        items = page["items"]
        if not items:
            raise HTTPException(404, "Review item not found")
        item = items[0]
        entity = ENTITIES[kind]
        args = payload.model_dump(mode="json")
        receipt = (
            self.scoped(AuditEvent, project_id)
            .with_only_columns(AuditEvent.details)
            .where(
                AuditEvent.entity_type == entity,
                AuditEvent.entity_id == item_id,
                AuditEvent.actor_id == self.user.id,
                AuditEvent.details["key"].as_string() == str(payload.key),
                AuditEvent.action.in_(("review.command", "review.add_note", "review.assign_owner")),
            )
        )
        for (details,) in await self.checked_query("review_history_query", receipt):
            if any(details.get(k) != v for k, v in args.items()):
                raise HTTPException(409, "This command key was used with different inputs")
            return {"change_order_id": details.get("change_order_id")}
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
