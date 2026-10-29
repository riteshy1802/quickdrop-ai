# Reproducing this audit

From repository root:

```sh
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
npm --prefix frontend run lint
npm --prefix frontend test
npm --prefix frontend run typecheck
npm --prefix frontend run build
uv run --directory backend python ../evals/audit_live.py
python evals/build_audit_report.py
```

Keep the current evidence folder before repeating the live audit. The audit harness
requires local PostgreSQL CREATEDB, the existing locked backend environment, the
configured real LLM credentials, Docker and a local redis:7-alpine image. It creates
fresh cloned DBs and fresh supplied sandbox processes, preserves scenario identities
and original timestamps, and uses actual FastAPI ASGI HTTP routes. It does not use
browser automation or alter the application's prompts/policy/data. Real model calls
may incur API charges; the provided sandbox transfers are simulated only.

The portable `evals/run.py URL` command is missing and deliberately reported FAIL.
The internal harness depends on backend internals and therefore cannot replace it.
The report's delivery result requires the original webhook reply to be final; eventual
worker completion plus polling/replay is reported separately. Inspect JSON evidence
rather than treating a process exit code as a count of passed official scenarios.
