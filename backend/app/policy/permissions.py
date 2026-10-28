"""Explicit, default-deny permission matrix. Roles always come from the database."""

from enum import StrEnum
from types import MappingProxyType


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    PROJECT_MANAGER = "project_manager"
    COMMERCIAL_MANAGER = "commercial_manager"
    SITE_ENGINEER = "site_engineer"
    VIEWER = "viewer"
    AUDITOR = "auditor"


class Action(StrEnum):
    TENANT_READ = "tenant.read"
    TENANT_MANAGE = "tenant.manage"
    USERS_MANAGE = "users.manage"
    PROJECT_READ = "project.read"
    PROJECT_CREATE = "project.create"
    PROJECT_UPDATE = "project.update"
    PROJECT_DELETE = "project.delete"
    MEMBERS_MANAGE = "project.members.manage"
    DOCUMENT_READ = "documents.read"
    DOCUMENT_WRITE = "documents.write"
    CONTRACT_READ = "contracts.read"
    CONTRACT_WRITE = "contracts.write"
    CONTRACT_COMMIT = "contracts.commit"
    RFI_WRITE = "rfis.write"
    CHANGE_WRITE = "change_orders.write"
    CHANGE_SUBMIT = "change_orders.submit"
    APPROVAL_DECIDE = "approvals.decide"
    RISK_WRITE = "risks.write"
    RISK_ACCEPT = "risks.accept"
    FINANCIAL_READ = "financial.read"
    FINANCIAL_WRITE = "financial.write"
    FINANCIAL_RELEASE = "financial.release"
    AUDIT_READ = "audit.read"


_READ = frozenset(
    {Action.TENANT_READ, Action.PROJECT_READ, Action.DOCUMENT_READ, Action.CONTRACT_READ}
)
_SITE = _READ | {Action.DOCUMENT_WRITE, Action.RFI_WRITE, Action.CHANGE_WRITE, Action.RISK_WRITE}
_COMMERCIAL = _SITE | {
    Action.CONTRACT_WRITE,
    Action.CONTRACT_COMMIT,
    Action.CHANGE_SUBMIT,
    Action.APPROVAL_DECIDE,
    Action.RISK_ACCEPT,
    Action.FINANCIAL_READ,
    Action.FINANCIAL_WRITE,
    Action.FINANCIAL_RELEASE,
}
PERMISSIONS = MappingProxyType(
    {
        Role.OWNER: frozenset(Action),
        Role.ADMIN: frozenset(Action),
        Role.PROJECT_MANAGER: _COMMERCIAL | {Action.PROJECT_CREATE, Action.PROJECT_UPDATE},
        Role.COMMERCIAL_MANAGER: _COMMERCIAL,
        Role.SITE_ENGINEER: _SITE,
        Role.VIEWER: _READ,
        Role.AUDITOR: _READ | {Action.AUDIT_READ},
    }
)
TENANT_WIDE_ROLES = frozenset({Role.OWNER, Role.ADMIN})


def has_permission(role: str, action: str) -> bool:
    return action in PERMISSIONS.get(role, frozenset())
