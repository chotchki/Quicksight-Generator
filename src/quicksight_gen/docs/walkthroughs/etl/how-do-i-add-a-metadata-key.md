# How do I add a metadata key without breaking the dashboards?

*Engineering walkthrough — Data Integration Team. Extension.*

## The story

The 11-column `transactions` contract intentionally doesn't carry
every per-`transfer_type` attribute as its own column —
`card_brand` belongs on PR sales but is meaningless on AR
internal transfers; `settlement_type` matters on settlements but
not on payments; `statement_line_id` belongs on Fed force-posts
only. The schema's answer is the `metadata` JSON column: each
`transfer_type` carries its own grab-bag of typed extras inside
JSON, and dataset SQL extracts via `JSON_VALUE(metadata,
'$.your_key')`.

That's powerful — and easy to misuse. Two failure modes show up
when teams add a new metadata key:

- **The wrong JSON dialect**: someone reaches for PostgreSQL's
  native `metadata->>'key'` operator and the query works in dev
  but fails to port. Or they reach for `JSONB`, breaking the
  schema constraint.
- **Visual references a key the data doesn't carry**: a Pivot or
  Table column reads `JSON_VALUE(metadata, '$.your_new_key')` for
  rows that pre-date the new key, and the cell renders blank
  (or worse, the visual silently filters those rows out).

## The question

"My team needs to add a new attribute (`originating_branch`,
`risk_score`, `fx_rate`) to a subset of `transactions` rows.
What's the contract for adding it without breaking existing
dashboards or the portability of the SQL?"

## Where to look

Three reference points:

- **`docs/Schema_v6.md` → metadata catalog tables** — the existing
  per-`transfer_type` key inventory. New keys should slot into the
  same shape (key name, type, what it drives).
- **`src/quicksight_gen/apps/payment_recon/datasets.py`** and
  **`src/quicksight_gen/apps/account_recon/datasets.py`** — the SQL
  patterns. Every metadata extraction looks like
  `JSON_VALUE(metadata, '$.<key>') AS <alias>`; new keys follow
  the same shape.
- **CLAUDE.md → "Database portability constraint"** — the
  forbidden-pattern list (`JSONB`, `->>`, `->`, `@>`, `?`, GIN
  indexes). If you reach for any of these, the new key won't
  port.

## What you'll see in the demo

Existing demo rows already exercise the pattern. Grep one out:

```bash
quicksight-gen demo seed --all -o /tmp/seed.sql
grep -m1 "card_brand" /tmp/seed.sql
```

You'll see a `JSON_OBJECT(... 'card_brand' VALUE 'visa', ...)`
literal in the INSERT. The matching dataset SQL:

```bash
grep -n "JSON_VALUE(metadata, '\\$.card_brand')" \
     src/quicksight_gen/apps/payment_recon/datasets.py
```

shows the consumer side: `JSON_VALUE(metadata, '$.card_brand') AS
card_brand` in the dataset projection. That pair —
`JSON_OBJECT(... 'key' VALUE 'val')` on the producer side,
`JSON_VALUE(metadata, '$.key')` on the consumer side — is the only
shape allowed.

## What it means

The contract for any new metadata key has four parts:

1. **JSON value type must be a portable scalar**. Strings,
   numbers, booleans, and dates are fine. Nested objects work for
   well-defined sub-payloads (e.g., AR's `limits` payload). Arrays
   work in principle but no current dataset reads one — exercise
   caution. **No binary, no Postgres-specific types**.
2. **Use `JSON_OBJECT(... 'key' VALUE 'value')` to write, not
   PostgreSQL row-to-JSON shortcuts**. Row-to-JSON casts emit a
   shape that breaks `JSON_VALUE` parsing on stricter dialects.
3. **Use `JSON_VALUE(metadata, '$.key')` to read, never `->>`**.
   The `->>` operator is PostgreSQL-only; `JSON_VALUE` is the
   SQL/JSON standard form.
4. **Document the new key in `Schema_v6.md`'s metadata catalog
   for that `transfer_type`**. Otherwise the
   `test_metadata_keys_referenced_in_examples_are_documented`
   test fails the next time anyone touches the etl-example
   generator.

A subtle constraint on dataset visuals: if a visual *expects* the
key to be present (e.g., uses it as a filter or grouping
dimension), all rows the visual sees must carry the key. The
options for handling rows without the key:

- **Filter the visual to rows that have it**:
  `WHERE JSON_EXISTS(metadata, '$.your_key')`. Cleanest when the
  key is genuinely optional.
- **Coalesce in the projection**: `COALESCE(JSON_VALUE(metadata,
  '$.your_key'), 'unknown') AS your_key`. Keeps the row visible
  but renders an explicit sentinel.
- **Backfill the key on existing rows**: a one-shot UPDATE to add
  `'your_key' VALUE '<derived>'` to the existing JSON. Right
  answer when the key has a sensible default for historical
  rows.

## Drilling in

A worked example. Suppose your team needs to add an
`originating_branch` key on PR sales so the Sales sheet can group
by branch.

**Step 1 — write it on the producer side (your ETL).** Add to the
existing `JSON_OBJECT` literal in your sale-projection INSERT:

```sql
JSON_OBJECT(
    'source'              VALUE 'core_banking',
    'merchant_id'         VALUE p.merchant_id,
    -- existing keys ...
    'originating_branch'  VALUE p.branch_code   -- new key
)
```

**Step 2 — read it on the consumer side (the dataset SQL).** In
the relevant `datasets.py` builder, add a projected column:

```sql
SELECT
    -- existing columns ...
    JSON_VALUE(metadata, '$.originating_branch') AS originating_branch
FROM transactions
WHERE transfer_type = 'sale';
```

Update the matching `DatasetContract` to add `("originating_branch",
"STRING")` so the contract test stays green.

**Step 3 — document it.** Add a row to the PR `sale` metadata
catalog table in `Schema_v6.md`:

```markdown
| `originating_branch` | string | Branch code that handled the sale | Sales sheet branch grouping |
```

**Step 4 — wire the visual.** Direct query (not SPICE) means new
columns show up immediately after `quicksight-gen deploy`. No
refresh step. Open the Sales sheet, drag `originating_branch`
into the Pivot grouping or Table column list.

## Next step

Once the key is producing, consuming, and rendering:

1. **Run the unit + integration tests**:
   `.venv/bin/pytest tests/test_demo_etl_examples.py
   tests/test_dataset_contract.py`. The schema-contract test
   verifies your new key is in the catalog; the dataset-contract
   test verifies the SQL projection matches.
2. **Re-run the pre-flight invariants** from the validation
   walkthrough. Adding a metadata key shouldn't break any of
   them, but if you backfilled rows via UPDATE, double-check that
   the cumulative-sum invariant still holds (UPDATEs on
   `signed_amount` are the danger; UPDATEs on `metadata` are
   safe).
3. **Deploy to the QuickSight environment**:
   `quicksight-gen deploy --all --generate -c run/config.yaml -o
   run/out/`. The new column appears on next dashboard open — no
   SPICE refresh needed.

## Related walkthroughs

- [How do I populate `transactions` from my core banking system?](how-do-i-populate-transactions.md) —
  the foundational projection. This walkthrough adds keys to that
  projection's `metadata` literal.
- [How do I prove my ETL is working before going live?](how-do-i-prove-my-etl-is-working.md) —
  re-run the three invariants after any metadata addition.
- `what-do-i-do-when-demo-passes-but-prod-fails.md` (forthcoming) —
  the "visual shows N/A" symptom in the debug recipes is usually
  a metadata-key contract violation.
- [Schema_v6 → metadata catalog](../../Schema_v6.md#table-1-prefix_transactions) —
  the per-`transfer_type` key inventory and its forbidden-syntax
  rules.
- [How much did we return?](../pr/how-much-did-we-return.md) —
  a **downstream consumer** example: PR's returned-payment KPI
  reads `metadata.is_returned`, the same metadata-key pattern a
  new addition follows.
