# Ops authentication and human workflows

Apply `make migrate` before starting the updated API and worker. No application startup
migrations or automatic administrator creation occur.

## Administrator setup

Set these values in the existing root `.env` or optional `backend/.env`:

```dotenv
OPS_ADMIN_EMAIL=admin@example.com
OPS_ADMIN_PASSWORD=<choose-a-unique-password-of-at-least-12-characters>
OPS_COOKIE_SECURE=false
OPS_SESSION_SECONDS=28800
OPS_LOGIN_ATTEMPTS=5
OPS_LOGIN_WINDOW_SECONDS=900
```

Run `cd backend && uv run python -m app.scripts.seed_admin`. The explicit seed stores
an Argon2id hash, normalizes the email, and leaves an existing account and password
unchanged. Repeated and concurrent seeds do not duplicate users. It never prints
passwords or hashes. There is no signup, reset, or user-management endpoint.

## Authentication

- `POST /auth/login`: JSON `{ "email": "...", "password": "..." }`. Returns only
  `{id,email}` and sets `quickdrop_ops_session`.
- `GET /auth/me`: returns the authenticated operator or HTTP 401.
- `POST /auth/logout`: invalidates the current database session and clears the cookie;
  returns HTTP 204. Missing or expired sessions receive HTTP 401.

Opaque session cookies contain 256 random bits; PostgreSQL stores only SHA-256
session digests, operator references, and fixed expiry times. Successful login rotates
the current cookie. Expired sessions are rejected on every request and cleaned up on
successful login. Cookies are HttpOnly, SameSite=Strict, host-only, and Secure for HTTPS,
non-development environments, or `OPS_COOKIE_SECURE=true`. Set the secure override when
TLS terminates at a proxy. Serve the frontend and API on the same site.

Login attempts are limited per normalized email and directly connected IP, across API
processes, using PostgreSQL counters and transaction locks. Only failed credential
checks count toward the configured fixed window (default: five failures in 15 minutes).
Successful logins neither consume nor reset the failure allowance. A blocked request
returns HTTP 429 with the remaining wait in `Retry-After`; restarting the API does not
clear these database counters. Forwarded IP headers are not trusted. Behind a proxy,
its address shares an IP limit; configure trusted proxy handling separately before
using this in a public service. Invalid and unknown accounts use the same error.
Credentialed CORS permits configured origins. Mutations reject untrusted Origin and
cross-site browser requests. Programmatic clients without Origin may use their cookie.
Never log credentials or cookies. Login/logout events use structured application logs
with operator IDs; other actions use the existing conversation trace service.

All `/ui/ops/*` routes, including reads and payout reconciliation, require sessions.
The evaluator endpoints `/messages`, `/trace/{rider_id}`, and `/ops/pending` remain
unauthenticated with their assignment response shapes. Assignment endpoints are demo
interfaces and require a deployment boundary before exposing real rider data publicly.
The existing rider simulator read guard remains independent.

## Actions

| Method and path | JSON body | Result |
| --- | --- | --- |
| POST `/ui/ops/cases/{id}/approve` | None | Authorizes one exact, full durable intent; never executes a payout |
| POST `/ui/ops/cases/{id}/reject` | `{reason}` | Rejects a pending financial approval |
| POST `/ui/ops/cases/{id}/assign` | Optional `{operator_id}` | Assigns an escalation; omitted ID means the current operator |
| POST `/ui/ops/cases/{id}/resolve` | `{reason}` | Resolves an escalation assigned to the current operator |
| POST `/ui/ops/conversations/{id}/takeover` | None | Changes AI to HUMAN and records the responsible operator |
| POST `/ui/ops/conversations/{id}/messages` | `{text,client_request_id}` | Persists an OPS reply; requires HUMAN mode and ownership |
| POST `/ui/ops/conversations/{id}/notes` | `{text,client_request_id}` | Persists a private OPS note on an active thread |
| POST `/ui/ops/conversations/{id}/handoff` | None | Explicitly returns safe, owned HUMAN threads to AI |
| POST `/ui/ops/conversations/{id}/resolve` | `{reason}` | Resolves a safe, owned HUMAN thread |

Reasons and text must be nonblank. `client_request_id` must be a UUID generated once
by the client and reused for retries. Concurrent identical requests return the same
message; conflicting key reuse returns HTTP 409. Messages include `operator_id`.
Ops history includes internal notes; rider history, summaries, agent context, and
public traces exclude their text. Notes are never transmitted to messaging vendors.
The message table is the source of truth for future simulator integration.

Approvals lock the rider, conversation, dispute, and case; recheck canonical CSV
coverage, item evidence, eligibility, full balance, prior intents, and provider ledger
through the existing authorization service. Existing or ambiguous payments, changed
amounts, missing provenance, settled disputes, and conflicting decisions return HTTP
409. Provider access here is GET-only. Approval state, operator, timestamp, audit, and
payment intent commit together or roll back together. No client-selected payment amount
is used. A ₹425 balance produces one ₹425 OPS_APPROVED intent, never automatic fragments.
The existing durable worker executes and confirms payments later.

Takeover and agent writes share the rider lock. Takeover increments a persisted control
version, assigns the operator, and finalizes pending incoming jobs with a support
acknowledgement. Every agent write and authorization boundary rechecks ownership, mode,
lease, and control version. Old executions cannot resume after takeover followed by
handback. Incoming HUMAN-mode messages remain persisted without invoking the LLM.
Already-authorized payment intents remain durable; takeover does not cancel payments
that were authorized before it committed.

Handback and resolution reject unresolved approvals/escalations, sensitive investigations,
identity/security flags, and pending/uncertain/manual-review payments. Reviewed escalation
resolution records the reason and closes that investigation without issuing money.
Resolved conversations retain history. Subsequent rider messages create a fresh thread.
Handback never replays old messages or starts a payment.

## Schema and verification

Revision `ef5a812c731a` adds `ops_sessions`, `ops_login_limits`, conversation operator and
control-version fields, and message author/idempotency fields. These are additive;
existing rows remain valid. No assignment datasets or PaySwift sandbox code change.
Authentication needs two small tables so revocation and rate limits work across processes.

Endpoint tests exercise sessions, all protected routes, financial conflicts, real CSV
₹425 evidence, concurrent decisions, message retries, private notes, in-flight graph
and authorization fencing, handback blockers, and resolution lifecycle. PaySwift uses
an in-process mock; tests do not execute payouts. Tests migrate and roll back only
uniquely named disposable databases. Run:

```sh
make lint
make test
```

Frontend wiring, SSE, outbound messaging, and a public deployment authentication boundary
for the assignment interfaces remain outside this milestone.
