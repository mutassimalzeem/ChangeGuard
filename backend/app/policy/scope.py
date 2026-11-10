"""Authenticated ORM query boundaries. Raw SQL and bulk writes fail closed."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import event, inspect, select
from sqlalchemy.orm import ColumnProperty, Session, undefer, with_loader_criteria
from sqlalchemy.sql import visitors
from sqlalchemy.sql.elements import ColumnClause, TextClause
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.selectable import Alias, Select

from app.api.exceptions import AuthorizationError
from app.core.database import Base
from app.domain.models import Project, ProjectMembership, Tenant
from app.policy.permissions import TENANT_WIDE_ROLES, Action, Role, has_permission

SCOPE_KEY = "access_principal"
FINANCIAL_FIELDS = {
    "project_events": frozenset({"suggested_cost_impact", "suggested_currency"}),
    "projects": frozenset({"currency", "contract_value"}),
    "contracts": frozenset({"value", "currency"}),
    "boq_items": frozenset({"unit_rate", "currency"}),
    "change_orders": frozenset({"amount", "currency", "cost_items", "draft_content"}),
    "risks": frozenset({"exposure_amount", "currency"}),
    "ai_traces": frozenset({"cost"}),
}
_WRITE_ACTIONS = {
    "projects": Action.PROJECT_UPDATE,
    "pilot_onboarding": Action.DOCUMENT_WRITE,
    "project_memberships": Action.MEMBERS_MANAGE,
    "documents": Action.DOCUMENT_WRITE,
    "document_chunks": Action.DOCUMENT_WRITE,
    "project_events": Action.DOCUMENT_WRITE,
    "contracts": Action.CONTRACT_WRITE,
    "contract_clauses": Action.CONTRACT_WRITE,
    "boq_items": Action.CONTRACT_WRITE,
    "rfis": Action.RFI_WRITE,
    "change_orders": Action.CHANGE_WRITE,
    "risks": Action.RISK_WRITE,
    "evidence_links": Action.CHANGE_WRITE,
    "claims": Action.CHANGE_WRITE,
    "ai_answers": Action.CHANGE_WRITE,
    "site_photos": Action.DOCUMENT_WRITE,
    "users": Action.USERS_MANAGE,
    "tenants": Action.TENANT_MANAGE,
}
_REVIEWED_STATUSES = {
    "change_orders": frozenset({"submitted", "approved", "accepted", "executed", "paid"}),
    "contracts": frozenset({"active", "signed", "executed", "committed"}),
    "risks": frozenset({"accepted", "dismissed", "overridden", "resolved"}),
}


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    tenant_id: UUID
    role: Role


def bind_scope(session, user) -> Principal:
    try:
        principal = Principal(user.id, user.tenant_id, Role(user.role))
    except ValueError:
        raise AuthorizationError() from None
    previous = session.info.get(SCOPE_KEY)
    if previous is not None and previous != principal:
        raise AuthorizationError("Cannot change the authenticated session identity")
    if previous is None:
        # Prevent rows loaded by trusted setup code from surviving in the identity map.
        for instance in list(session.identity_map.values()):
            table = inspect(instance).mapper.local_table
            if "project_id" in table.c or table.name == "projects":
                session.expire(instance)
    session.info[SCOPE_KEY] = principal
    return principal


def accessible_project_ids(principal: Principal):
    if principal.role in TENANT_WIDE_ROLES:
        table = Project.__table__
        return select(table.c.id).where(table.c.tenant_id == principal.tenant_id)
    table = ProjectMembership.__table__
    return select(table.c.project_id).where(
        table.c.tenant_id == principal.tenant_id,
        table.c.user_id == principal.user_id,
        table.c.is_active.is_(True),
    )


def _entity_descriptions(statement):
    return getattr(statement, "column_descriptions", [])


def _has_financial_column(expression):
    for node in visitors.iterate(expression):
        for column in getattr(node, "base_columns", ()):
            table = getattr(column, "table", None)
            if table is not None and column.name in FINANCIAL_FIELDS.get(table.name, ()):
                return True
    return False


def _guard_financial_options(statement):
    for option in statement._with_options:
        for loader in getattr(option, "context", (option,)):
            strategy = dict(getattr(loader, "strategy", ()) or ())
            if strategy.get("deferred") is True:
                continue
            for token in getattr(loader, "path", ()):
                if (
                    isinstance(token, str)
                    and token.startswith("column:")
                    and strategy.get("deferred") is False
                ):
                    raise AuthorizationError("Financial fields cannot be undeferred")
                for column in token.columns if isinstance(token, ColumnProperty) else ():
                    if column.name in FINANCIAL_FIELDS.get(column.table.name, ()):
                        raise AuthorizationError("Financial fields cannot be undeferred")


def _validate_orm_shape(statement):
    """Do not allow mixing unscoped Core SQL into an otherwise ORM query."""
    mapped_tables = set()
    trusted_aliases = set()
    nodes = list(visitors.iterate(statement))
    for node in nodes:
        mapper = getattr(node, "_annotations", {}).get("parentmapper")
        if mapper is not None:
            mapped_tables.add(mapper.local_table.name)
        entity = getattr(node, "_annotations", {}).get("parententity")
        if entity is not None and hasattr(entity, "selectable"):
            trusted_aliases.add(entity.selectable)
    domain_tables = set(Base.metadata.tables)

    def visit(node, parent=None, count_expression=False):
        if isinstance(node, TextClause):
            raise AuthorizationError("Textual SQL is not permitted in a scoped query")
        if isinstance(node, Select) and node._propagate_attrs.get("compile_state_plugin") != "orm":
            if any(
                getattr(child, "name", None) in domain_tables for child in visitors.iterate(node)
            ):
                raise AuthorizationError("Core subqueries are not permitted in a scoped query")
        if (
            isinstance(node, Alias)
            and not node._annotations.get("parententity")
            and node._deannotate() not in trusted_aliases
        ):
            raise AuthorizationError("Use ORM aliases in scoped queries")
        if isinstance(node, ColumnClause):
            if node.is_literal and not (node.name == "*" and count_expression):
                raise AuthorizationError("SQL literals are not permitted in a scoped query")
            table = getattr(node, "table", None)
            if (
                table is not None
                and table.name in domain_tables
                and table.name not in mapped_tables
            ):
                raise AuthorizationError("Core projections are not permitted in a scoped query")
        for child in node.get_children():
            visit(
                child,
                node,
                count_expression or (isinstance(node, Function) and node.name == "count"),
            )

    visit(statement)


@event.listens_for(Session, "do_orm_execute")
def enforce_query_scope(state):
    principal = state.session.info.get(SCOPE_KEY)
    if principal is None and state.session.info.get("require_project_scope"):
        project_tables = {
            mapper.local_table.name
            for mapper in Base.registry.mappers
            if "project_id" in mapper.local_table.c
        } | {"projects"}
        if isinstance(state.statement, TextClause):
            if state.statement.text.strip().upper() != "SELECT 1":
                raise AuthorizationError("Project queries require an authenticated scope")
        elif any(
            getattr(node, "name", None) in project_tables
            for node in visitors.iterate(state.statement)
        ):
            raise AuthorizationError("Project queries require an authenticated scope")
    if principal is not None and (
        not state.is_select
        or not state.is_orm_statement
        or getattr(state.statement, "is_from_statement", False)
    ):
        raise AuthorizationError("Scoped sessions require ORM SELECTs; use checked ORM writes")
    if principal is not None and state.is_column_load:
        raise AuthorizationError("Use an explicit scoped SELECT instead of refreshing columns")
    if not state.is_select or not state.is_orm_statement:
        return
    statement = state.statement
    if principal is not None and not state.is_relationship_load:
        _validate_orm_shape(statement)
    descriptions = _entity_descriptions(statement)
    if principal is not None:
        selected_tables = {
            inspect(d["entity"]).mapper.local_table.name
            for d in descriptions
            if d.get("entity") is not None
        }
        selected_tables.update(
            node._annotations["parentmapper"].local_table.name
            for node in visitors.iterate(statement)
            if getattr(node, "_annotations", {}).get("parentmapper") is not None
        )
        if selected_tables & {"auth_sessions", "password_reset_grants", "auth_rate_limits"}:
            raise AuthorizationError("Authentication state is not a business query resource")
        if selected_tables & {
            "audit_events",
            "authentication_events",
            "ai_traces",
        } and not has_permission(principal.role, Action.AUDIT_READ):
            raise AuthorizationError()
    financial = principal is None or has_permission(principal.role, Action.FINANCIAL_READ)
    if financial:
        # Entity loads may include deferred financial fields only for authorized callers.
        if any(
            d.get("entity") is not None and d.get("expr") is d.get("entity") for d in descriptions
        ):
            statement = statement.options(undefer("*"))
    else:
        _guard_financial_options(statement)
        # Guard explicit projections and derived/filter/order expressions too.
        expressions = [d["expr"] for d in descriptions if d.get("expr") is not d.get("entity")]
        for attribute in (
            "_where_criteria",
            "_order_by_clauses",
            "_group_by_clauses",
            "_having_criteria",
        ):
            expressions.extend(getattr(statement, attribute, ()))
        if any(_has_financial_column(expr) for expr in expressions):
            raise AuthorizationError("Financial permission required")
    if principal is None:
        state.statement = statement
        return
    project_ids = accessible_project_ids(principal)
    statement = statement.options(
        with_loader_criteria(Tenant, Tenant.id == principal.tenant_id, include_aliases=True)
    )
    for mapper in Base.registry.mappers:
        model = mapper.class_
        table = mapper.local_table
        if "tenant_id" in table.c:
            statement = statement.options(
                with_loader_criteria(
                    model, model.tenant_id == principal.tenant_id, include_aliases=True
                )
            )
        if table.name == "users" and principal.role not in TENANT_WIDE_ROLES:
            statement = statement.options(
                with_loader_criteria(model, model.id == principal.user_id, include_aliases=True)
            )
        if model is Project:
            statement = statement.options(
                with_loader_criteria(model, model.id.in_(project_ids), include_aliases=True)
            )
        elif model is ProjectMembership:
            if principal.role not in TENANT_WIDE_ROLES:
                statement = statement.options(
                    with_loader_criteria(
                        model, model.user_id == principal.user_id, include_aliases=True
                    )
                )
        elif "project_id" in table.c:
            clause = model.project_id.in_(project_ids)
            if table.c.project_id.nullable:
                clause = clause | model.project_id.is_(None)
            statement = statement.options(with_loader_criteria(model, clause, include_aliases=True))
    state.statement = statement


@event.listens_for(Session, "before_flush")
def enforce_write_scope(session, flush_context, instances):
    principal = session.info.get(SCOPE_KEY)
    if principal is None:
        if session.info.get("require_project_scope"):
            for instance in session.new | session.dirty | session.deleted:
                table = inspect(instance).mapper.local_table
                if table.name == "projects" or (
                    "project_id" in table.c and getattr(instance, "project_id", None) is not None
                ):
                    raise AuthorizationError("Project writes require an authenticated scope")
        return
    for instance in session.new | session.dirty | session.deleted:
        state = inspect(instance)
        table = state.mapper.local_table
        link_write = session.info.get("event_link_write")
        is_link = link_write is not None and instance is link_write[0] and instance in session.new
        is_link_audit = link_write is not None and instance is link_write[1] and instance in session.new
        if is_link or is_link_audit:
            link, audit = link_write
            if (audit not in session.new or link not in session.new
                    or audit.actor_id != principal.user_id or link.actor_id != principal.user_id
                    or link.tenant_id != principal.tenant_id or audit.tenant_id != principal.tenant_id
                    or audit.project_id != link.project_id or audit.entity_id != link.event_id
                    or audit.entity_type != "project_event" or audit.action != "project_event.link_entity"
                    or not link.reason.strip() or audit.details.get("reason") != link.reason
                    or not has_permission(principal.role, Action.RISK_ACCEPT)
                    or not has_permission(principal.role, Action.RFI_WRITE if link.rfi_id else Action.CHANGE_WRITE)):
                raise AuthorizationError("Invalid explicit event link")
        resolution = session.info.get("risk_resolution")
        resolved_risk = resolution is not None and instance is resolution[0]
        resolution_audit = resolution is not None and instance is resolution[1] and instance in session.new
        if resolved_risk or resolution_audit:
            risk, audit, link = resolution
            kind, target = ("rfi", link.rfi_id) if link.rfi_id else ("change_order", link.change_order_id)
            if (audit not in session.new or risk.resolution_link_id != link.id
                    or risk.project_event_id != link.event_id or risk.project_id != link.project_id
                    or risk.tenant_id != principal.tenant_id or link.tenant_id != principal.tenant_id
                    or risk.risk_type != "daily_report_delay_without_link" or risk.status != "resolved"
                    or audit.actor_id != principal.user_id or risk.resolved_by_id != principal.user_id
                    or audit.tenant_id != principal.tenant_id or audit.project_id != risk.project_id
                    or audit.entity_id != risk.id or audit.entity_type != "risk" or audit.action != "risk.resolve"
                    or audit.details.get("reason") != risk.resolution_reason or not risk.resolution_reason
                    or audit.details.get("resolved_at") != risk.resolved_at.isoformat()
                    or audit.details.get("resolving_entity_type") != kind
                    or audit.details.get("resolving_entity_id") != str(target)
                    or not has_permission(principal.role, Action.RISK_ACCEPT)
                    or not has_permission(principal.role, Action.RFI_WRITE if link.rfi_id else Action.CHANGE_WRITE)):
                raise AuthorizationError("Invalid risk resolution")
        if table.name == "event_entity_links" and not is_link:
            raise AuthorizationError("Event links require the append-only audited workflow")
        if table.name == "risks" and not resolved_risk:
            if any(state.attrs[name].history.has_changes() for name in (
                "resolution_link_id", "resolved_by_id", "resolved_at", "resolution_reason"
            )):
                raise AuthorizationError("Risk resolution requires an audited event link")
        review = session.info.get("risk_review")
        reviewed_risk = review is not None and instance is review[0]
        review_audit = review is not None and instance is review[1] and instance in session.new
        workflow = session.info.get("change_order_workflow")
        workflow_order = workflow is not None and instance is workflow[0]
        workflow_audit = workflow is not None and instance is workflow[1] and instance in session.new
        workflow_approval = workflow is not None and instance is workflow[2]
        investigation_review = session.info.get("investigation_review")
        investigation_audit = (investigation_review is not None and instance is investigation_review[1]
                               and instance in session.new)
        investigation_task = investigation_review is not None and instance is investigation_review[0]
        if investigation_audit or investigation_task:
            task, audit = investigation_review
            if (not has_permission(principal.role, Action.DOCUMENT_WRITE)
                    or inspect(task).mapper.local_table.name != "document_review_tasks"
                    or audit not in session.new
                    or audit.actor_id != principal.user_id or audit.tenant_id != principal.tenant_id
                    or task.tenant_id != principal.tenant_id or audit.project_id != task.project_id
                    or audit.entity_id != task.id or audit.entity_type != "document_review_task"
                    or audit.action != "investigation.request_human_review"
                    or not audit.details.get("evidence")):
                raise AuthorizationError("Invalid investigation review request")
        if workflow_order or workflow_audit or workflow_approval:
            order, audit, approval = workflow
            required_action = {
                "change_order.submit": Action.CHANGE_SUBMIT,
                "change_order.approved": Action.APPROVAL_DECIDE,
                "change_order.rejected": Action.APPROVAL_DECIDE,
            }.get(audit.action, Action.CHANGE_WRITE)
            if (audit not in session.new or audit.actor_id != principal.user_id
                    or audit.tenant_id != principal.tenant_id or audit.project_id != order.project_id
                    or audit.entity_type != "change_order" or audit.entity_id != order.id
                    or audit.details.get("to_status") != order.status
                    or not audit.details.get("reason")
                    or not has_permission(principal.role, required_action)):
                raise AuthorizationError("Invalid audited change-order workflow")
            if approval is not None and (
                approval.change_order_id != order.id or approval.project_id != order.project_id
                or approval.tenant_id != order.tenant_id
            ):
                raise AuthorizationError("Invalid workflow approval")
        if reviewed_risk or review_audit:
            risk, audit = review
            if (not has_permission(principal.role, Action.RISK_ACCEPT)
                    or audit not in session.new or audit.actor_id != principal.user_id
                    or audit.tenant_id != principal.tenant_id or audit.entity_id != risk.id
                    or audit.project_id != risk.project_id or not audit.details.get("reason")):
                raise AuthorizationError("Invalid risk review")
        tenant_id = instance.id if table.name == "tenants" else getattr(instance, "tenant_id", None)
        if tenant_id != principal.tenant_id:
            raise AuthorizationError("Tenant access denied")
        pilot_audit = session.info.get("pilot_audit")
        pilot_member = session.info.get("pilot_membership")
        is_pilot_audit = instance is pilot_audit and instance in session.new
        user_audit = session.info.get("user_action_audit")
        is_user_audit = instance is user_audit and instance in session.new
        if is_user_audit:
            required = {
                "project.create": (Action.PROJECT_CREATE, "project"),
                "project.update": (Action.PROJECT_UPDATE, "project"),
                "document.upload": (Action.DOCUMENT_WRITE, "document"),
                "document.delete": (Action.DOCUMENT_WRITE, "document"),
            }.get(user_audit.action)
            if (required is None or user_audit.actor_id != principal.user_id
                    or user_audit.tenant_id != principal.tenant_id
                    or user_audit.entity_type != required[1]
                    or not has_permission(principal.role, required[0])):
                raise AuthorizationError("Invalid user action audit")
        created_project = session.info.get("created_project")
        creator_membership = (created_project is not None
                              and table.name == "project_memberships"
                              and instance in session.new
                              and instance.project_id == created_project.id
                              and instance.tenant_id == principal.tenant_id
                              and instance.user_id == principal.user_id
                              and has_permission(principal.role, Action.PROJECT_CREATE))
        is_pilot_member = instance is pilot_member and instance in session.new
        if is_pilot_audit or is_pilot_member:
            if pilot_audit is None:
                raise AuthorizationError("Missing pilot audit")
            required = Action.PROJECT_CREATE if pilot_audit.action == "pilot.create" else Action.DOCUMENT_WRITE
            if (pilot_audit not in session.new or pilot_audit.actor_id != principal.user_id
                    or pilot_audit.tenant_id != principal.tenant_id
                    or pilot_audit.action not in {"pilot.create", "pilot.review", "pilot.checklist"}
                    or pilot_audit.entity_type != "pilot" or pilot_audit.entity_id != pilot_audit.project_id
                    or not has_permission(principal.role, required)):
                raise AuthorizationError("Invalid pilot audit")
            if is_pilot_member and (pilot_audit.action != "pilot.create"
                    or pilot_member.user_id != principal.user_id
                    or pilot_member.project_id != pilot_audit.project_id):
                raise AuthorizationError("Invalid pilot creator membership")
        action = _WRITE_ACTIONS.get(table.name)
        if table.name == "projects" and instance in session.new:
            action = Action.PROJECT_CREATE
        if not (review_audit or workflow_audit or workflow_approval
                or investigation_audit or investigation_task or is_pilot_audit or is_pilot_member
                or is_user_audit or creator_membership or is_link or is_link_audit or resolution_audit) and (
            action is None or not has_permission(principal.role, action)
        ):
            raise AuthorizationError()
        if table.name == "change_orders" and instance not in session.new and not workflow_order:
            if any(attribute.history.has_changes() for attribute in state.attrs):
                raise AuthorizationError("Change orders require an audited workflow")
        if table.name == "risks" and instance not in session.new and not reviewed_risk:
            reviewed_fields = ("severity", "exposure_amount", "schedule_impact_days",
                               "responsible_party", "recommended_action", "confidence")
            if any(state.attrs[name].history.has_changes() for name in reviewed_fields):
                raise AuthorizationError("Risk overrides require an audited human review")
        if table.name == "projects" and instance in session.deleted:
            raise AuthorizationError("Project deletion requires human approval")
        if "status" in state.attrs and state.attrs.status.history.has_changes():
            if (instance.status in _REVIEWED_STATUSES.get(table.name, ())
                    and not reviewed_risk and not workflow_order and not resolved_risk):
                raise AuthorizationError(
                    "This status transition requires a verified human workflow"
                )
        if instance not in session.new:
            for name in ("tenant_id", "project_id"):
                if name in state.attrs and state.attrs[name].history.has_changes():
                    raise AuthorizationError("Ownership changes are forbidden")
        project_id = (
            instance.id if table.name == "projects" else getattr(instance, "project_id", None)
        )
        pilot_created = session.info.get("pilot_created_project")
        pilot_creation_record = (
            pilot_created is not None and pilot_created.id == project_id
            and pilot_created.tenant_id == principal.tenant_id
            and has_permission(principal.role, Action.PROJECT_CREATE)
            and instance in session.new
            and (is_pilot_member or is_pilot_audit or table.name == "pilot_onboarding")
        )
        project_creation_record = (created_project is not None and project_id == created_project.id
                                   and (creator_membership or (is_user_audit and user_audit.action == "project.create")))
        if project_id is not None and not (table.name == "projects" and instance in session.new) and not pilot_creation_record and not project_creation_record:
            with session.no_autoflush:
                exists = session.scalar(select(Project.id).where(Project.id == project_id))
            if exists is None:
                raise AuthorizationError("Project access denied")
        if not has_permission(principal.role, Action.FINANCIAL_WRITE):
            if any(
                state.attrs[name].history.has_changes()
                for name in FINANCIAL_FIELDS.get(table.name, ())
            ):
                raise AuthorizationError("Financial permission required")


def project_record_data(instance, principal: Principal) -> dict:
    """Serialize mapped columns explicitly; never serialize an ORM __dict__."""
    table = inspect(instance).mapper.local_table
    if getattr(instance, "tenant_id", None) != principal.tenant_id:
        raise AuthorizationError()
    financial = has_permission(principal.role, Action.FINANCIAL_READ)
    hidden = FINANCIAL_FIELDS.get(table.name, frozenset()) if not financial else frozenset()
    # Opaque JSON can contain arbitrary financial fields; expose through typed schemas later.
    hidden = hidden | {"attributes", "details", "password_hash", "token_version"}
    return {
        column.name: getattr(instance, column.name)
        for column in table.c
        if column.name not in hidden
    }
