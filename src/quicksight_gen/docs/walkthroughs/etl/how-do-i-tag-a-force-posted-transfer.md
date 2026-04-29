# How do I tag a force-posted external transfer correctly?

*Engineering walkthrough — Data Integration Team. Extension.*

## The story

Most postings the bank makes originate inside the bank — an
operator at SNB initiated the ACH, the wire, the internal transfer.
A handful of postings are *forced on us* by an external system: the
Fed pushes an inbound ACH credit before our origination side caught
up; the card processor reports a settlement before our internal
catch-up posts. The bank still has to record those rows in
`transactions` (otherwise the GL is wrong), but they're a different
*kind* of posting.

The schema captures this with the `origin` column. Two values:

- `internal_initiated` — the bank started this. The default for
  almost every row.
- `external_force_posted` — an external system started this; we
  recorded it for GL parity. The minority case.

Get this tag wrong on Fed-statement ingest and the AR
*GL vs Fed Master Drift* check (and its siblings) misclassify the
row, silently under-firing on real exceptions.

## The question

"My Fed-statement loader has a row that doesn't have a matching
SNB-internal posting yet. What do I write in `origin` and what
`metadata` do I attach so the AR drift checks see it as
'Fed-side, internal catch-up pending' instead of as a real
exception?"

## Where to look

Two reference points:

- **`quicksight-gen demo etl-example account-recon`** — Pattern 2
  ("Force-posted ACH from the Fed") is the canonical projection.
  Strip the sentinel suffix and wire to your Fed-statement parser.
- **`docs/Schema_v6.md` → `origin` column spec** — the per-value
  failure-mode notes describe exactly which checks under-fire when
  you skip `external_force_posted`.

## What you'll see in the demo

Run:

```bash
quicksight-gen demo etl-example account-recon -o /tmp/ar-examples.sql
```

Pattern 2 in the output is the full INSERT for an inbound Fed ACH
credit that hasn't matched an outbound SNB origination yet. Two
columns drive the classification:

```sql
'external_force_posted',                       -- origin column
JSON_OBJECT(
    'source'            VALUE 'fed_statement', -- metadata key
    'statement_line_id' VALUE 'fed-stmt-2026-04-20-line-042'
)                                              -- metadata column
```

`origin` is the structural switch the drift-split logic reads.
`metadata.source` is the provenance tag that lets exception
walkthroughs explain *which upstream system* generated the row.
Both are required.

## What it means

The AR exception layer treats the two `origin` values
asymmetrically:

1. **`origin = 'internal_initiated'` rows are subject to the full
   set of AR exception checks** (drift, non-zero transfers, limit
   breach, overdraft). If an internal posting is wrong, *the bank*
   is wrong, and an operator should investigate.
2. **`origin = 'external_force_posted'` rows are excluded from
   "operator initiated drift" checks but *included* in the "is the
   Fed ahead of us?" checks**. Specifically:
   - **GL vs Fed Master Drift** counts a day where the *sum* of
     `external_force_posted` Fed-card rows on `gl-1815` doesn't
     equal the *sum* of internal catch-up postings.
   - **Fed Activity Without Internal Post** lists individual
     `external_force_posted` rows that have no follow-up internal
     posting after a grace period.
   - **ACH Sweep No Fed Confirmation** is the inverse: an internal
     ACH origination posted but no `external_force_posted` Fed
     confirmation arrived.

So the wrong tag flips the row from one check to its opposite — or
out of all checks entirely. There's no benign default.

## Drilling in

The decision tree for any row your loader sees:

- **The bank started it (operator, scheduler, internal automation):**
  `origin = 'internal_initiated'`. Default for ~99% of rows.
- **An external system started it and we're recording for GL parity:**
  `origin = 'external_force_posted'`. `metadata.source` should name
  the upstream (`'fed_statement'`, `'card_processor'`,
  `'wire_correspondent'`, etc.).

A subtlety on the `parent_transfer_id` chain: when an external
force-post *eventually* gets matched by an internal catch-up,
**the catch-up's `parent_transfer_id` should point at the
force-post's `transfer_id`**, not the other way around. The Fed
row is the parent; the internal catch-up is the child. This is the
opposite direction of the PR sale → settlement chain (where the
sale is the child of its settlement) and easy to get backwards.

Concretely, for a Fed-pushed inbound ACH followed two days later by
an SNB origination catch-up:

```sql
-- Day 0: Fed force-posts. Pattern 2 from etl-example.
INSERT INTO transactions (..., transfer_id, parent_transfer_id, origin, ...)
VALUES (..., 'fed-xfer-EXAMPLE-001', NULL, 'external_force_posted', ...);

-- Day 2: SNB catch-up posts. parent_transfer_id points at the Fed row.
INSERT INTO transactions (..., transfer_id, parent_transfer_id, origin, ...)
VALUES (..., 'snb-xfer-EXAMPLE-042', 'fed-xfer-EXAMPLE-001',
            'internal_initiated', ...);
```

Skip the parent link on the catch-up and the chain integrity check
in the validation walkthrough flags an orphan; the GL drift check
on day 2 won't subtract correctly because it can't tell that
`snb-xfer-EXAMPLE-042` is "the catch-up for" the Fed row.

## Next step

Once your Fed-statement projection is wired up:

1. **Verify Pattern 2's tag pair lands correctly**. Pull a sample
   Fed force-post row from your loaded data and confirm both
   `origin = 'external_force_posted'` AND `JSON_VALUE(metadata,
   '$.source') = 'fed_statement'` are set. Either alone is wrong.
2. **Run the day-0 + day-N pre-flight against the chain**. Use the
   orphan-parent query (Invariant 3 in the validation walkthrough)
   on a window that covers your longest expected catch-up lag —
   typically 5 business days for ACH, 1 day for card.
3. **Open AR Exceptions and inspect the Fed-related KPIs**. If
   *GL vs Fed Master Drift Days* spikes after a Fed-statement
   load, you're either missing the catch-up postings (real
   exception) or your Fed rows are tagged
   `internal_initiated` (tag bug — they get counted as bank
   activity instead of Fed activity).

## Related walkthroughs

- [How do I populate `transactions` from my core banking system?](how-do-i-populate-transactions.md) —
  the foundational projection. This walkthrough is its
  Fed-statement variant.
- [How do I prove my ETL is working before going live?](how-do-i-prove-my-etl-is-working.md) —
  Invariant 3 (parent-chain integrity) is the pre-flight check
  for the catch-up linkage described here.
- AR Exceptions: GL vs Fed Master Drift —
  the **downstream consumer**. Read this to understand what a
  correctly tagged Fed row enables.
- AR Exceptions: ACH Sweep No Fed Confirmation —
  the inverse case (we posted, Fed didn't confirm) — also reads
  the `origin` tag.
- [Schema_v6 → `origin` column spec](../../Schema_v6.md#table-1-prefix_transactions) —
  the column-contract details.
