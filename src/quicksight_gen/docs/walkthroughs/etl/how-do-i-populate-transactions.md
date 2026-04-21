# How do I populate `transactions` from my core banking system?

*Engineering walkthrough — Data Integration Team. Foundational.*

## The story

You've got an upstream core banking system with a `gl_postings`
table (or its local equivalent — `general_ledger.entry`,
`accounting.posting_detail`, etc.). It carries one row per posting
leg already, which is the natural granularity of our `transactions`
table. You need to write the ETL job that lands it in our
two-table schema by the morning cut so the dashboards work.

The good news: it's mostly a column-rename. The contract is small
(11 mandatory columns + a handful of conditional ones — see
[Schema_v3.md → Getting Started for Data Teams](../../Schema_v3.md#getting-started-for-data-teams)).
The bad news: skip the wrong column and a downstream check goes
silent. So this walkthrough covers the canonical projection plus
the per-column failure modes.

## The question

"For my core banking system's `gl_postings` table, what's the
canonical projection that maps it to `transactions`? What columns
must I populate, and what columns can wait until v2?"

## Where to look

Two reference points:

- **`docs/Schema_v3.md`** — column-level contract and per-column
  failure modes ("If you skip this, what dashboard breaks?").
- **`quicksight-gen demo etl-example --all -o etl-examples.sql`** —
  emits 11 canonical INSERT-pattern blocks (6 PR + 5 AR) that you
  can crib from. Each one carries a `-- WHY:` header and a
  `-- Consumed by:` pointer to the dashboard view that reads it.

If you're new to the schema, generate `etl-examples.sql` first and
read it top-to-bottom. The patterns are written as if they were
the only documentation a customer would ever see — they're
self-contained.

## What you'll see in the demo

Run:

```bash
quicksight-gen demo etl-example --all -o /tmp/etl-examples.sql
head -50 /tmp/etl-examples.sql
```

The first block is **Pattern 1: PR sale** — the canonical
projection from a POS sale into `transactions`. Strip the
sentinel suffix (`-EXAMPLE-001`) and wire each column to your
upstream feed's source field. The full block runs ~50 lines and
covers every column the PR side cares about.

For an end-to-end mapping from `core_banking.gl_postings` →
`transactions`, see **Example 1** in `docs/Schema_v3.md` (the
SQL block under "Populating customer DDA postings from core
banking"). It's the same pattern shape as the demo `etl-examples`
output but written as a real `INSERT INTO ... SELECT FROM` against
a hypothetical core-banking source schema.

## What it means

For every row your ETL writes, you're committing to a contract:

1. **The 11 mandatory columns** (per [Schema_v3.md → minimum
   viable feed](../../Schema_v3.md#the-minimum-viable-feed)) get
   the row visible on the dashboard at all.
2. **`parent_transfer_id`** populated only for chained transfers
   (sale → settlement → payment → external_txn for PR; reversal
   chains for AR). Skip it and pipeline-traversal walkthroughs
   silently return nothing for the affected rows.
3. **`origin = 'external_force_posted'`** on Fed / processor
   force-posts. Skip it and AR's GL-vs-Fed-Master-Drift check
   under-fires (rows look like normal operator postings).
4. **`metadata` JSON** — the universal extras container. Skip it
   on day 1 if your downstream consumer doesn't need it; populate
   it in priority order (`source` first, then per-`transfer_type`
   keys per the catalog). The catalog tables in Schema_v3 list the
   keys + what each one drives.

Everything else (`memo`, `external_system`, `control_account_id`)
is conditional — populate when the downstream consumer demands it.

## Drilling in

The mapping pattern looks like this for a customer-DDA posting
(from Schema_v3 Example 1, abbreviated):

```sql
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
)
SELECT
    p.posting_id,                                      -- your PK
    p.transfer_id,                                     -- your transfer grouping
    p.transfer_type,                                   -- map your enum to ours
    'internal_initiated'                AS origin,     -- or external_force_posted for Fed
    p.account_number                    AS account_id,
    a.account_name,
    a.gl_control_account                AS control_account_id,
    a.account_role                      AS account_type,
    a.is_bank_owned                     AS is_internal,
    p.signed_amount,
    ABS(p.signed_amount)                AS amount,
    CASE WHEN p.posting_status = 'P' THEN 'success' ELSE 'failed' END,
    p.posting_timestamp                 AS posted_at,
    p.posting_timestamp::date           AS balance_date,
    p.memo,
    JSON_OBJECT('source' VALUE 'core_banking')
FROM core_banking.gl_postings p
JOIN core_banking.accounts a ON a.account_number = p.account_number
WHERE p.posting_date >= CURRENT_DATE - INTERVAL '7 days';
```

A few things to note about this projection:

- **`balance_date`** is denormalized from `posted_at` deliberately
  — fast date filters in the dashboard datasets need a column they
  can range-scan without an expression cast. It's our redundancy
  for our query speed; the cost is your ETL writes one extra
  column.
- **`status`** maps from your status enum to ours. Anything that's
  not `success` MUST be `failed` (no third state) — the drift
  check and net-zero check both `WHERE status = 'success'` to
  exclude rejected legs.
- **`signed_amount`** is `+` for money flowing INTO the account
  (a `debit` in bank's-bookkeeping terms), `−` for money flowing
  OUT (a `credit`). `daily_balances.balance` for any account-day
  equals `SUM(signed_amount)` up to that day, so getting this
  sign right is what makes the drift check honest. If your
  upstream uses the opposite sign convention, flip it here, not
  later in a view. Every check assumes our sign convention.
- **`metadata`** carries `source` on every row from this projection
  (driven by the `JSON_OBJECT(... VALUE 'core_banking')` literal).
  That single key is enough to satisfy the Fraud / AML provenance
  filter on day 1.

## Next step

Once your projection is wired up:

1. **Populate a small slice** — one day, one source system. Don't
   try to backfill 90 days on the first run.
2. **Run the validation walkthrough**
   ([How do I prove my ETL is working before going live?](how-do-i-prove-my-etl-is-working.md))
   — it walks you through the net-zero, drift-recompute, and
   parent-chain integrity checks you should run before declaring
   the load complete.
3. **Open the AR Exceptions sheet and the PR Exceptions sheet** —
   if KPIs read 0 with no drilldown rows, your feed landed and
   the contract holds. If KPIs spike unexpectedly, see
   [What do I do when the demo passes but my prod data fails?](what-do-i-do-when-demo-passes-but-prod-fails.md)
   for the symptom-organized debug recipes.
4. **Iterate on metadata** — once the minimum feed is stable,
   layer in `parent_transfer_id` and the per-`transfer_type`
   metadata keys per the priority order in
   [Schema_v3.md → What changes after day 1](../../Schema_v3.md#what-changes-after-day-1).

If your upstream source isn't a `gl_postings` table — say it's a
processor report, a Fed statement file, or a sweep-engine log —
the same projection shape applies, but the inbound columns differ.
Schema_v3.md Examples 4 and 5 cover PR sales and Fed-statement
ingest specifically; the demo `etl-example` output covers the
remaining patterns.

## Related walkthroughs

- [How do I prove my ETL is working before going live?](how-do-i-prove-my-etl-is-working.md) —
  the **next step** after writing the projection. Validates the
  invariants the dashboard depends on.
- [How do I tag a force-posted external transfer correctly?](how-do-i-tag-a-force-posted-transfer.md) —
  the canonical pattern for Fed-statement ingest, which is the one
  case where `origin = 'external_force_posted'`.
- [How do I add a metadata key without breaking the dashboards?](how-do-i-add-a-metadata-key.md) —
  the extension contract for when your team needs a new metadata
  field.
- [Schema_v3 → Getting Started for Data Teams](../../Schema_v3.md#getting-started-for-data-teams) —
  the persona-oriented intro to the contract.
- [Schema_v3 → ETL examples](../../Schema_v3.md#etl-examples) —
  the canonical SQL templates this walkthrough references.
- [Where's my money for merchant?](../pr/wheres-my-money-for-merchant.md) —
  a **downstream consumer** walkthrough: what an analyst does with
  the `transactions` rows your projection lands.
