# How do I extend the schema with a new transfer_type or account_type?

*Customization walkthrough — Developer / Product Owner. Reskinning + extending.*

## The story

Your bank does a kind of money movement the demo doesn't model
— say `repo` for repurchase agreements, `mortgage_servicing` for
mortgage payment passthrough, or `correspondent_settlement` for
nostro/vostro flows. You want it on the dashboards: filterable,
groupable, drill-able, the whole experience the existing
`transfer_type` values (`ach`, `wire`, `sale`, `settlement`,
etc.) get out of the box.

The good news: `transfer_type` and `account_type` are values
in the data, not enums in the dashboard code. The Transfer Type
dropdown filter on the AR Transactions tab auto-populates from
the distinct values present in the dataset. Add a row to
`transactions` with `transfer_type = 'repo'` and the next
dashboard load shows `repo` as a filterable value with no code
change.

The catch: the schema's `CHECK (transfer_type IN (...))`
constraint enforces the canonical list. New values require a
schema-side update (one DDL line) and a downstream impact
review (do the existing exception checks make semantic sense
for the new type?). This walkthrough covers both.

## The question

"My bank's data has a movement type the demo doesn't model.
What's the minimum I need to change to surface it as a
first-class value on the dashboards?"

## Where to look

Three reference points:

- **`demo/schema.sql`** — the `CHECK (transfer_type IN (...))`
  constraint at the top of the `transactions` table DDL. This
  is the source of truth for the canonical value list.
- **[Schema_v6.md → Canonical account_type values](../../Schema_v6.md#table-1-prefix_transactions)** /
  **[Schema_v6.md → Table 1 transactions](../../Schema_v6.md#table-1-prefix_transactions)** —
  the per-`transfer_type` metadata key inventory and the
  `account_type` table (`gl_control`, `dda`, `merchant_dda`,
  `external_counter`, `concentration_master`, `funds_pool`).
- **`src/quicksight_gen/apps/account_recon/filters.py:243`** — the
  `_transfer_type_filter_group()` definition. Notice it
  doesn't enumerate values; QuickSight populates the dropdown
  from distinct values in the `transfer_type` column at query
  time.

## What you'll see in the demo

The current canonical `transfer_type` set lives in
`demo/schema.sql`:

```sql
transfer_type VARCHAR(30) NOT NULL
    CHECK (transfer_type IN (
        'sale', 'settlement', 'payment', 'external_txn',
        'ach', 'wire', 'internal', 'cash',
        'funding_batch', 'fee', 'clearing_sweep'
    )),
```

11 values cover everything the demo seeds. The dashboard's
Transfer Type filter (on the AR Transactions, Transfers, and
Exceptions tabs) reads the column directly — no separate enum
file in code, no per-value visual config. New values surface
the moment they appear in `transactions`.

The `account_type` column is similar but **not** constrained
in the schema:

```sql
account_type VARCHAR(50) NOT NULL,
```

The canonical list (`gl_control`, `dda`, `merchant_dda`,
`external_counter`, `concentration_master`, `funds_pool`) is
documented in
[Schema_v6.md](../../Schema_v6.md#table-1-prefix_transactions)
but enforced only by convention. Adding a new account_type is
zero-DDL.

## What it means

The "extend" surface depends on which column you're touching:

### Adding a new `transfer_type` value

Three steps:

1. **Update the CHECK constraint.** Edit `demo/schema.sql` to
   add the new value to the `CHECK (transfer_type IN (...))`
   list. If you've already deployed, run an ALTER TABLE to
   drop and recreate the constraint with the new value. (The
   schema is direct query — no downstream cache to invalidate.)
2. **Decide the metadata-key payload.** The existing
   per-`transfer_type` metadata catalog
   ([Schema_v6.md](../../Schema_v6.md#metadata-json-columns))
   gives each `transfer_type` its own metadata key set
   (`card_brand` on sales, `settlement_type` on settlements,
   etc.). Decide what goes in `metadata` for your new value.
   See [How do I add an app-specific metadata key?](how-do-i-add-a-metadata-key.md)
   for the read pattern.
3. **Wire your ETL to write the new value.** Whatever upstream
   feed produces the new movement type now writes
   `transfer_type = 'repo'` (or whatever you named it). The
   filter dropdown picks it up automatically; no dashboard
   code changes.

### Adding a new `account_type` value

Two steps (no schema change needed — `account_type` has no
CHECK constraint):

1. **Document the new value.** Update
   [Schema_v6.md → Canonical account_type values](../../Schema_v6.md#table-1-prefix_transactions)
   with the new role and what it means. The list is the
   convention; without it, future-you will guess.
2. **Wire your ETL to write the new value.** Same as
   `transfer_type` — whatever feed creates the new account
   role writes `account_type = 'broker_dealer'` (or whatever
   you named it). The dashboard surfaces it automatically.

## Drilling in

A few patterns to know once the basic addition works:

### Filter dropdowns auto-populate from data

QuickSight's multi-select filter doesn't enumerate values in
its config — it reads them from the dataset's column at query
time. The wiring in
`src/quicksight_gen/apps/account_recon/filters.py:251-258` looks
like:

```python
return _multi_select_filter_group(
    fg_id="fg-ar-transfer-type",
    title="Transfer Type",
    column_name="transfer_type",        # ← column reference, no values
    sheet_ids=_TRANSFER_TYPE_SCOPED_SHEETS,
)
```

Add a new value, dashboard renders it. Drop a value, the
dropdown stops showing it. No deploy step required after the
ETL writes the new value.

### Why no new tables

Both apps share the same two base tables. A new `transfer_type`
is a new *value* in the existing `transactions.transfer_type`
column — not a new table, not a new dataset, not a new sheet.
This is the single load-bearing decision behind the schema:
denormalization-by-default keeps the surface small enough that
"add a movement type" is a value-write, not a schema migration.

When you're tempted to add a per-type table (`repo_transactions`,
`mortgage_servicing_transactions`), push back. The pattern is
to encode the type in `transfer_type` and put per-type extras
in `metadata`. Tables are reserved for legitimately disjoint
domains (the AR-only dimension tables `ar_ledger_accounts`,
`ar_subledger_accounts`, `ar_ledger_transfer_limits` —
configuration, not flow data).

### Existing exception checks may or may not apply to your new type

The 14 AR exception checks (drift, overdraft, sweep target
non-zero, etc.) read from `transactions` and `daily_balances`
without `WHERE transfer_type = ...` filters in most cases —
they apply to *every* transfer that lands in the affected
account. So your new `transfer_type = 'repo'` rows will
participate in every exception check that scopes to the
account, not the type:

- **Drift checks (`ar_ledger_balance_drift`,
  `ar_subledger_balance_drift`)** — apply universally. A repo
  leg that doesn't net to zero with its counter-leg surfaces
  in sub-ledger drift, just like an ACH leg.
- **Overdraft (`ar_subledger_overdraft`)** — applies
  universally. A repo that drives a sub-ledger negative
  surfaces here.
- **Type-scoped checks** (limit breach, ACH sweep no Fed
  confirmation, etc.) — read `transfer_type = 'ach'` /
  `'sweep'` / etc. directly. Won't fire on your new type
  unless you add it to the relevant SQL's WHERE clause. See
  [How do I swap dataset SQL?](how-do-i-swap-dataset-sql.md)
  for the contract-preserving way to extend a dataset's
  scope.

The decision per check: does the *semantic intent* of the
check apply to your new type? If yes, extend the WHERE clause
to include it; if no, leave the check scoped as-is.

### Single-leg vs multi-leg transfers

The `expected_net_zero` flag in `ar_transfer_summary`
distinguishes types whose transfers must net to zero
(multi-leg: `ach`, `wire`, `internal`, `clearing_sweep`,
`funding_batch`) from types whose transfers don't have a
counter-leg (single-leg: `sale`, `external_txn`).

When you add a new type, decide which it is and update the
`ar_transfer_summary` view (in `demo/schema.sql`) to mark it.
A multi-leg type incorrectly marked single-leg silently
suppresses Non-Zero Transfer alerts for it; a single-leg type
incorrectly marked multi-leg fires false-positive Non-Zero
Transfer alerts on every row.

## Next step

Once your new canonical value is wired:

1. **Run pytest.** The contract tests
   (`tests/test_dataset_contract.py`) don't enumerate
   `transfer_type` values, so they'll pass without changes.
   But if you extended a type-scoped exception check's WHERE
   clause, the contract test for *that* dataset will catch
   any column-shape drift.
2. **Seed a few demo rows for the new type.** Add a
   generator branch in `apps/payment_recon/demo_data.py` or
   `apps/account_recon/demo_data.py` that emits a handful of
   `transfer_type = 'repo'` rows. The
   `TestScenarioCoverage` pattern in the demo-data tests
   (see CLAUDE.md "Demo Data Conventions") makes this a
   one-line assertion: ≥N rows of the new type. Without
   demo coverage, the dashboard "works" but the new value's
   visual treatment never gets exercised in the e2e tests.
3. **Re-deploy.** `quicksight-gen demo apply --all -c
   config.yaml -o out/` to rewrite seed data,
   `quicksight-gen deploy --all --generate -c config.yaml -o
   out/` to push the schema and dashboard changes. The new
   value appears in the Transfer Type filter dropdown on the
   first dashboard refresh.

## Related walkthroughs

- [How do I add an app-specific metadata key?](how-do-i-add-a-metadata-key.md) —
  paired pattern. New `transfer_type` values almost always
  carry per-type metadata keys; the metadata-key walkthrough
  covers the read pattern.
- [How do I swap the SQL behind a dataset?](how-do-i-swap-dataset-sql.md) —
  for when you need to extend a type-scoped exception check
  to fire on your new value. The contract-preserving SQL edit
  is the right shape.
- [Schema_v6 → Canonical account_type values](../../Schema_v6.md#table-1-prefix_transactions) —
  the documented convention for `account_type`. Update the
  table when you add a new role.
