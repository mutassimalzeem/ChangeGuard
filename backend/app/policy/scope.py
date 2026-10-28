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
    "projects": frozenset({"currency"}),
    "contracts": frozenset({"value", "currency"}),
    "boq_items": frozenset({"unit_rate", "currency"}),
    "change_orders": frozenset({"amount", "currency"}),
    "risks": frozenset({"exposure_amount", "currency"}),
    "ai_traces": frozenset({"cost"}),
}
_WRITE_ACTIONS = {
    "projects": Action.PROJECT_UPDATE,
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
    "users": Action.USERS_MANAGE,
    "tenants": Action.TENANT_MANAGE,
}
_REVIEWED_STATUSES = {
    "change_orders": frozenset({"submitted", "approved", "accepted", "executed", "paid"}),
    "contracts": frozenset({"active", "signed", "executed", "committed"}),
    "risks": frozenset({"accepted"}),
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
        tenant_id = instance.id if table.name == "tenants" else getattr(instance, "tenant_id", None)
        if tenant_id != principal.tenant_id:
            raise AuthorizationError("Tenant access denied")
        action = _WRITE_ACTIONS.get(table.name)
        if table.name == "projects" and instance in session.new:
            action = Action.PROJECT_CREATE
        if action is None or not has_permission(principal.role, action):
            raise AuthorizationError()
        if table.name == "projects" and instance in session.deleted:
            raise AuthorizationError("Project deletion requires human approval")
        if "status" in state.attrs and state.attrs.status.history.has_changes():
            if instance.status in _REVIEWED_STATUSES.get(table.name, ()):
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
        if project_id is not None and not (table.name == "projects" and instance in session.new):
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
