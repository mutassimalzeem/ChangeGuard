# ChangeGuard — Security and Trust Policy

**Version:** 0.1  
**Date:** October 27, 2026  
**Status:** MVP security baseline  

---

## 1. Security objective

ChangeGuard handles commercially sensitive construction data: contracts, pricing, drawings, supplier information, project delays, and dispute evidence.

The security objective is simple:

> Customers must be able to trust that their project evidence is private, access-controlled, traceable, and never altered silently.

---

## 2. Security principles

1. **Tenant isolation by default.** No data crosses tenant boundaries.
2. **Least privilege.** Users and services receive only required access.
3. **Evidence integrity.** Original files are immutable.
4. **Human approval for consequential actions.** AI cannot approve, send, delete, or finalize critical actions.
5. **Auditability.** Every meaningful action is recorded.
6. **Defense in depth.** Validate at API, application, database, storage, and AI layers.
7. **Fail closed.** If permission or validation cannot be determined, deny the action.
8. **No secret leakage.** Secrets stay in secret management, never in code or logs.

---

## 3. Authentication

### MVP requirements

- Email and password authentication.
- Secure password hashing using Argon2id or bcrypt.
- Session tokens or short-lived JWTs.
- Refresh-token rotation where applicable.
- Account lockout or throttling after repeated failures.
- Password reset via signed, expiring links.
- Optional magic-link login.
- SSO can be added later for enterprise customers.

### Password policy

- Minimum 12 characters.
- Block common breached passwords.
- Do not impose arbitrary complexity rules that encourage bad patterns.
- Store only password hashes.

---

## 4. Authorization

Use role-based access control.

### Roles

| Role | Permissions |
|---|---|
| Owner | Full tenant administration |
| Admin | User, project, and configuration management |
| Project manager | Project operations, change orders, approvals within assigned projects |
| Commercial manager | Cost, BOQ, change-order, and claim review |
| Site engineer | Upload evidence, view assigned project data |
| Viewer | Read-only access to authorized data |
| Auditor | Read-only access to audit and evidence history |

### Authorization rules

- Every API endpoint must declare required permission.
- Every object access must check tenant, project, and role.
- Financial data may be restricted to commercial and management roles.
- Approval rights must be explicit.
- No user may approve their own high-risk action where separation of duties is required.

---

## 5. Tenant isolation

### Enforcement points

Tenant isolation must be enforced at:

1. API layer.
2. Service layer.
3. Database query layer.
4. Object-storage layer.
5. Search and retrieval layer.
6. Background-worker context.
7. AI prompt context.

### Database rules

- Every tenant-owned table includes `tenant_id`.
- Every query includes tenant filtering.
- Use database constraints and indexes on `tenant_id`.
- Consider PostgreSQL row-level security for defense in depth.

### Object-storage rules

Use tenant-scoped keys:

```text
/tenant_id/project_id/documents/document_id/original.pdf
/tenant_id/project_id/documents/document_id/extracted.json
/tenant_id/project_id/documents/document_id/chunks/chunk_id.json
```

Direct public access is disabled. Downloads require short-lived signed URLs and authorization checks.

---

## 6. Data protection

### Data classification

| Class | Examples | Handling |
|---|---|---|
| Public | Product marketing content | No restriction |
| Internal | System logs, metrics | Access-controlled |
| Confidential | Project documents, drawings, BOQs | Tenant-isolated, encrypted |
| Highly sensitive | Contracts, pricing, personal data, dispute evidence | Strict access, audit, minimization |

### Encryption

- TLS 1.2+ for all transport.
- Encryption at rest for database, object storage, and backups.
- Application-level encryption for selected highly sensitive fields where justified.
- Secure key management; never hard-code keys.

### Data minimization

Collect only what is necessary:

- Name, email, role.
- Project metadata.
- Uploaded documents.
- Operational events.
- Audit records.

Do not collect unnecessary personal data, device data, or location data without a clear purpose and consent.

---

## 7. AI-specific security

AI introduces risks beyond normal software security.

### Threats

| Threat | Risk | Control |
|---|---|---|
| Prompt injection | AI follows malicious instructions in documents | Treat documents as untrusted data |
| Indirect prompt injection | Malicious instruction in email, PDF, or image | Input filtering, instruction isolation, tool restrictions |
| Data exfiltration | AI reveals unauthorized data | Permission-aware retrieval |
| Hallucination | False financial or contractual claim | Citation enforcement and validation |
| Overprivileged agent | AI performs unsafe action | Read-only tools and approval gates |
| Sensitive-data leakage to model provider | Confidential data leaves tenant boundary | Data policy, redaction, provider agreements |
| Model-output manipulation | Invalid JSON or false claims | Schema validation and groundedness checks |

### Rules

1. Retrieved documents are **data**, never instructions.
2. The model cannot receive unrestricted database access.
3. Tool calls are allowlisted.
4. Financial calculations happen outside the LLM.
5. Every generated factual claim requires evidence.
6. If evidence is insufficient, the system must refuse or request review.
7. Prompt-injection attempts are logged.
8. High-risk AI outputs require human approval.

---

## 8. Audit and logging

### Audit events

Record:

- Login and failed login.
- Password reset.
- Role change.
- Project creation and modification.
- Document upload, download, and deletion.
- Extraction correction.
- Risk creation, dismissal, and override.
- Change-order creation and status change.
- Approval and rejection.
- AI query and generated conclusion.
- Tool call.
- Export.
- Configuration change.

### Audit record fields

```json
{
  "event_id": "uuid",
  "tenant_id": "uuid",
  "actor_user_id": "uuid",
  "actor_type": "user|system|ai",
  "action": "change_order.approve",
  "resource_type": "change_order",
  "resource_id": "uuid",
  "project_id": "uuid",
  "before": {},
  "after": {},
  "reason": "Approved after commercial review",
  "trace_id": "uuid",
  "created_at": "2026-10-27T08:47:00Z"
}
```

### Log hygiene

Never log:

- Passwords.
- API keys.
- Tokens.
- Full authorization headers.
- Raw sensitive document content unless operationally necessary.
- Customer secrets.

Use redaction and structured logging.

---

## 9. Secrets management

- Store secrets in environment-specific secret management.
- Never commit `.env` files.
- Rotate database, storage, LLM, and email credentials.
- Use separate credentials per environment.
- Grant workers only the permissions they need.
- Use short-lived credentials where possible.

---

## 10. File-upload security

### Upload controls

- Validate file extension, MIME type, and magic bytes.
- Enforce maximum file size.
- Scan for malware where feasible.
- Store originals outside the web root.
- Serve downloads through authorized, expiring URLs.
- Sanitize filenames.
- Prevent path traversal.
- Limit concurrent uploads per user.

### Document processing

- Process untrusted files in isolated workers.
- Restrict worker network access where possible.
- Set CPU, memory, and execution-time limits.
- Do not execute embedded macros or scripts.
- Quarantine failed or suspicious files.

---

## 11. API security

- Use HTTPS only.
- Authenticate every non-public endpoint.
- Apply rate limiting.
- Validate all request bodies with strict schemas.
- Use parameterized queries.
- Return generic errors; do not leak stack traces.
- Set security headers.
- Use CORS restrictions.
- Version the API.
- Log rejected authorization attempts.

---

## 12. Backup and recovery

### Requirements

- Automated daily database backups.
- Point-in-time recovery where available.
- Encrypted backups.
- Separate backup credentials.
- Quarterly restore test.
- Document recovery time objective and recovery point objective.

### MVP targets

| Item | Target |
|---|---|
| RPO | <= 24 hours initially |
| RTO | <= 8 hours initially |
| Backup frequency | Daily |
| Restore test | Quarterly |

---

## 13. Incident response

### Severity levels

| Severity | Example | Response |
|---|---|---|
| S1 | Cross-tenant data exposure | Immediate containment, customer notification, root-cause analysis |
| S2 | Unauthorized access to one project | Contain, revoke access, investigate |
| S3 | AI generated unsupported critical output | Disable feature path, add guardrail, review |
| S4 | Non-sensitive bug or availability issue | Standard engineering response |

### Response steps

1. Detect and confirm.
2. Contain access.
3. Preserve evidence and logs.
4. Notify affected customers when required.
5. Remediate.
6. Conduct post-incident review.
7. Add regression tests and guardrails.

---

## 14. Customer trust requirements

Before pilot onboarding, provide customers with:

- Data-handling summary.
- Who can access their data.
- Where data is stored.
- Whether third-party AI providers process their data.
- Retention and deletion policy.
- Audit-log availability.
- Incident-contact process.

---

## 15. Security acceptance criteria

The MVP is acceptable when:

1. No cross-tenant access is possible through tested paths.
2. All sensitive endpoints require authorization.
3. Original documents are immutable and access-controlled.
4. AI outputs cannot bypass approval or permission checks.
5. Prompt-injection fixtures do not cause unauthorized actions.
6. Audit records are append-only and complete for critical actions.
7. Secrets are not present in source control or logs.
8. Backups and restore procedures are documented.
