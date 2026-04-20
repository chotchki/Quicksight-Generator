# What do I do when the demo passes but my prod data fails?

*Engineering walkthrough — Data Integration Team. Debug.*

## The story

The demo dashboards work. You ran `demo apply`, opened both apps,
saw the planted exception scenarios light up the way they should.
You then wrote your own ETL against your own upstream feed,
loaded a slice into the same `transactions` and `daily_balances`
tables, and the dashboard looks *off* — KPIs at zero where they
shouldn't be, KPIs spiking where they shouldn't, visuals
rendering "N/A" where there should be values.

Almost every "demo works, prod doesn't" failure traces back to a
small set of root causes. This walkthrough is organized by
*symptom* — what you're seeing on the dashboard — so you can jump
to the matching diagnosis and check.

## The question

"My data is loaded but the dashboard doesn't look right. Where do
I start?"

## Where to look

Start at the symptom. Each section below names the visual
behavior, the most-likely root cause, and a one-shot SQL or CLI
check to confirm.

If a symptom matches more than one section, work top to bottom —
the earlier sections are more common and have cheaper checks.

## What you'll see (and what it means)

### Symptom 1 — "Every KPI on a sheet shows 0; the table is empty"

**Most likely**: the date filter on the sheet excludes everything
your load covers. Sheets default to a recent window (typically
the last 30 days) and your load may have used `posted_at` /
`balance_date` values outside that window.

**Check**:

```sql
SELECT MIN(balance_date), MAX(balance_date), COUNT(*)
FROM transactions
WHERE -- your scope filter, e.g.,
      account_id LIKE 'your-prefix-%';
```

If the date range is older than the sheet's default window, either
adjust the date filter on the sheet (top of the page) or backfill
your load with `balance_date` values inside the dashboard's
window.

### Symptom 2 — "A KPI shows 0 but I know exceptions exist in my data"

**Most likely**: the SQL filter the dataset applies excludes your
rows. AR datasets carry `WHERE transfer_type IN ('ach', 'wire',
'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')`;
PR datasets carry their own per-`transfer_type` filters. If your
ETL writes `transfer_type` values outside the inventory in
[Schema_v3.md → transfer_type catalog](../../Schema_v3.md#table-1-transactions),
the rows land but no dataset reads them.

**Check**:

```sql
SELECT transfer_type, COUNT(*)
FROM transactions
WHERE -- your scope filter
GROUP BY transfer_type
ORDER BY COUNT(*) DESC;
```

Compare against the `transfer_type` enum in Schema_v3. Any value
not in the enum is an orphan from the dataset's perspective.

### Symptom 3 — "A visual cell shows N/A or a column is blank"

**Most likely**: the visual reads a metadata key the rows don't
carry. Common when a new dataset is wired up against historical
rows that pre-date a key, or when an upstream feed inconsistently
populates an optional key.

**Check**: pick a metadata key the visual references — say
`card_brand` — and count rows missing it:

```sql
SELECT COUNT(*) AS rows_missing_key
FROM transactions
WHERE transfer_type = 'sale'
  AND -- your scope filter
  AND NOT JSON_EXISTS(metadata, '$.card_brand');
```

A non-zero count means the visual will render N/A for those rows.
Either backfill the key (one-shot UPDATE, see the metadata-key
walkthrough) or make the visual filter to rows that have it.

### Symptom 4 — "Drift KPI fires unexpectedly"

**Most likely**: your `daily_balances.balance` value disagrees
with the cumulative SUM of `signed_amount` in `transactions`.
Three sub-causes, in order of frequency:

1. **Sign-flip on one leg** — your upstream uses opposite sign
   convention from ours and the projection caught most legs but
   missed one branch.
2. **Missing posting** — the balance feed lands postings that
   never made it to the transactions feed (or vice versa).
3. **`balance_date` mismatch** — the balance row's
   `balance_date` doesn't line up with the `balance_date` your
   transactions used. Common when one feed snapshots at midnight
   UTC and the other at a local-time EOD.

**Check**: Pattern 5 of `quicksight-gen demo etl-example
account-recon` is the canonical drift recompute. Run it scoped
to the offending account-day to see the magnitude:

```sql
-- Substitute your account_id and balance_date.
SELECT
    db.balance                                       AS stored,
    COALESCE(SUM(t.signed_amount), 0)                AS recomputed,
    db.balance - COALESCE(SUM(t.signed_amount), 0)   AS drift
FROM daily_balances db
LEFT JOIN transactions t
  ON t.account_id    = db.account_id
 AND t.balance_date <= db.balance_date
 AND t.status        = 'success'
WHERE db.account_id   = 'your-account-id'
  AND db.balance_date = DATE 'your-date'
GROUP BY db.balance;
```

The sign of `drift` tells you which side is wrong:
positive = stored balance is higher than the postings explain
(missing debit posting, or a credit posting got dropped);
negative = the opposite.

### Symptom 5 — "PR pipeline drilldown returns nothing for my merchant"

**Most likely**: the `parent_transfer_id` chain has a gap. The
[Where's my money for merchant?](../pr/wheres-my-money-for-merchant.md)
walkthrough relies on traversing
`external_txn → payment → settlement → sale` via
`parent_transfer_id`. If any link is NULL where it shouldn't be,
the trace stops short.

**Check**: run Invariant 3 from the validation walkthrough scoped
to your merchant:

```sql
SELECT t.transfer_id, t.transfer_type, t.parent_transfer_id
FROM transactions t
WHERE JSON_VALUE(t.metadata, '$.merchant_id') = 'your-merchant-id'
  AND t.transfer_type IN ('payment', 'settlement', 'sale')
  AND (
      t.parent_transfer_id IS NULL
      OR NOT EXISTS (
          SELECT 1 FROM transactions p
          WHERE p.transfer_id = t.parent_transfer_id
      )
  );
```

Rows here are gaps. NULL means the link was never written
(common projection bug). Non-NULL but missing parent means the
parent landed in a different load batch and got cut by your
window filter.

### Symptom 6 — "Two-leg transfer doesn't show net-zero in the AR Non-Zero Transfers table"

**Most likely**: one of the legs has `status = 'success'` and the
other has `status = 'failed'` (or some third value the schema
doesn't recognize). The check filters `WHERE status = 'success'`
before summing, so a single-leg "success" looks unbalanced.

**Check**:

```sql
SELECT transfer_id, status, COUNT(*), SUM(signed_amount)
FROM transactions
WHERE transfer_id IN ( -- the offending transfer_ids from the table
)
GROUP BY transfer_id, status;
```

If a transfer has mixed statuses, the schema's expectation is that
both legs share status. Pick the right one (usually `failed` for
both if the transfer was rejected; `success` for both if it
posted) and republish.

## Drilling in

A few patterns that recur across symptoms:

- **Window filters on the load are the #1 cause of "missing
  parent" / "missing balance" failures.** When in doubt, expand
  your load window to cover the longest expected chain age (5
  business days for ACH, 30 days for unsettled PR sales).
- **`status` enum drift is the #1 cause of unexpected
  exceptions.** Anything that's not `success` MUST map to
  `failed`. A third value (`pending`, `void`, `reversed`) lands
  rows that downstream views can't classify.
- **Clock skew between feeds is the #1 cause of drift KPI
  surprises.** Standardize `posted_at` and `balance_date` on a
  single timezone before writing — don't let two feeds disagree
  on what "today" means.

## Next step

Once you've identified the root cause:

1. **Fix it in the projection, not in a one-shot patch.** A
   patched-up data state without a fixed projection regresses on
   the next load.
2. **Re-run the three pre-flight invariants** from the
   [validation walkthrough](how-do-i-prove-my-etl-is-working.md).
   They catch most of the symptoms above before the dashboard
   sees them.
3. **Add a regression query for your specific failure** to your
   ETL DAG. The pre-flight covers universal invariants; your
   feed has its own per-source invariants worth pinning.
4. **If you can't find the root cause**, capture: (a) one
   offending row from your feed, (b) the pre-flight query result
   that caught it, (c) the dashboard state. The combination is
   what someone needs to help you triage.

## Related walkthroughs

- [How do I populate `transactions` from my core banking system?](how-do-i-populate-transactions.md) —
  the foundational projection that most fixes go back to.
- [How do I prove my ETL is working before going live?](how-do-i-prove-my-etl-is-working.md) —
  the universal pre-flight checks. Most symptoms here are
  invariant violations the pre-flight would have caught.
- [How do I tag a force-posted external transfer correctly?](how-do-i-tag-a-force-posted-transfer.md) —
  the `origin` tag covers Symptom 4's drift surprises around
  Fed-statement ingest.
- [How do I add a metadata key without breaking the dashboards?](how-do-i-add-a-metadata-key.md) —
  Symptom 3 is most often a metadata-key contract violation.
- [Schema_v3 → minimum viable feed](../../Schema_v3.md#the-minimum-viable-feed) —
  the column-by-column failure modes are the source-of-truth for
  the symptoms above.
- [Where's my money for merchant?](../pr/wheres-my-money-for-merchant.md) —
  the analyst-side traversal that depends on Symptom 5's
  `parent_transfer_id` chain being intact.
- [AR Exceptions: Ledger Drift](../ar/ledger-drift.md) —
  the analyst-side view of Symptom 4's drift KPI spike.
