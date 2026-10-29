"""Trusted business scope propagated through async calls and worker threadpools."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ModelScope:
    tenant_id: UUID | None = None
    project_id: UUID | None = None


_DEFAULT_SCOPE = ModelScope()
_scope = ContextVar("model_gateway_scope", default=_DEFAULT_SCOPE)


def current_scope():
    return _scope.get()


@contextmanager
def model_scope(tenant_id, project_id=None):
    scope = ModelScope(UUID(str(tenant_id)), UUID(str(project_id)) if project_id else None)
    token = _scope.set(scope)
    try:
        yield scope
    finally:
        _scope.reset(token)
