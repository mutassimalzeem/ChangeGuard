# Authentication (Feature 1.2)

Apply `alembic upgrade head` before starting the backend. Revision
`0002_authentication` adds refresh sessions, password reset grants, PostgreSQL
rate-limit buckets, system authentication events, and `users.token_version`.
The revision is reversible; downgrading removes authentication state and revokes
sessions by deleting it.

## API contract

All endpoints accept JSON under `/api/v1/auth`. Passwords are 12–1024 characters
at signup/reset; login accepts existing shorter passwords for migration purposes.
Emails are case-folded. Tenant slugs use lowercase letters, digits, and hyphens.

| POST endpoint | JSON body | Result |
| --- | --- | --- |
| `/register` | `tenant_slug`, `tenant_name`, `full_name`, `email`, `password` | Generic 202; creates a new tenant and owner when the slug is unused |
| `/login` | `tenant_slug`, `email`, `password` | `access_token`, `refresh_token`, `token_type`, `expires_in` |
| `/refresh` | `refresh_token` | New access/refresh pair; consumes the supplied refresh token |
| `/logout` | `refresh_token` | Idempotent 204; revokes the refresh-token family |
| `/password-reset/request` | `tenant_slug`, `email` | Generic 202; sends reset instructions if the active account exists |
| `/password-reset/confirm` | `token`, `password` | 200; changes password, consumes reset grants, revokes sessions |

Signup cannot add users to an existing tenant. Invitations/memberships belong to a
later feature. Each user belongs to one tenant; the same email may be used in
different tenants, so login/reset require the tenant slug. Existing slugs receive
the same registration response regardless of email. Signup does not verify email
ownership; email verification is a separate future feature.

Use `Depends(get_current_user)` from `app.api.dependencies` on protected routes.
It checks the JWT signature, algorithm allowlist, issuer, audience, purpose,
required claims, expiration, user token version, active user, and active tenant.
It returns the current database user and sets trusted tenant/user request state.
It never trusts tenant/user headers or JWT roles for authorization decisions.
No additional protected business endpoints are added by this feature.

## Token lifecycle

Passwords use Argon2id (19 MiB, 2 iterations, parallelism 1). Legacy bcrypt hashes
are verified without truncation and upgraded to Argon2id on successful login.
Hashing runs in a worker thread. Unknown users perform dummy Argon2 verification.

Access tokens default to 15 minutes (configuration is capped at 30 minutes).
Refresh tokens are 384-bit opaque random values; only SHA-256 hashes are stored.
Each refresh rotates to a new token with the family's original absolute expiry.
Reusing a rotated token revokes the entire family. Row locks serialize refresh,
logout, and reset operations across workers. Concurrent requests using the same
refresh token count as replay: the family is revoked, requiring a new login.

Logout revokes refresh tokens in that family; an existing access token remains
valid until its short expiry. Password reset revokes all refresh families and
increments the user's token version, immediately invalidating old access tokens.
Disabled users/tenants cannot log in, refresh, or use the current-user dependency.

Reset tokens are purpose/audience-bound signed JWTs, expire after 30 minutes by
default, and have a stored hash-backed single-use grant. A newer reset request
invalidates prior grants. A reset token cannot be used as an access token.

## Password reset email

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_FROM_EMAIL`, and optionally
`SMTP_USERNAME`/`SMTP_PASSWORD`. STARTTLS with certificate verification is on by
default. Use a trusted HTTPS `FRONTEND_URL` in deployed environments. The reset
link is `<FRONTEND_URL>/reset-password#token=...`; frontend reset UI implementation
is outside this backend feature. The fragment avoids query-string logging.

Without SMTP_HOST, every reset request gets the same 503 before account lookup.
With SMTP configured, known and unknown accounts get the same 202 response; a
background task sends email after the database commit. Mail delivery failures emit
a fixed operational event without exception text; users may retry the request.
Background tasks are not a durable email queue, so production deployments that
need delivery retries should supply an adapter using their job infrastructure.
`get_password_reset_mailer` is injectable, and tests capture mail without sending it.
Reset tokens are never returned in API responses or written to application logs.

## Rate limits, errors, and audits

Failed-login limits persist in PostgreSQL and apply to both an HMAC-hashed
tenant/email identifier and an HMAC-hashed client IP. Defaults: 5 account failures
and 50 IP failures per 900-second window. A successful login does not erase prior
failed attempts within that window. Register/reset requests have separate account
and IP budgets (`AUTH_REQUEST_LIMIT`, default 10 / 100 per window). Buckets are
locked in stable order and reset after expiration. Purge expired buckets and old
revoked/expired session/grant rows according to your retention policy.

Only the ASGI peer address is used, never unverified forwarding headers. Configure
the deployment's trusted proxy handling so this address represents the client.
Rate limiting returns generic 429 with Retry-After. Credential/token denials return
generic 401. Authentication validation errors do not echo request inputs. Token
responses use Cache-Control: no-store. Clients must securely store bearer tokens
and use HTTPS; cookie transport/CSRF policies are not implemented here.

`authentication_events` is a system audit stream that can record failures even for
unknown tenants; it permits a null tenant and never stores raw email, password,
token, or IP. `auth_rate_limits` is also system-owned. Tenant-owned sessions/grants
retain non-null tenant FKs and tenant-consistent user FKs. Known-tenant events are
also written to `audit_events`. Actions include registration, login, login_failed,
refresh_replay, logout, password_reset_requested, password_reset_failed, and
password_reset. Failed-login rate updates, replay revocations, and audits are
explicitly committed even when the HTTP result is a denial.

The hashing, reset, and rotation choices follow the OWASP Password Storage and
Forgot Password cheat sheets and RFC 9700 section 4.14.2:

- https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
- https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
- https://www.rfc-editor.org/rfc/rfc9700.html#section-4.14.2
