# Deterministic financial reconciliation

The financial engine reads trusted rider identity, message `received_at`, an
explicit claim scope and source records. It neither writes disputes/payments nor
authorizes a transfer. No LLM, PaySwift HTTP client, Redis or worker is involved.

## Entry points

- `app/services/financial/calculator.py`: pure completed-trip fare, cancellation,
  per-trip rounding, exact sums and group totals.
- `incentive.py`: unique completed-trip counts on IST dates and one ₹150 incentive
  at 12 or more completed trips.
- `eligibility.py`: ownership, seven-day window and distance review screen.
- `types.py`: immutable Pydantic request, source, payment evidence and result models.
- `reconciliation.py`: `reconcile_records()` for pure calculations;
  `await reconcile(session, request, source_data_complete=...)` for PostgreSQL.
- `app/repositories/financial.py`: batched SELECTs for source trips/payouts and
  existing rider disputes, items and payment intents. No policy math in SQL.

Example, after setting up the normal async session:

```python
from datetime import datetime
from app.services.financial.reconciliation import reconcile
from app.services.financial.types import ClaimRequest

request = ClaimRequest(
    rider_id="R003",  # trusted account identity, never extracted from chat
    received_at=datetime.fromisoformat("2026-09-22T09:05:00+05:30"),
    trip_ids=("T926334",),
)
result = await reconcile(session, request, source_data_complete=True)
print(result.model_dump_json(indent=2))
```

This example verifies expected ₹74, historical paid ₹49 and historical shortfall
₹25. Its outstanding balance remains `null` until provider payment history is
reconciled. JSON serializes Decimal values as exact strings, consistent with the
existing read APIs. No new HTTP endpoint is added in this milestone.

Claim scopes may combine `trip_ids`, `trip_dates` (all trip components for those
IST dates), `penalty_dates` (penalty deductions/cancellations), and
`incentive_dates`. Repeated scope keys produce one item per logical source.
Unknown trip dates stay `null`; they are never invented. Empty scopes and missing
daily records require more information.

## Policy interpretations

`docs/policy.md` remains authoritative and unchanged:

- Completed fare: `25 + 6 * max(0, distance_km - 2)`, multiplied by surge over the
  whole fare, then rounded **per trip** with Decimal `ROUND_HALF_UP`.
- Rider cancellations: −₹10. Customer cancellations: ₹0. Neither earns a normal
  trip fare or counts toward incentive eligibility.
- Incentive: exactly ₹150 once per qualifying IST date, not once per trip.
- The seven-day ambiguity is resolved as the **seven completed IST dates before
  the incoming received_at date**: age 1 through 7 inclusive. Today, future dates
  and age 8+ are ineligible. No wall-clock date is used. UTC timestamps are
  converted using `Asia/Kolkata` before comparing calendar dates.

Pure monetary functions require finite Decimal values and reject floats.
Arithmetic uses its own precision/rounding context, so caller changes to Python's
global Decimal context do not change results. Individual trip rounding happens
before aggregation. Group totals do not implicitly include daily incentives.

## Source quality and the reference discrepancy

The caller must explicitly attest `source_data_complete=True` only when the
selected source export/ingestion covers the claim scope. It is not a rider/LLM
assertion. Without it the engine cannot infer missing pay from absent records.

Independent of fare policy, completed-trip distances above **100 km** enter
manual source-unit review. This is a conservative data-quality screen, not a
fare cap: the pure calculator remains uncapped. No generic distance scaling or
unit inference is performed. Cancellation penalties and incentive counts do
not depend on distance, so this screen does not change those calculations.

The user explicitly verified one exception: `T312538` stores **5000 metres**,
meaning **5 km**, despite the CSV column being named `distance_km`. The pure
`normalization.normalize_trip_record()` function applies only to this complete
fingerprint:

- Trip `T312538`, rider `R031`, status `completed`.
- Timestamp `2026-09-18T04:47:00Z`.
- Raw distance `5000`, surge `1.5`.

The rule `T312538_VERIFIED_METRES_TO_KM_V1` substitutes Decimal `5` in an
immutable financial read record. The controlled synchronization stage may also
persist that approved effective value in PostgreSQL; the CSV and all other
trip fields are preserved. Changed fingerprints and other trips receive no
correction. Applying the rule a second time has no effect. Original conflicting
records remain conflicts even if their normalized values would agree.

Policy arithmetic then derives **₹65 expected pay**, **₹43 historical paid** and
**₹22 verified shortfall**. No adjustment amount is encoded in the correction or
financial engine. Outstanding is ₹22 when provider history is explicitly
confirmed complete with no subsequent payment; it remains unknown by default.
Controlled synchronization may now persist the approved 5 km value after
history checks; original 5000 remains in the CSV and normalization report.
The result includes `data_quality_transformations` with rule ID, source ID,
original/normalized values and the verification reason.

The raw source has 222 unusual-distance trips (204 completed). Only this one is
approved: 221 other unusual distances, including 203 completed trips, remain
uncorrected. See [data-quality-report.md](data-quality-report.md) for the audit
summary and [data-quality-report.json](data-quality-report.json) for every
finding, source row and SHA-256 hash. No additional normalization is authorized.

Conflicting duplicate source IDs, wrong-date trip payout lines, unexpected line
signs, unknown trips, foreign ownership and incomplete coverage cannot produce a
positive verified adjustment. Identical repeated copies of one source ID count
once; distinct payout line IDs count independently, including duplicate penalty
deductions. Trip payouts are matched by rider, trip, line type and service date.
Incentives are matched by rider and IST date, regardless of any trip reference.
Wrong-date trip entries are fetched and flagged rather than silently dropped.

## Amounts and payment evidence

Each item exposes:

- `expected_amount`: official policy amount for this logical source.
- `historical_paid`: signed amount from the source payout lines.
- `raw_difference`: expected minus historical paid.
- `verified_shortfall`: `max(0, raw_difference)` for verified, eligible sources.
- `confirmed_adjustments`: subsequent provider-confirmed credits allocated to
  exactly this source and date.
- `outstanding`: remaining nonnegative shortfall after those confirmed credits,
  or `null` if source/payment reconciliation is incomplete.

Totals sum positive shortfalls **per item**. An unrelated overpayment never
cancels another trip's shortfall. Overpayment has an explanation and creates no
negative payment request. A partial/ineligible result may expose valid item
shortfalls, but its aggregate outstanding is unknown; inspect the item outcomes.

`PaymentEvidence` defaults to `provider_history_complete=False`. Complete or
confirmed evidence must name the trusted `rider_id`; evidence for another rider
is rejected for accounting and requires reconciliation. The future
trusted PaySwift reconciliation layer may supply complete provider history and
`ConfirmedPayment` evidence with stable provider IDs and exact source/date
allocations. Allocation amounts must sum to the confirmed payment amount.
Repeated identical provider evidence is counted once; conflicting evidence is
blocked. Credits for other sources are never subtracted from the current item.

The persisted item identity convention is `(source_type, source_id)`:
`trip`/`penalty` use the trip ID, `incentive` uses the ISO IST date. Existing penalty
items referencing one historical deduction line are also matched to the parent
trip's penalty item. Future writers must preserve this convention.

Existing PENDING, AWAITING_APPROVAL, PROCESSING, UNKNOWN, NEEDS_REVIEW, FAILED or
unconfirmed SUCCEEDED intents block another adjustment. FAILED never frees a
reservation here. SUCCEEDED only counts as confirmed when provider ID, intent
identity/amount and source allocations agree with supplied trusted evidence.
UNKNOWN remains blocked even if supplied evidence suggests success: the future
payment reconciliation workflow must resolve that state explicitly. Resolved
claims without corroborating settlement, and prior payments without source
items, also block duplicate payment assumptions. Unscoped legacy claims require
manual attribution instead of arbitrary offsets.

`payment_authorized` is **always false**. Even a fully verified outstanding
amount requires the later authorization/payment layer to re-read provider state,
lock/revalidate current claims, enforce total owed, positive whole rupees, the
₹200 threshold and once-per-IST-day reservation, and reuse durable idempotency.
These read-only results are not concurrency-safe payment reservations. No
payment state or schema is changed in this milestone.

## Verification

Run from `backend/`:

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
```

Unit tests are database-free. PostgreSQL tests use the existing disposable test
database/transaction fixtures, seed the original assignment data, verify SELECT-
only integration and validate real reference amounts: ₹25 surge, ₹150 incentive,
₹10 duplicate penalty, ₹176 across two trips, ₹425 across five missing trips,
₹32 distance correction, normalized rider references, paid incentives and
ineligible claims. The approved R031 normalization, derived ₹22 result, full
fingerprint guard, idempotency and unchanged raw records are tested separately.

The controlled pipeline and synchronization safeguards are documented in
[controlled-normalization.md](controlled-normalization.md). Ambiguous financial
claims now expose `REQUIRES_REVIEW` and structured quality issues; corrected
records expose their approved provenance even after database synchronization.
