# Controlled normalization — execution summary

Status: **APPLIED** to local PostgreSQL `quickdrop` at `localhost:5432`.
The dry-run was inspected before apply. All decision/history tables were empty;
no prior financial basis was overwritten.

| Metric | Result |
| --- | ---: |
| Original source rows audited | 6,576 |
| Canonical unique records | 6,566 |
| VALID | 6,280 |
| CORRECTED | 65 |
| REQUIRES_REVIEW | 221 |
| INVALID | 0 |
| Identical duplicate trip rows skipped | 10 |

Rules: the two approved rider aliases (64 references), identical-trip-ID
deduplication, and the exact approved `T312538` distance correction (5000 -> 5).
No other distance was converted. These are source normalization counts; the
rider aliases were already canonical in PostgreSQL before this synchronization.

| PostgreSQL operation | First apply | Repeat apply |
| --- | ---: | ---: |
| Inserted | 0 | 0 |
| Updated | 1 | 0 |
| Unchanged/skipped | 6,565 | 6,566 |

The sole update was `trips.T312538.distance_km`: 5000 -> 5. Before and after row
counts are 40 riders, 3,304 trips and 3,222 payout lines. Every live source record
was compared to the normalization bundle after apply. Historical payout rows,
negative penalties, repeated deduction line IDs and all original CSV hashes
are unchanged. The financial engine derives ₹65 expected, ₹43 paid and ₹22
historical shortfall, with CORRECTED provenance. Independent provider-history
checks remain necessary before an outstanding amount can authorize any payment.

Evidence and unresolved work:

- All 222 unusual distances are integer multiples of 100, clustered in R031,
  R032, R038, R039 and R040. A hypothetical /1000 interpretation gives 0.8–11.4 km.
- 202 completed-trip historical payouts match that hypothetical policy fare;
  two match the hypothetical unsurged fare. This supports a format hypothesis,
  not independent proof of physical distances or approval for a general rule.
- **221 distances remain REQUIRES_REVIEW**, with no effective distance fabricated.
- Four repeated-penalty groups and 16 missing trip credits remain financial
  investigation findings; all source payout records are preserved.

Artifacts:

- [Inspected dry-run](data_quality.dry-run.json)
- [Applied normalization and synchronization report](data_quality.json)
- [Zero-write repeat report](data_quality.repeat.json)
- [Rules, safety checks and rollback limitations](../docs/controlled-normalization.md)
