# Controlled source normalization and PostgreSQL synchronization

The original `data/riders.csv`, `data/trips.csv`, `data/payout_lines.csv`, policy
and reference conversations remain unchanged. This stage persists the previously
approved effective distance for one trip, while preserving historical payouts.
No tables, schema migrations, extra services or dependencies are introduced.

## Modules and commands

- `app/data_quality/rules.py`: the two approved rider aliases, the exact trip
  correction fingerprint and review-only threshold.
- `normalize.py`: validated, deterministic source pipeline and effective trip
  values, independent of fare calculations.
- `audit.py`: numerical and historical-payment evidence for the unit hypothesis.
- `report.py`: immutable classification, issue and transformation types.
- `sync.py`: plan, history checks, locking and controlled writes.
- `app/scripts/sync_data.py`: explicit dry-run/apply CLI; existing seed and audit
  entry points reuse the same approved rules.

From `backend/`:

```sh
uv run python -m app.scripts.sync_data --dry-run --report reports/data_quality.dry-run.json
# Inspect conflicts, target, proposed operations, and source hashes first.
uv run python -m app.scripts.sync_data --apply --report reports/data_quality.json
# Repeat explicitly to verify that no additional writes are necessary.
uv run python -m app.scripts.sync_data --apply --report reports/data_quality.repeat.json
```

Neither mode rewrites the source CSVs. Explicit `--data-dir` and `--report` paths
are supported; default paths resolve from the project, independently of the
shell's starting directory. Normalized CSV exports are unnecessary here and are
not generated. The normalization bundle and reports provide reproducible
canonical records without creating a second competing source of truth.

## Classification and counts

Original rows: **6,576** (40 riders + 3,314 trips + 3,222 payout lines).
Canonical unique records: **6,566** (40 + 3,304 + 3,222).

| Classification | Unique records | Meaning |
| --- | ---: | --- |
| VALID | 6,280 | Structurally valid source values retained |
| CORRECTED | 65 | 64 approved rider references and one approved distance |
| REQUIRES_REVIEW | 221 | Distance units remain materially unverified |
| INVALID | 0 | No current mandatory structural violations |

Ten identical duplicate trip rows are excluded from the canonical rows and
reported individually with source row numbers. Conflicting duplicates or
unresolved rider identifiers block synchronization rather than choosing one.
All 3,222 payout lines remain distinct, including 150 negative penalty lines and
four groups containing repeated −₹10 deductions. Those deductions are financial
facts to reconcile, not duplicates the importer may delete. The 16 missing trip
credits and four repeated-penalty groups remain separate financial investigation
signals; structurally valid historical payout records are not relabeled invalid.

## Approved rules

1. `APPROVED_RIDER_ALIASES_V1`: only `R7 -> R007` (38 source rows) and
   `r19 -> R019` (26 rows). Both canonical IDs must exist in `riders.csv`;
   ambiguity and other unknown references fail. The same rule applies to trip
   and payout references. Rider primary keys are never renamed or merged.
2. `IDENTICAL_SOURCE_ID_KEEP_FIRST_V1`: retain one identical trip row per source
   ID; record every skipped source row. Conflicting values stop normalization.
3. `T312538_VERIFIED_METRES_TO_KM_V1`: only trip `T312538`, rider `R031`, completed
   at `2026-09-18T04:47:00Z`, raw distance 5000, surge 1.5, is corrected to Decimal
   5 km. The user explicitly approved this record. A changed fingerprint is not
   corrected. The distance rule contains no fare or payout answer. Canonical 5 km
   values retain provenance on subsequent financial reads.

## Distance investigation and limits

All 222 unusual distances are integers and multiples of 100. They occur in only
five rider groups: R031 (33), R032 (46), R038 (51), R039 (48), R040 (44). Statuses:
204 completed, 14 rider cancellations, 4 customer cancellations. Dividing these
numbers by 1,000 would yield 0.8–11.4 km, overlapping the ordinary 0.8–13.0 km
range. Among completed trips, that hypothetical interpretation matches the
historical surged policy fare in 202 cases; the other two match the hypothetical
unsurged fare.

This is strong evidence of a clustered source-format problem, but a payout
export can contain errors and reference outcomes are not independent proof of a
trip's physical distance. **No general conversion has been approved.** The
report labels the candidate distances as hypotheses, never effective values.
Only the approved record-specific correction is applied. The remaining 221
records retain their raw database numbers, while their normalized **effective
financial distance is unknown**. The current schema has no persisted quality or
raw/effective columns; this limitation is represented in the report and
validated normalization layer, not concealed through fabricated values or new
tables. Existing payout history is never used to infer a distance automatically.

## Synchronization safety

The CLI is restricted to the local development/Compose PostgreSQL host and reports
actual database/role/server identity without passwords. Dry-run uses a
repeatable-read, read-only transaction. It reports source/database differences,
proposed inserts/updates/skips, conflicts and decision-history counts.

Apply recomputes the complete plan in one transaction. It takes
`SHARE ROW EXCLUSIVE` locks on source tables and `SHARE` locks on decision/history
tables before inspecting state. A five-second lock timeout avoids indefinite
blocking. These maintenance locks stop concurrent writers from introducing a
financial decision between validation and the update. Ordinary reads can
continue. PostgreSQL's lock behavior is documented in its
[explicit-locking reference](https://www.postgresql.org/docs/16/explicit-locking.html).

Rules for existing data:

- Equal canonical records are skipped; there is no unconditional upsert.
- Missing source records may be inserted in FK order (riders, trips, payouts).
  Review-classified trips preserve their raw storage value; this is not an
  effective-distance attestation.
- The only supported UPDATE is the exact approved trip-distance correction.
- Rider names, identities, existing payout rows and relationships are never
  overwritten. Unexpected differences block the whole batch.
- The current immediate composite foreign keys do not support a speculative
  multi-row ownership rewrite. An existing rider-reference mismatch is reported
  for manual handling, rather than adding a migration or merging riders.
- Any dispute, payment intent (including FAILED/UNKNOWN), trace, message or
  nonempty conversation context for a rider whose financial source basis would be changed or newly introduced
  blocks apply. This intentionally conservative rider-level check catches
  legacy/unscoped history where exact trip attribution is not yet reliable. It
  may require manual review for unrelated history on that same rider; it never
  rewrites old decisions silently. Other riders' history does not block apply.
- No deletes, truncation, volume resets, payout updates or payment execution occur.

A complete plan is written before transaction commit. After success the report
is marked `applied`. `applied_in_transaction` in an interrupted report requires
checking PostgreSQL with a new dry-run before assuming whether commit completed.
Source fingerprints are rechecked during normalization; reports preserve raw
source hashes, before-values and rule identifiers. An aborted transaction rolls
back every change. After-commit reversal is a manual maintenance operation:
recheck the same decision-history protections and full trip fingerprint, then
conditionally restore only distance 5 to the original CSV value 5000 in a
transaction. Never reverse against newly created financial history or restore a
whole database over unrelated records.

## Financial integration

The data-access/normalization layer produces validated effective trip values
and quality metadata before policy calculations. Items distinguish `VALID`,
`CORRECTED`, `REQUIRES_REVIEW` and `INVALID`; ambiguous completed-trip earnings
return structured `REQUIRES_REVIEW` issues with unknown effective distance and
no positive verified adjustment. Invalid/conflicting sources are separately
identified. Known-corrected records retain the original 5000 -> 5 provenance,
even after PostgreSQL stores 5.

Only materially affected components are blocked: an unrelated valid trip,
verified cancellation penalty or daily completed-trip count is not rejected
because another trip has ambiguous distance units. Claims still need trusted
rider identity, eligible historical `received_at`, complete source coverage and
provider payment reconciliation. `T312538` derives ₹65 expected, ₹43 historical
paid and ₹22 shortfall using the unchanged policy calculator. No payout amount
is encoded in normalization rules, and payment authorization remains false.

The complete machine-readable artifacts are under `backend/reports/`; the
original raw-only audit under `backend/docs/` remains a reproducible source audit.
