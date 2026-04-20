# How do I prove my ETL is working before going live?

*Engineering walkthrough — Data Integration Team. Foundational.*

## The story

You've populated `transactions` and `daily_balances` from your
upstream feed. The morning cut runs at 6 AM and the dashboards open
at 8. Before you cut the load tag and go to bed, you'd like to know
your feed is *internally consistent* — not "the dashboards render"
(that's surface-level), but "the invariants the dashboards depend on
actually hold".

Three invariants matter on day one. Each one is testable from a
single SQL query against the two base tables, and each one
corresponds to a specific exception check on the dashboard. If your
ETL violates the invariant, the check will fire — but it'll fire at
8 AM in front of a Treasury operator. Better to fire it at 6:05 AM
in your own pipeline.

## The question

"Before I open the dashboard, what SQL can I run against my newly
loaded `transactions` and `daily_balances` to know the feed is
sound — and what does each check correspond to on the dashboard if
it's not?"

## Where to look

Three reference points:

- **`quicksight-gen demo etl-example account-recon`** — Pattern 5
  is the canonical ledger-drift recompute query. Copy it as-is and
  point it at your account set.
- **`docs/Schema_v3.md`** — the per-column failure-mode notes
  ("If you skip this, what dashboard breaks?") tell you which
  invariant a column violation will trip.
- **AR Exceptions sheet** — three checks (AR Non-Zero Transfers,
  Ledger Drift, Sub-Ledger Drift) are the dashboard-side
  consequence of the invariants below. If your pre-flight passes,
  these KPIs read zero on the demo data.

## What you'll see in the demo

Run the three pre-flight checks against the seeded demo database:

```bash
quicksight-gen demo apply --all -c run/config.yaml -o run/out/
psql "$DEMO_DATABASE_URL" -f /tmp/preflight.sql
```

Where `/tmp/preflight.sql` is the three queries below. On a clean
demo seed, all three return zero rows — that's the green-light
signal. The seeded "planted failures" (drift scenarios, stuck
suspense, etc.) are at the *check* layer, not the *invariant*
layer; the invariants always hold for the seed because the
generator is deterministic and self-consistent.

## What it means

Each query asserts one invariant. A non-empty result means a row
in your feed contradicts what the schema and dashboards assume.

### Invariant 1 — non-failed transfer legs net to zero

```sql
-- Pre-flight: transfers whose successful legs do NOT sum to zero.
SELECT
    transfer_id,
    SUM(signed_amount) AS net,
    COUNT(*)           AS leg_count
FROM transactions
WHERE status = 'success'
  AND transfer_type NOT IN ('external_txn', 'sale')   -- single-leg types
GROUP BY transfer_id
HAVING SUM(signed_amount) <> 0;
```

A row here means a multi-leg transfer (`internal`, `payment`,
`settlement`, `clearing_sweep`, `ach`, `wire`, etc.) has legs that
don't balance. Either you projected the wrong sign on one leg,
dropped a leg, or set `status = 'success'` on a leg that didn't
post.

**Dashboard consequence**: AR Non-Zero Transfers KPI fires for the
listed `transfer_id`s. PR's parallel check will too.

### Invariant 2 — `daily_balances.balance` matches the recomputed cumulative sum

This is Pattern 5 from `quicksight-gen demo etl-example account-recon`,
reproduced here as the pre-flight smoke test:

```sql
-- Pre-flight: ledger rows whose stored EOD balance disagrees with
-- the cumulative SUM of postings to that account.
SELECT
    db.account_id,
    db.balance_date,
    db.balance                                         AS stored,
    COALESCE(SUM(t.signed_amount), 0)                  AS recomputed,
    db.balance - COALESCE(SUM(t.signed_amount), 0)     AS drift
FROM daily_balances db
LEFT JOIN transactions t
  ON t.account_id    = db.account_id
 AND t.balance_date <= db.balance_date
 AND t.status        = 'success'
WHERE db.balance_date = CURRENT_DATE
GROUP BY db.account_id, db.balance_date, db.balance
HAVING db.balance - COALESCE(SUM(t.signed_amount), 0) <> 0;
```

A row here means the balance feed and the transaction feed
disagree on the same account-day. Either a posting is missing /
extra in `transactions`, or the EOD `balance` value in
`daily_balances` is stale.

**Dashboard consequence**: AR Ledger Drift and Sub-Ledger Drift
checks fire. The drift timeline rollup at the top of the
Exceptions sheet will show a non-zero band on today's date.

### Invariant 3 — `parent_transfer_id` chains have no orphans

```sql
-- Pre-flight: transactions whose parent_transfer_id points at a
-- transfer_id that doesn't exist in our base table.
SELECT DISTINCT
    t.transfer_id,
    t.transfer_type,
    t.parent_transfer_id   AS missing_parent
FROM transactions t
WHERE t.parent_transfer_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM transactions p
      WHERE p.transfer_id = t.parent_transfer_id
  );
```

A row here means a child transfer (PR settlement, payment, or
external_txn; AR reversal child) names a parent that wasn't loaded
in the same cut. Most often this is an ordering bug: the child
landed before the parent, or you trimmed the parent out with a
narrow `WHERE` clause on the source feed.

**Dashboard consequence**: The PR pipeline-traversal walkthroughs
([Where's my money for merchant?](../pr/wheres-my-money-for-merchant.md))
silently return nothing for the orphaned chains. No KPI fires, but
the "trace this dollar" experience breaks.

## Drilling in

Three patterns, all violating the same shape — your ETL trusted
something it shouldn't have:

- **Sign-flip on leg 2.** Most common Invariant 1 violation:
  upstream uses opposite sign convention from ours, and you flipped
  the sign in *some* projections but not all. Audit all branches of
  your `signed_amount` mapping.
- **Lagging balance feed.** Most common Invariant 2 violation: the
  balance file lands an hour after the postings file, and your ETL
  processes them in the order they arrive. Either wait for both or
  re-stamp `balance_date` on the postings feed to match the
  authoritative EOD batch.
- **Narrow WHERE clause.** Most common Invariant 3 violation: a
  `WHERE posting_date >= CURRENT_DATE - INTERVAL '7 days'` filter
  on a child table cuts off parents from older days. For chained
  types, either pull all transfers in the chain together, or
  expand the lookback to cover the longest expected chain age.

A "what should I see on the dashboard if everything's good"
checklist:

- [ ] **Getting Started** sheet renders with a date range for
  today's cut.
- [ ] **AR Exceptions** sheet — top three rollups (Balance Drift
  Timelines, Two-Sided Post Mismatch, Expected-Zero EOD): KPI
  counts non-zero only for *seeded* failure scenarios; no rows for
  the accounts your real ETL touched today.
- [ ] **AR Non-Zero Transfers KPI** = 0.
- [ ] **Ledger Drift KPI** = 0 for any account whose `balance` you
  populated today.
- [ ] **PR Settlement Mismatch / Payment Mismatch / Unmatched
  External Transactions KPIs** = 0 for the merchants you loaded
  today (note: planted demo failures will show non-zero — those are
  the *demo's* job, not yours).

## Next step

Once your three pre-flight queries all return zero rows:

1. **Wire them into your DAG**. Run them as a smoke-test step
   between the load and the "publish" tag. Treat any non-empty
   result as a hard failure — don't publish a load with broken
   invariants.
2. **Backfill, one day at a time**. With pre-flight wired up, you
   can now safely load older days. Run the load + pre-flight per
   day; if any day fails an invariant, fix and re-run that day in
   isolation.
3. **Add app-specific checks for your metadata keys**. The three
   invariants above are *universal*. If you populate
   `parent_transfer_id` for chained PR transfers, also assert that
   every `payment` row has a non-NULL `parent_transfer_id` (since
   payments without a parent external_txn won't appear in PR
   reconciliation views). The pattern is the same — one SELECT,
   `HAVING ... <> 0` or `WHERE ... IS NULL`, fail the DAG on
   non-empty.
4. **Open the dashboard with an analyst on the call**. The pre-
   flight verifies the *contract*; the analyst verifies the
   *meaning*. They'll catch things like "the merchant exists but
   the volume looks 10x too high" that no SQL invariant can.

If any pre-flight query is non-empty and you can't trace it, see
the `what-do-i-do-when-demo-passes-but-prod-fails.md` walkthrough
(forthcoming) for the symptom-organized debug recipes.

## Related walkthroughs

- [How do I populate `transactions` from my core banking system?](how-do-i-populate-transactions.md) —
  the **prior step**: writing the projection these invariants check.
- `how-do-i-tag-a-force-posted-transfer.md` (forthcoming) —
  Invariant 1 + Invariant 3 both interact with `origin` and the
  parent chain on Fed-statement ingest.
- `what-do-i-do-when-demo-passes-but-prod-fails.md` (forthcoming) —
  the symptom-organized debug companion when an invariant fails
  and you can't immediately see why.
- [Schema_v3 → minimum viable feed](../../Schema_v3.md#the-minimum-viable-feed) —
  the column contract whose failure modes drive the invariants.
- [AR Exceptions: Balance Drift Timelines rollup](../ar/balance-drift-timelines-rollup.md) —
  the dashboard-side view of what Invariant 2 catches when it fires
  in production.
