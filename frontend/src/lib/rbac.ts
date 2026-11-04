/**
 * Client mirror of the backend permission matrix.
 *
 * Source of truth: backend/app/policy/permissions.py (Role, Action values,
 * PERMISSIONS). The API stays authoritative: a 403 from the server must be ignored here. This
 * module only decides what the UI offers, so a permission added on the backend
 * has to be added here too; a test keeps the two role sets in sync.
 */

export const ROLES = [
  "owner",
  "admin",
  "project_manager",
  "commercial_manager",
  "site_engineer",
  "viewer",
  "auditor",
] as const;

export type Role = (typeof ROLES)[number];

export const PERMISSIONS = [
  "tenant.read",
  "tenant.manage",
  "users.manage",
  "project.read",
  "project.create",
  "project.update",
  "project.delete",
  "project.members.manage",
  "documents.read",
  "documents.write",
  "contracts.commit",
  "contracts.read",
  "contracts.write",
  "rfis.write",
  "change_orders.write",
  "change_orders.submit",
  "approvals.decide",
  "risks.write",
  "risks.accept",
  "financial.read",
  "financial.write",
  "financial.release",
  "audit.read",
] as const;

export type Permission = (typeof PERMISSIONS)[number];

const READ: readonly Permission[] = ["tenant.read", "project.read", "documents.read", "contracts.read"];

const SITE: readonly Permission[] = [...READ, "documents.write", "rfis.write", "change_orders.write", "risks.write"];

const COMMERCIAL: readonly Permission[] = [
  ...SITE,
  "contracts.write",
  "contracts.commit",
  "change_orders.submit",
  "approvals.decide",
  "risks.accept",
  "financial.read",
  "financial.write",
  "financial.release",
];

/** `owner` and `admin` hold every permission, as on the backend. */
export const ROLE_PERMISSIONS: Readonly<Record<Role, ReadonlySet<Permission>>> = {
  owner: new Set(PERMISSIONS),
  admin: new Set(PERMISSIONS),
  project_manager: new Set<Permission>([
    ...COMMERCIAL,
    "project.create",
    "project.update",
  ]),
  commercial_manager: new Set(COMMERCIAL),
  site_engineer: new Set(SITE),
  viewer: new Set(READ),
  auditor: new Set([...READ, "audit.read"]),
};

/** Roles whose project access is tenant-wide rather than granted per project. */
export const TENANT_WIDE_ROLES: ReadonlySet<Role> = new Set<Role>(["owner", "admin"]);

export function isRole(value: string): value is Role {
  return (ROLES as readonly string[]).includes(value);
}

export function hasPermission(role: string, action: Permission): boolean {
  return isRole(role) && ROLE_PERMISSIONS[role].has(action);
}

/** True when the role holds at least one of `actions`. */
export function hasAnyPermission(
  role: string,
  actions: readonly Permission[],
): boolean {
  return actions.some((action) => hasPermission(role, action));
}
