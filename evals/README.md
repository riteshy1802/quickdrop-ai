# Portable evaluator

Run `python evals/run.py http://localhost:8000` with Python 3.12 (standard library
only). No backend imports, database access or private UI endpoints are used.
`--payswift-url http://localhost:8081` changes the provider address; `--output FILE`
selects JSON output; `--scenario N` selects one original scenario.

Use a fresh disposable Compose project and provider ledger. Original messages,
IDs, timestamps, expectations and order are unchanged. The two R003 scenarios
refer to the same obligation: the full-suite comparison includes its existing
confirmed payment rather than issuing a second one. A rider with preexisting state
before its first suite scenario fails the isolation check. Never reset shared data.

Only explicit opt-in `--allow-nonlocal` permits a nonlocal URL. This is consent for
TEST infrastructure only, never permission to run against production. Both API and
provider destinations are checked. No credentials are accepted or printed.

Four independent results distinguish decision, authorization, provider settlement,
and original HTTP delivery. Trace formats beyond the assignment's fixed envelope
are implementation-specific: if structured financial evidence cannot be interpreted,
the result remains NOT VERIFIED, never inferred from rupee mentions in a reply.
Unavailable provider confirmation is likewise NOT VERIFIED. Polling the trace may
observe eventual completion; it cannot retroactively deliver a reply to the vendor.

`python -m unittest discover -s evals -p test_run.py` checks the standalone runner
against an incomplete HTTP server and verifies nonlocal refusal and outcome matching.
The internal `audit_live.py` additionally inspects isolated database state, exercises
human workflows, and records real model calls. It is not the portable evaluator.
