# Reproduction

Use a fresh disposable Compose project and volumes. Never reuse the developer's
normal database or PaySwift ledger. Source `.env` remains ignored; supply your own
model credentials and local-only database password.

```sh
docker compose -p quickdrop-remediation up --build -d
docker compose -p quickdrop-remediation run --rm seed
python evals/run.py http://localhost:8000 --payswift-url http://localhost:8081
```

If local ports are occupied, use a Compose override with separate published API,
frontend, provider, PostgreSQL and Redis ports. The executed run used 18000, 13000,
18081, 15432 and 16379. Root Compose uses project-scoped networks and volumes.
The two complete HTTP runs have independent, fresh project state. Shared rider
scenarios inside a suite compare the same obligation and cumulative provider ledger.

The internal live audit accepts `AUDIT_REPORT_DIR` and `AUDIT_LOG_DIR` so new evidence
never overwrites the original audit. Exact command and result definitions are in the
remediation report. Use `LLM_PROVIDER=amazon`, foreground budget 7, and real Nova
credentials; it creates fresh per-case databases/providers and cleans them up.

Checks:

```sh
uv run --directory backend pytest -q
uv run --directory backend ruff check .
uv run --directory backend ruff format --check .
python -m unittest discover -s evals -p test_run.py
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

Only after preserving evidence, remove the disposable project with
`docker compose -p quickdrop-remediation down --volumes`. Never substitute the normal
project name. Supplied PaySwift keeps its ledger in memory; its restart erases that
sandbox ledger and must never be treated as proof that an existing obligation was unpaid.
