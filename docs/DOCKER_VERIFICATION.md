# Docker deployment verification

Verified 30 October 2026, Asia/Kolkata, from commit
`34b0573c761dae2882131ded3623b0eff09b56b2` plus the deployment changes in this
working tree. [Sanitized results](docker-verification-results.json) contain the
observed service states, counts, source hashes, and configuration statuses.

**Deployment smoke verification: PASS. Local runtime configuration validation: PASS.**
No actual dotenv values were displayed, copied into test configuration, or logged.
Docker supplied runtime configuration directly to the presence-only
validator and application checks. No command opened or parsed dotenv secrets
or dumped container environments.

## Changes

- The existing root `docker-compose.yml` remains the only deployment definition.
  API, worker, migration, readiness, and seed tasks share a project-specific backend
  image. Image identities were checked for the four persistent task containers;
  the seed task uses the same Compose anchor and was executed twice.
- Optional host-port overrides allow independent projects. Existing internal ports
  and service destinations remain unchanged. Published ports bind to loopback;
  remote access needs an explicitly configured reverse proxy. The supplied PaySwift
  application and compiled server are unchanged; only its host port mapping is
  configurable.
- Backend remains Python 3.12 with frozen UV dependencies and UID 10001. Frontend
  remains Node 22 with `npm ci`, a production build, and the non-root `node` user.
  Its runtime Next.js cache directory is now writable by that user.
- Build exclusions cover nested dotenv files, credential files, virtual environments,
  dependency directories, caches, and test output. Public `.env.example` files remain
  permitted. Root Git ignores protect dotenv variants while allowing examples.
- Root `.env.example` covers every backend setting, provider alternatives, worker
  options, Ops initialization, frontend proxy configuration, and optional host ports.
  README documents setup, environment precedence, validation, status, and logs.
- `app.scripts.check_env` reports only variable names and Configured / Missing /
  Invalid format. It disables dotenv reads itself; Compose supplies runtime values.
  Missing optional values use application defaults and do not fail validation.
  Pydantic exception strings now hide invalid input values.

## Environment readiness

All required environment variables passed the presence-only validation check (`app.scripts.check_env` exit code 0):

- `POSTGRES_PASSWORD`: Configured
- `OPS_ADMIN_EMAIL`: Configured
- `OPS_ADMIN_PASSWORD`: Configured
- `DEMO_SESSION_SECRET`: Configured (32+ characters for stable Rider cookies across API restarts)
- Selected LLM Provider (`AWS` or `GROQ`): Configured
- `REDIS_URL`: Configured
- `PAYSWIFT_BASE_URL`: Configured

Ops administrator settings and selected provider credentials were Configured.
An actual generic greeting through the configured provider returned successfully
inside the built backend image. No credential values or model response text were
included in evidence. This model check was separate from the disposable stack,
which used synthetic local credentials and no external model key.

## Executed checks

| Check | Result | Evidence |
|---|---|---|
| Compose services and build contexts | PASS | All nine required services; existing root file used with an isolated project directory. |
| Dockerfile syntax and dependencies | PASS | Backend, frontend, and supplied provider images built successfully. UV frozen install and `npm ci` executed. |
| Production frontend build | PASS | `next build` completed inside Node 22 image. |
| Python imports and runtime permissions | PASS | LangGraph, Groq, boto3, SQLAlchemy, Redis and asyncpg import; API/frontend non-root; frontend cache writable. |
| Shared backend image | PASS | API, worker, migration and readiness containers have the same image ID; seed uses the same image. |
| Complete startup | PASS | Both `up -d --wait` and `up --build -d --wait` completed. |
| Startup ordering | PASS | Migration/readiness tasks exited 0; API started after the dependency gates. PostgreSQL, Redis and API healthy. |
| HTTP endpoints | PASS | API `/health`, PaySwift `/health`, frontend `/rider`, `/ops`, and `/api/backend/health` returned 200. |
| Migration validation | PASS | `alembic current` and `heads`: `ef5a812c731a`; `alembic check`: no new operations. |
| Explicit seed and repeatability | PASS | 40 riders, 3,304 trips, 3,222 payout lines; second seed inserted zero rows. |
| Ops initialization and authentication | PASS | Repeated admin seed unchanged; login and authenticated `/auth/me` succeeded with generated test credentials. |
| Official messaging and persistence | PASS | Guarded nonfinancial `/messages` request accepted; same message ID returned cached reply; history persisted. |
| Trace and pending endpoints | PASS | `/trace/R003` returned trace structure; `/ops/pending` returned a list. |
| Worker connectivity | PASS | Running worker; container reached Redis and PaySwift; Redis Pub/Sub probe delivered its payload. |
| SSE and proxy streaming | PASS | Authenticated direct/proxy subscriptions became ready. Actual application events included message creation, agent status, reply deltas, reply completion and agent completion. |
| Restart recovery | PASS | API, worker, PostgreSQL and Redis restarted. Health/proxy recovered; Ops and Rider sessions remained usable; SSE reconnected and history refetched. |
| Persistence and duplicate safety | PASS | Restart retained 40/3,304/3,222 source rows, one conversation, two messages and zero intents. Subsequent streaming check added two messages and still zero intents. |
| Build-context exclusion | PASS | Synthetic nested dotenv and npm credential canaries absent from images after rebuild. No actual secret files were copied to test contexts. |
| Generated browser assets | PASS | No synthetic credential canary or recognizable AWS/Groq credential pattern found in browser chunks. This is a bounded check, not a complete secret-history audit. |
| Actual model connectivity | PASS | One generic greeting through the application's configured provider; no finance tools or database writes. |
| Existing local environment readiness | PASS | All required variables configured; validation exited 0. |
| Backend checks | PASS | 20 focused configuration, API and reference-clock tests; repository Ruff lint; changed Python files pass format check. |
| Frontend checks | PASS | 43 tests; ESLint; Next type generation and TypeScript check. |
| Payment execution | NOT TESTED | No payment initiated. Provider health/connectivity do not prove settlement. Earlier financial audit results remain separate. |
| All 24 assignment scenarios | NOT TESTED | Intentionally not repeated for this deployment task. |
| Browser end-to-end interaction | NOT TESTED | HTTP and component tests only; no browser opened. |

## Isolation and cleanup

Project `quickdrop-verify-2193366` used generated credentials, independent host ports,
network, volumes, and image tags. Application source was copied without actual
dotenv or credential files. Compose used the existing root definition with that
project directory; no override or second Compose file was created.

Before cleanup, volume ownership labels and container-name prefixes were verified.
Only disposable containers, volumes, network, image tags, and generated runtime
credentials were removed. Existing development PostgreSQL, Redis, and PaySwift
containers remained running. Original CSVs, agent code, financial calculations,
payment worker and supplied PaySwift files are unchanged.

## Setup commands

Copy `.env.example` to `.env` only for a new setup. Supply private credentials and
the shared session secret; do not overwrite existing environment files.

```sh
docker compose build api frontend
docker compose run --rm --no-deps api python -m app.scripts.check_env
docker compose up --build -d
docker compose run --rm seed
docker compose run --rm api python -m app.scripts.seed_admin
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 worker
```

The provider and migration gates run automatically. Seeding remains explicit.
Use `/rider` or `/ops` on port 3000 and `/health` on port 8000, unless host-port
overrides are configured. Next.js builds its proxy destination as
`http://api:8000`; browser requests use the same-origin `/api/backend` prefix.
