# Roles, permissions, and project boundaries (Feature 1.3)

Run `alembic upgrade head` before deploying. Revision `0003_roles_permissions`
adds tenant-consistent project memberships and constrains users to the seven
supported roles. Existing `member` and unknown role values become `viewer`;
existing supported roles are preserved. No project assignments are inferred.
The downgrade drops assignments and the role check but does not restore old
unknown role names.

## Permission matrix

A = role permission; H = role permission plus a required human workflow;
- = denied. Every project action also requires project access in the same tenant.
Owners/admins have tenant-wide project access. Every other role, including project
and commercial managers and auditors, requires an active explicit membership.
Membership only grants project access; it never changes a user's role.

| Action | owner | admin | project_manager | commercial_manager | site_engineer | viewer | auditor |
| --- | --- | --- | --- | --- | --- | --- | --- |
| tenant.read | A | A | A | A | A | A | A |
| tenant.manage | A | A | - | - | - | - | - |
| users.manage | A | A | - | - | - | - | - |
| project.read | A | A | A | A | A | A | A |
| project.create | A | A | A | - | - | - | - |
| project.update | A | A | A | - | - | - | - |
| project.delete | H | H | - | - | - | - | - |
| project.members.manage | A | A | - | - | - | - | - |
| documents.read | A | A | A | A | A | A | A |
| documents.write | A | A | A | A | A | - | - |
| contracts.read | A | A | A | A | A | A | A |
| contracts.write | A | A | A | A | - | - | - |
| contracts.commit | H | H | H | H | - | - | - |
| rfis.write | A | A | A | A | A | - | - |
| change_orders.write | A | A | A | A | A | - | - |
| change_orders.submit | H | H | H | H | - | - | - |
| approvals.decide | A | A | A | A | - | - | - |
| risks.write | A | A | A | A | A | - | - |
| risks.accept | H | H | H | H | - | - | - |
| financial.read | A | A | A | A | - | - | - |
| financial.write | A | A | A | A | - | - | - |
| financial.release | H | H | H | H | - | - | - |
| audit.read | A | A | - | - | - | - | A |

`approvals.decide` additionally needs verified requester/actor IDs, forbids
self-approval, and requires a human when the caller is automated. Missing context,
unknown roles, unknown actions, tenant mismatches, and missing assignments deny.
An H result is not permission to execute; a later workflow must verify and record
an independent human decision. Direct approved/submitted contract/change-order
and accepted-risk state changes are blocked in business sessions.

## FastAPI integration

- `require_authenticated_user`: validate the token and active user/tenant using the
  authentication dependency, then bind an immutable principal from the database
  user to the request's session. JWT role claims are never authoritative.
- `require_role(Role.OWNER, Role.ADMIN)`: accept any of the listed roles; otherwise
  return 403. Empty or invalid role lists are configuration errors.
- `require_tenant_access`: compare the path/query `tenant_id` to the authenticated
  tenant; return 403 for a mismatch.
- `require_project_access`: resolve the path/query `project_id` through a tenant
  and membership scoped query; return the Project or the same 404 for missing,
  foreign, and unassigned projects. A valid owner/admin cannot cross tenants.
- `require_permission(Action.FINANCIAL_READ)`: apply a matrix permission in
  addition to authentication. This is a role gate, not a workflow approval.
- `require_policy_action(action)`: combine project access and policy; return 403
  for denied, 409 for human approval required, and the Project only for allowed.

For example, use `Depends(require_project_access)` and
`Depends(require_permission(Action.DOCUMENT_WRITE))` on a document mutation.
Use `ProjectAccessService(session, user)` for project record reads, membership
management, and project policy decisions. No business API routes are introduced
here; the integration tests mount test-only endpoints to exercise dependencies.

## Query and write enforcement

The runtime `ScopedAsyncSession` requires a bound authenticated scope for project
queries/writes. Omitting the new dependency therefore fails closed instead of
running an unfiltered query. The legacy `get_current_user` remains an authentication
primitive; business code should use `require_authenticated_user` or one of the
project/role dependencies. Auth registration/login/reset use narrowly scoped
identity/control-table queries before a principal exists. The constant health
query SELECT 1 is allowed before authentication.

Once bound, session execution applies tenant criteria to tenant-owned ORM entities,
plus accessible-project criteria to project records, joins, ORM aliases, aggregates,
subqueries, and relationship loaders. Assignments are checked in SQL, not cached
in JWTs. Tenant-wide roles still receive tenant filters. Session.get/get_one force
queries rather than returning stale identity-map objects. Scope binding expires
preloaded project rows; explicit column refresh is rejected in favor of a scoped
SELECT. A session cannot switch identities.

Raw/textual SQL, unannotated Core subqueries/projections, SQL literals, ORM
from_statement queries, and bulk INSERT/UPDATE/DELETE are rejected in a bound
business session. Use ORM objects and flush for checked writes. Before-flush
checks enforce tenant ownership, project access, role write permissions, immutable
ownership columns, financial permissions, and reviewed workflow status boundaries.
Direct approval/control-table mutations are not a business-session capability.
Only owners/admins may assign/revoke memberships through ProjectAccessService;
foreign-tenant users/projects are rejected by both service checks and composite FKs.

These are application-session boundaries, not PostgreSQL row-level security.
Direct engines/connections and explicitly trusted provisioning/test sessions are
privileged infrastructure and must never be exposed to request payloads. Background
jobs need a validated actor/service identity and the same ProjectAccessService
boundary; existing task placeholders do not execute project queries. Do not clear
session.info or open unscoped sessions to bypass a denied operation.

## Financial data

Only owner, admin, project_manager, and commercial_manager can read/write typed
financial fields: project/contract/BOQ/change-order/risk currency, contract value,
BOQ unit rate, change-order amount, risk exposure amount, and AI trace cost.
Financial columns are deferred with raiseload; unauthorized access cannot trigger
an implicit load. Explicit amount projections, aggregates, filters, and sorting
also require financial permission. Authorized root entity loads undefer those
fields. For nested authorized financial data, fetch it through the project record
service rather than relying on implicit loading.

ProjectAccessService.records returns column dictionaries through
project_record_data; financial fields are omitted for restricted roles. Opaque
JSON attributes/details and authentication internals are omitted from this generic
projection. Do not return ORM __dict__ or arbitrary JSON as a business response;
add typed schemas as business endpoints are built. This controls structured model
fields, not financial statements embedded in document text or uploaded files;
file/content classification policies are separate work.

## Validation

Tests cover every role's project/membership rules, generic foreign-project denial,
JWT role-claim spoofing, revoked assignments, alias/aggregate/relationship and
identity-map isolation, raw SQL/Core bypass attempts, financial projection/write
restrictions, policy approval decisions, migration role conversion, and invalid
role/cross-tenant membership database constraints. They use the disposable
PostgreSQL fixtures from Feature 1.1.
