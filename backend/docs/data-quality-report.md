# Source-data quality audit

The audit reads all three original assignment CSVs and makes no source or
database changes. The reproducible [JSON report](data-quality-report.json)
contains file SHA-256 hashes, individual findings, source row numbers and the
approved financial transformation. Run from `backend/`:

```sh
uv run python -m app.scripts.audit_data --output docs/data-quality-report.json
```

The audit uses explicit review-only screens: distance above 100 km, surge above
3, and absolute historical payout above ₹1,000. These are diagnostic heuristics,
not official financial-policy limits or permission to change records.

| Dataset | Original rows | Unique source identifiers |
| --- | ---: | ---: |
| riders.csv | 40 | 40 |
| trips.csv | 3,314 | 3,304 |
| payout_lines.csv | 3,222 | 3,222 |

## Newly approved correction

The user verified that **only `T312538`** stores distance in metres. Its entire
trip fingerprint must match: rider `R031`, timestamp
`2026-09-18T04:47:00Z`, status `completed`, raw distance `5000`, surge `1.5`.

| Field | Original | Financial read value |
| --- | --- | --- |
| distance_km | 5000 (verified as metres) | Decimal 5 km |

Rule: `T312538_VERIFIED_METRES_TO_KM_V1`.
Source: `trips.csv`, row **1979** (header is row 1).

This correction runs at the financial read boundary on an immutable copy.
The original CSV remains **5000**. Controlled synchronization may persist
the approved effective distance **5** in PostgreSQL after history checks; the
normalization report preserves the original value and update plan. Rider, trip ID,
timestamp, status and surge are unchanged. The result records transformation
provenance; the JSON report records the same rule and source values. Other trips
and changed fingerprints receive no conversion. The rule is idempotent.

The unchanged official formula yields:

`ROUND_HALF_UP((25 + 6 × (5 − 2)) × 1.5) = ₹65`.

Historical payout `PL002492` is ₹43, yielding **₹22 verified shortfall**. The
amount is computed, never hardcoded into the engine. Confirmed outstanding also
requires the existing independent provider-history checks; the correction never
authorizes a payment.

## Additional findings — reported without new corrections

| Finding | Result | Treatment |
| --- | --- | --- |
| Unusual distances | 222 unique trips: 204 completed, 14 rider cancellations, 4 customer cancellations | The one approved correction leaves **221 uncorrected**, including 203 completed trips. Values range up to 11,400; verify source units individually. |
| Duplicate trip IDs | 10 additional rows with identical data; no conflicting duplicates | Original rows remain. Existing seed behavior skips identical primary keys. |
| Inconsistent rider IDs | 38 references to `R7`, 26 to `r19` | Previously approved reference mappings to existing `R007`/`R019` remain in the importer; no other mappings were added. |
| Repeated penalty deductions | Four logical sources have two distinct −₹10 lines each | Preserve both historical deductions; investigate as financial discrepancies. |
| Completed trips without a trip payout line | 16 unique trips | Investigate missing payments; do not fabricate or insert payout history. |
| Negative amounts | 150 lines, all cancellation penalties | Expected signed history, not data to replace or drop. |

Repeated penalty groups:

| Rider | IST date | Trip | Historical line IDs |
| --- | --- | --- | --- |
| R001 | 2026-09-19 | T429673 | PL000068, PL000069 |
| R014 | 2026-09-18 | T637155 | PL001119, PL001120 |
| R027 | 2026-09-21 | T936237 | PL002152, PL002153 |
| R030 | 2026-09-20 | T815454 | PL002420, PL002421 |

Duplicate trip IDs: T262030, T218759, T776568, T461379, T115545, T859610,
T310191, T667164, T758181, T152720. Both CSV row numbers appear in the JSON report.

Trips without trip payout lines: T121056, T158281, T206956, T409395, T417277,
T472165, T481678, T504613, T563729, T618128, T621978, T795007, T863754, T900949,
T954299, T967216. Absence is a reconciliation finding; it does not prove why a
payment is missing or authorize an adjustment.

## Checks with no additional findings

Across the actual source files, the audit found no invalid trip statuses or
payout line types, malformed/blank required fields, invalid or naive timestamps,
invalid dates, nonfinite numbers, negative distances, nonpositive surge values,
negative non-penalty amounts, nonnegative penalty lines, zero or fractional
payout amounts, conflicting duplicate IDs, unknown trip references, remaining
unknown rider references after approved alias resolution, rider/trip ownership
mismatches, payout/trip date mismatches, trip payments on cancelled trips,
penalties without rider cancellations, trip dates before rider joining, or
incentives incorrectly tied to a trip. No surge/payout review-screen exceedances
were found. Penalty deductions sharing a logical source remain separate records.

All further corrections require verification and explicit approval. Neither the
audit nor the approved distance rule re-seeds, updates or truncates history.

See [controlled-normalization.md](controlled-normalization.md) for the newer
classified source pipeline, systematic distance analysis and guarded
PostgreSQL synchronization reports under `backend/reports/`.
