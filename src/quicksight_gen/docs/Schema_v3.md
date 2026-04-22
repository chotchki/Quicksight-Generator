# Schema v3 — the two-table reconciliation feed contract

This document is the contract for the data your ETL pipeline writes into,
and the data the AR / PR dashboards read out of. After Phase G, the
entire system runs on **two base tables**:

- `transactions` — one row per money-movement leg (posting)
- `daily_balances` — one row per (account, date) snapshot

Everything else — drift checks, exception catalogues, rollups, the
reconciliation engine — is **computed views** on top of those two tables.

> **System compatibility requires PostgreSQL 17+.**
> SQL must stay portable across the dialect that consumes this app, so
> the schema and all queries use only standards-portable features:
> - JSON storage in `TEXT` columns with `IS JSON` constraints.
> - JSON extraction via SQL/JSON path functions (`JSON_VALUE`,
>   `JSON_QUERY`, `JSON_EXISTS`).
> - B-tree indexes only on real columns.
> - No `JSONB`, no `->>` / `->` / `@>` / `?` operators, no GIN indexes
>   on JSON, no Postgres extensions, no array / range types.
> See **Forbidden SQL patterns** at the end.

---

## Getting Started for Data Teams

You're an SNB Data Integration Team engineer. An upstream feed lands at
2 AM; by 9 AM the dashboards downstream of you need to be accurate.
You've inherited this two-table contract from the previous engineer and
want to know: **which columns must I populate today, and which can wait
until v2?**

### The minimum viable feed

To see *something* on the dashboard, populate these columns on every row:

- **`transactions` (11 columns)** — `transaction_id`, `transfer_id`,
  `transfer_type`, `account_id`, `account_name`, `account_type`,
  `is_internal`, `signed_amount`, `amount`, `posted_at`, `balance_date`.
- **`daily_balances` (6 columns)** — `account_id`, `account_name`,
  `account_type`, `is_internal`, `balance_date`, `balance`.

Skip `metadata` entirely on day 1; populate `parent_transfer_id`,
`origin`, `external_system`, `memo`, `control_account_id` only when
their downstream consumer demands it. The per-column tables below
spell out which check breaks if you don't.

### Order of operations for a new feed

1. **Stand up the schema** — `quicksight-gen demo schema -o schema.sql`
   gives you the canonical DDL. Run it against a dev database.
2. **Generate exemplary INSERTs** — `quicksight-gen demo etl-example
   --all -o etl-examples.sql` emits pattern-by-pattern inserts you
   can crib from.
3. **Map your upstream feed** — most core-banking systems have a
   `gl_postings` (or equivalent) detail table; ETL Examples below
   show the canonical projection. See
   [How do I populate `transactions` from my core banking system?](walkthroughs/etl/how-do-i-populate-transactions.md).
4. **Validate locally before going live** — the ledger-drift and
   net-zero invariants must hold. See
   [How do I prove my ETL is working before going live?](walkthroughs/etl/how-do-i-prove-my-etl-is-working.md).
5. **Watch the dashboards** — open the AR Exceptions sheet and the PR
   Exceptions sheet. If KPIs read 0 with no drilldown rows, the feed
   landed; if KPIs spike unexpectedly, see
   [What do I do when the demo passes but my prod data fails?](walkthroughs/etl/what-do-i-do-when-demo-passes-but-prod-fails.md).

### What changes after day 1

The metadata column is where new fields land between schema migrations.
Once the minimum feed is stable, the order of metadata-key population
priority is roughly:

1. `source` on every row — Fraud / AML can't filter without it.
2. `parent_transfer_id` on chained transfers — PR pipeline traversal
   and AR reversal/stuck checks need it to walk the chain.
3. `origin = 'external_force_posted'` on Fed / processor force-posts —
   AR's GL-vs-Fed-Master-Drift check is silent without it.
4. PR sales metadata (`merchant_account_id`, `card_brand`, `cashier`) —
   merchant-side analytics + Phase H sale-vs-settlement cross-check.
5. `daily_balances.metadata.limits` on ledger rows — limit-breach KPI
   shows 0 without it (no limits configured = nothing to breach).

For each metadata key, the **What breaks if you skip a column** notes
under the column-spec tables call out the specific failure mode.

---

## Why this shape

Three audiences shape these tables:

1. **Data Integration Team** — writes ETL jobs from upstream core-banking
   systems, the Fed, processors, etc. Wants the FEWEST tables that
   correctly model double-entry money movement. Two tables fit on a
   whiteboard.
2. **GL Reconciliation / Accounting Operations** — reads the dashboards
   to hunt exceptions. Doesn't care about the table layout, but cares
   that "stored balance" and "computed-from-transactions balance" agree.
3. **Future personas** (Fraud, AML, Merchant Support) — write their own
   views over these two tables. The column set is **denormalized** to
   make ad-hoc analytics queries readable without a join.

The trade-off: redundancy (account name, type, etc. repeat on every
transaction row). The win: one feed contract, two tables, no joins
required for most analyst queries.

---

## Table 1 — `transactions`

One row per posting leg. A "transfer" is a logical movement of money;
each transfer has one or more rows in this table that must net to zero
when summed by `transfer_id` (excluding `failed` rows). Transfer chains
(originator → suspense → recipient) are modeled via `parent_transfer_id`.

### Columns

| Column | Type | Null? | Populated by | Consumed by |
|---|---|---|---|---|
| `transaction_id` | VARCHAR(100) | NOT NULL PK | ETL — unique posting-leg ID | drill-down, joins |
| `transfer_id` | VARCHAR(100) | NOT NULL | ETL — groups legs of one transfer | net-zero check, transfer summary |
| `parent_transfer_id` | VARCHAR(100) | NULL | ETL — chain pointer | stuck-transfer, reversal checks |
| `transfer_type` | VARCHAR(30) | NOT NULL | ETL | filters; per-check views |
| `origin` | VARCHAR(30) | NOT NULL | ETL — `internal_initiated` / `external_force_posted` | force-post checks |
| `account_id` | VARCHAR(100) | NOT NULL | ETL — what account this leg hits | every check |
| `account_name` | VARCHAR(255) | NOT NULL | ETL (denormalized) | display |
| `control_account_id` | VARCHAR(100) | NULL | ETL — parent / GL summary account; NULL for top-level | hierarchy queries |
| `account_type` | VARCHAR(50) | NOT NULL | ETL — see canonical values | filters |
| `is_internal` | BOOLEAN | NOT NULL | ETL | scope filters |
| `signed_amount` | DECIMAL(14,2) | NOT NULL | ETL — `+` = money IN to account (`debit` in bank's bookkeeping); `−` = money OUT (`credit`). See **Sign convention** below. | net-zero check, drift |
| `amount` | DECIMAL(14,2) | NOT NULL | ETL — `ABS(signed_amount)` | display, filters |
| `status` | VARCHAR(20) | NOT NULL | ETL — `success` / `failed` | exclude failed from balance math |
| `posted_at` | TIMESTAMP | NOT NULL | ETL | timeline, ordering |
| `balance_date` | DATE | NOT NULL | ETL — `DATE(posted_at)`, denormalized | fast date filters |
| `external_system` | VARCHAR(100) | NULL | ETL — for external rows (`BankSync`, `PaymentHub`, etc.) | PR external txns |
| `memo` | VARCHAR(255) | NULL | ETL | display |
| `metadata` | TEXT | NULL | ETL — JSON; see metadata contract below | PR-specific extracts, source provenance |

### Constraints

```sql
CREATE TABLE transactions (
    transaction_id      VARCHAR(100)   PRIMARY KEY,
    transfer_id         VARCHAR(100)   NOT NULL,
    parent_transfer_id  VARCHAR(100),
    transfer_type       VARCHAR(30)    NOT NULL
        CHECK (transfer_type IN (
            'sale', 'settlement', 'payment', 'external_txn',
            'ach', 'wire', 'internal', 'cash',
            'funding_batch', 'fee', 'clearing_sweep'
        )),
    origin              VARCHAR(30)    NOT NULL DEFAULT 'internal_initiated'
        CHECK (origin IN ('internal_initiated', 'external_force_posted')),
    account_id          VARCHAR(100)   NOT NULL,
    account_name        VARCHAR(255)   NOT NULL,
    control_account_id  VARCHAR(100),
    account_type        VARCHAR(50)    NOT NULL,
    is_internal         BOOLEAN        NOT NULL,
    signed_amount       DECIMAL(14,2)  NOT NULL,
    amount              DECIMAL(14,2)  NOT NULL,
    status              VARCHAR(20)    NOT NULL DEFAULT 'success'
        CHECK (status IN ('success', 'failed')),
    posted_at           TIMESTAMP      NOT NULL,
    balance_date        DATE           NOT NULL,
    external_system     VARCHAR(100),
    memo                VARCHAR(255),
    metadata            TEXT,
    CHECK (metadata IS NULL OR metadata IS JSON)
);
```

### Indexes

```sql
CREATE INDEX idx_transactions_account_date ON transactions(account_id, posted_at);
CREATE INDEX idx_transactions_transfer     ON transactions(transfer_id);
CREATE INDEX idx_transactions_type_status  ON transactions(transfer_type, status);
CREATE INDEX idx_transactions_control      ON transactions(control_account_id);
CREATE INDEX idx_transactions_balance_date ON transactions(balance_date);
CREATE INDEX idx_transactions_parent       ON transactions(parent_transfer_id);
```

No GIN indexes on `metadata`. No expression indexes on JSON-path
extractions. If a metadata key needs to be indexed for performance, lift
it into a first-class column instead.

### Sign convention

`signed_amount > 0` means money flowing **into** the account named by
`account_id`; `signed_amount < 0` means money flowing **out**. The
invariant is mechanical — `daily_balances.balance` for any account-day
equals the cumulative `SUM(signed_amount)` over all success rows up to
and including that day, and the drift-check views rely on it. Every
`account_type` follows this rule, `merchant_dda` included: a sale
credits the merchant's sub-ledger (positive), a payment debits it
(negative).

Readers coming from bank's-bookkeeping literature will see the same
convention phrased as "+= debit, −= credit" — that's a general-ledger
perspective where positive increases assets / decreases liabilities. The
two readings are the same statement from opposite ends of the double-
entry: a +$100 row on a customer DDA is a "debit" to the GL and "money
IN" to the depositor, simultaneously. The code uses the account-holder
view throughout (KPI math, drift checks, dataset SQL), so when a
walkthrough or dashboard element says "Debit", read it as the bank's-
bookkeeping label for "positive `signed_amount`".

### What breaks if you skip a column

The DB constraints catch the obvious ones (PK, NOT NULL). The non-obvious
failure modes — where a column is *technically* nullable / defaultable
but downstream code silently misbehaves — are:

- **`parent_transfer_id` left NULL on chained transfers** — PR pipeline
  traversal can't link `external_txn → payment → settlement → sale`;
  the **Where's My Money** walkthrough returns nothing for affected
  merchants. AR's *Stuck in Internal Transfer Suspense* and
  *Reversed Transfers Without Credit-Back* checks both walk the chain
  via this FK and miss the entire chain when it's NULL.
- **`origin` left at its default `internal_initiated` for force-posts** —
  AR's **GL vs Fed Master Drift** check separates operator-initiated
  from Fed-forced drift via this column. A Fed force-post tagged
  `internal_initiated` reads as a normal posting and the drift check
  under-fires. The check is silent — you only notice when reconciliation
  shows up off-by-Fed-volume.
- **`control_account_id` left NULL on a sub-ledger row** — the row is
  treated as a top-level / ledger account. Sub-ledger drift roll-up to
  the parent ledger silently drops the row's amount; the Drift KPI
  reads low.
- **`status` left at default `success` on a failed leg** — drift math
  includes the failed amount, drift KPI fires falsely, alert fatigue.
- **`is_internal` set wrong (e.g., `TRUE` for a Fed account)** — the
  external-rows scope filter on PR's reconciliation tab pulls Fed rows
  into the merchant view. *Show Only External* toggles do the wrong
  thing.
- **`account_name`, `memo`** — display only; no functional consequence,
  but tooltips and tables show NULL/empty cells.
- **`external_system` left NULL for an `external_txn` row** — the PR
  Payment Reconciliation tab's *External System* filter pivot collapses
  to "(empty)"; analysts can't slice by clearing system.

If your ETL writes a column and the dashboard goes dark, this list is
the first place to look — the symptom-to-column mapping is rarely 1:1
because checks compose.

---

## Table 2 — `daily_balances`

One row per (account, date) snapshot. Populated by upstream balance
feeds — typically core banking for internal accounts, Fed statement for
the FRB master, processor reports for clearing accounts. Stored
balances are compared against balances **computed** from `transactions`
via the drift-check views; non-zero drift surfaces in the Exceptions
tab.

### Columns

| Column | Type | Null? | Populated by | Consumed by |
|---|---|---|---|---|
| `account_id` | VARCHAR(100) | NOT NULL | ETL | every balance query |
| `account_name` | VARCHAR(255) | NOT NULL | ETL (denormalized) | display |
| `control_account_id` | VARCHAR(100) | NULL | ETL — parent account; NULL = ledger / top-level | hierarchy queries |
| `account_type` | VARCHAR(50) | NOT NULL | ETL | filters |
| `is_internal` | BOOLEAN | NOT NULL | ETL | scope filters |
| `balance_date` | DATE | NOT NULL | ETL | timeline |
| `balance` | DECIMAL(14,2) | NOT NULL | upstream balance feed | drift check (stored side) |
| `metadata` | TEXT | NULL | ETL — JSON; carries limits on ledger rows, source provenance everywhere | limit-breach check, source filters |

### Constraints

```sql
CREATE TABLE daily_balances (
    account_id          VARCHAR(100)   NOT NULL,
    account_name        VARCHAR(255)   NOT NULL,
    control_account_id  VARCHAR(100),
    account_type        VARCHAR(50)    NOT NULL,
    is_internal         BOOLEAN        NOT NULL,
    balance_date        DATE           NOT NULL,
    balance             DECIMAL(14,2)  NOT NULL,
    metadata            TEXT,
    PRIMARY KEY (account_id, balance_date),
    CHECK (metadata IS NULL OR metadata IS JSON)
);
```

### Indexes

```sql
CREATE INDEX idx_daily_balances_date    ON daily_balances(balance_date);
CREATE INDEX idx_daily_balances_control ON daily_balances(control_account_id, balance_date);
```

### What breaks if you skip a column

- **`balance` populated incorrectly (or the row missing entirely on a
  given date)** — the drift check has nothing to compare the
  recomputed balance against. Drift KPI either reads 0 (row missing)
  or fires for every account that day (stored balance defaults to 0
  and recomputed balance is the day's net).
- **`control_account_id` left NULL on a sub-ledger row** — same
  consequence as on `transactions`: the row is treated as top-level,
  drift roll-up drops it.
- **`metadata.limits` not populated on the relevant ledger rows** —
  the AR limit-breach KPI reads 0 not because nothing breached but
  because no limits exist to breach. Silent failure — operations
  thinks the bank's outflow caps are healthy when they're actually
  unenforced.
- **Daily snapshots missing for a date** — the drift timeline shows a
  gap; aging buckets compute against the wrong "as of" date.

---

## Account hierarchy via `control_account_id`

The two tables both carry a self-referential FK column,
`control_account_id`. This is the **standard accounting term** — the
"control account" is the GL summary account that aggregates a
subsidiary ledger's detail accounts.

For Data Integration Team readers without an accounting background:
think of `control_account_id` as **the parent account in the FK sense**.
A row whose `control_account_id IS NULL` is a top-level / ledger
account. A row with `control_account_id = '<some-other-account>'` is a
sub-ledger detail account that rolls up to that control account.

```
account_id              control_account_id   account_type        is top-level?
gl-1010                 NULL                 gl_control          yes (ledger)
gl-2010                 NULL                 gl_control          yes (ledger)
900-0001                gl-2010              merchant_dda        no (sub-ledger)
800-0002                gl-2010              dda                 no (sub-ledger)
ext-frb-master          NULL                 external_counter    yes (ledger)
```

Direct postings to a ledger account (e.g., a force-post at the
clearing-sweep level) are recorded as `transactions` rows whose
`account_id` is the ledger and whose `control_account_id` is `NULL`.

---

## Canonical `account_type` values

`account_type` describes the **role** of the account, not its
structural level — level derives from `control_account_id IS NULL`.

| `account_type` | What it is |
|---|---|
| `gl_control` | A General Ledger control account (1010 Cash, 1810 ACH Settlement, 2010 Customer Deposits, etc.). Always top-level. |
| `dda` | A Demand Deposit Account belonging to a customer (commercial). |
| `merchant_dda` | A DDA belonging to a merchant customer (PR side). Carries merchant-specific metadata on its `transactions` rows. |
| `external_counter` | An account at an external party (FRB Master, processor clearing, etc.). `is_internal = FALSE`. |
| `concentration_master` | The Cash Concentration Master sub-ledger (gl-1850 family). |
| `funds_pool` | A funds-pool account. |

This list extends as new account roles enter the demo. Add a row above;
do not pack the structural level into `account_type`.

---

## The `metadata` text column contract

`metadata` is a `TEXT` column on both tables, constrained to
`IS JSON`. It is the universal "extras" container — a single column
that lets Phase H consumers add new fields without schema churn.

**All extraction goes through SQL/JSON path functions:**

```sql
-- Read a scalar
SELECT JSON_VALUE(metadata, '$.card_brand') AS card_brand
FROM transactions WHERE transfer_type = 'sale';

-- Read a nested scalar
SELECT JSON_VALUE(metadata, '$.limits.ach') AS ach_limit
FROM daily_balances WHERE control_account_id IS NULL;

-- Filter by existence
SELECT * FROM transactions
WHERE JSON_EXISTS(metadata, '$.merchant_account_id');
```

**Forbidden** (Postgres-specific, not portable): `metadata->>'key'`,
`metadata->'key'`, `metadata @> '{...}'`, `metadata ? 'key'`.

### Canonical keys

#### On every row (both tables)

| Key | Type | Why it matters |
|---|---|---|
| `source` | string | **Provenance.** Where did this row come from? Drives Fraud / AML filtering ("show me only force-posted activity from the Fed feed"). Values: `core_banking`, `fed_statement`, `manual_force_post`, `sweep_engine`, `processor_report`, etc. Phase G populates this on every row written by demo data. |

#### On `transactions` rows where `transfer_type = 'sale'` (PR merchant sales)

| Key | Type | Why it matters |
|---|---|---|
| `card_brand` | string | Filter / segment merchant analytics. Values: `visa`, `mastercard`, `amex`, etc. |
| `card_last_four` | string | Display in transaction detail table. |
| `payment_method` | string | `card` / `cash` / etc. — display + segment. |
| `cashier` | string | Per-cashier reporting. |
| `merchant_account_id` | string | **Cross-check anchor.** Ties the sale back to the merchant_dda account_id. Used by the Phase H sale-vs-settlement merchant cross-check (does the sale's recorded merchant match the recipient account when the funds eventually settle?). |
| `merchant_name` | string | Display in merchant-side tables. |
| `merchant_type` | string | Filter / segment by merchant type (`franchise` / `independent` / `cart`). |
| `settlement_id` | string | Chain to which settlement transferred this sale. |
| `taxes`, `tips`, `discount_percentage` | string (numeric) | Optional sales metadata. |

#### On `transactions` rows where `transfer_type = 'settlement'` (PR settlement aggregates)

| Key | Type | Why it matters |
|---|---|---|
| `settlement_type` | string | `daily` / `weekly` / `monthly` — drives the merchant-cadence pivot on the Settlements sheet and the "is yesterday's batch overdue?" logic in *Did All Merchants Get Paid Yesterday*. |
| `sale_count` | string (numeric) | How many sales rolled into this settlement. Drives the per-settlement sale-count column and the *Sale ↔ Settlement Mismatch* check's denominator. |

#### On `transactions` rows where `transfer_type = 'payment'` (PR merchant payouts)

| Key | Type | Why it matters |
|---|---|---|
| `settlement_id` | string | Chain back to the settlement that produced this payment. |
| `payment_status` | string | `paid` / `pending` / `returned`. |
| `is_returned` | string | `'true'` / `'false'`. Quoted to keep JSON shape simple. |
| `return_reason` | string | Why a return was generated (NSF / processor reject / etc.). |
| `external_transaction_id` | string | Chain to the external_txn that observed this payment. |

#### On `transactions` rows where `transfer_type = 'external_txn'` (external observations)

| Key | Type | Why it matters |
|---|---|---|
| `record_count` | string (numeric) | How many internal payments this external txn aggregates. |

#### On `transactions` rows generated by Phase H ingest (external bank statement)

| Key | Type | Why it matters |
|---|---|---|
| `source` | `'fed_statement'` | Distinguishes Phase H statement-ingest rows from core-banking rows. |
| `statement_line_id` | string | Traceability back to the original Fed statement line. |

#### On `daily_balances` rows where `control_account_id IS NULL` (ledger rows)

| Key | Type | Why it matters |
|---|---|---|
| `limits` | object | Per-transfer-type daily outflow caps for sub-ledgers under this control account. Read by the limit-breach check via `JSON_VALUE(db.metadata, '$.limits.' \|\| t.transfer_type)`. Example: `{"ach": 100000, "wire": 50000, "internal": 25000}`. |

### Why a `metadata` column instead of more first-class columns?

Two reasons:

1. **The Data Integration Team values one feed contract.** New fields
   demanded by Fraud / AML / future personas land in metadata without
   the ETL pipeline needing a schema migration.
2. **The dashboards consume a stable contract.** Dataset SQL extracts
   only the keys it needs via `JSON_VALUE`; new metadata keys don't
   break anything.

If a key becomes a first-class consumer (appears in many `WHERE` /
`GROUP BY` clauses across many checks), promote it from metadata to a
real column. Don't preemptively promote everything.

---

## Computed views catalogue

Every existing dashboard view restates against the new tables. **The
view names and column projections do not change** — only their
underlying table references move from `posting` / `transfer` /
`ar_*_daily_balances` / `pr_*` to `transactions` / `daily_balances`.

Phase G migrates the views in this order (one commit per dataset, each
guarded by its `DatasetContract`):

| View | Today reads | Will read |
|---|---|---|
| `ar_subledger_balance_drift` | `posting`, `ar_subledger_daily_balances`, etc. | `transactions`, `daily_balances` |
| `ar_ledger_balance_drift` | `posting`, `ar_ledger_daily_balances`, etc. | `transactions`, `daily_balances` |
| `ar_transfer_summary` + `ar_transfer_net_zero` | `posting`, `transfer`, `ar_subledger_accounts` | `transactions` |
| `ar_subledger_overdraft` | `ar_subledger_daily_balances` | `daily_balances` |
| `ar_subledger_limit_breach` | `posting`, `transfer`, `ar_subledger_accounts`, `ar_ledger_accounts`, `ar_ledger_transfer_limits` | `transactions`, `daily_balances` (limits via `JSON_VALUE` on ledger rows) |
| `ar_sweep_target_nonzero` | `ar_subledger_daily_balances`, `ar_subledger_accounts`, `ar_ledger_accounts` | `daily_balances` |
| `ar_concentration_master_sweep_drift` | `posting`, `transfer`, `ar_subledger_accounts` | `transactions` |
| `ar_ach_orig_settlement_nonzero` | `ar_ledger_daily_balances`, `ar_ledger_accounts` | `daily_balances` |
| `ar_ach_sweep_no_fed_confirmation` | `transfer`, `posting` | `transactions` |
| `ar_fed_card_no_internal_catchup` | `transfer`, `posting` | `transactions` |
| `ar_gl_vs_fed_master_drift` | `transfer`, `posting` | `transactions` |
| `ar_internal_transfer_stuck` | `transfer`, `posting` | `transactions` |
| `ar_internal_reversal_uncredited` | `transfer`, `posting` | `transactions` |
| `ar_internal_transfer_suspense_nonzero` | `ar_ledger_daily_balances`, `ar_ledger_accounts` | `daily_balances` |
| 3 cross-check rollups | their underlying views | unchanged (re-aggregate the migrated views) |
| `pr_payment_recon_view` | `pr_external_transactions`, `pr_payments` | `transactions` (filter by `transfer_type IN ('external_txn', 'payment')`) |
| `pr_sale_settlement_mismatch` | `pr_settlements`, `pr_sales` | `transactions` (filter by `transfer_type IN ('settlement', 'sale')`) |
| `pr_settlement_payment_mismatch` | `pr_payments`, `pr_settlements` | `transactions` |
| `pr_unmatched_external_txns` | `pr_external_transactions`, `pr_payments` | `transactions` |

The actual SQL for each migrated view lives in
`src/quicksight_gen/account_recon/datasets.py` and
`src/quicksight_gen/payment_recon/datasets.py`. See those files for
the current shape; Phase G rewrites each in turn.

---

## Materialized views

One view in the schema is materialized rather than recomputed on every
read: **`ar_unified_exceptions`**. The Today's Exceptions sheet feeds
from this single object instead of a 14-block `UNION ALL` composed at
dataset-load time. The transitive read graph (14 per-check views, each
scanning `transactions` and/or `daily_balances`) was too heavy for
QuickSight Direct Query — without materialization the sheet would not
render. Materializing makes load instant.

### The refresh contract

`ar_unified_exceptions` is **not** auto-refreshed. After every ETL
load, run:

```sql
REFRESH MATERIALIZED VIEW ar_unified_exceptions;
```

The demo's `quicksight-gen demo apply` command issues this REFRESH
automatically after seeding; production ETL pipelines must do the
same. Daily ETL → daily REFRESH is the expected cadence.

### Aging-column timing semantics

Two columns on the matview are computed from `CURRENT_DATE` at
**refresh time**, not at query time:

- `days_outstanding` — `(CURRENT_DATE - exception_date::date)`
- `aging_bucket` — derived from `days_outstanding` (5 fixed bands:
  `1: 0-1 day`, `2: 2-3 days`, `3: 4-7 days`, `4: 8-30 days`,
  `5: >30 days`).

This means: if you skip a day's REFRESH, the dashboard's aging
columns **lag** by however many days the matview is stale. A daily
refresh tied to your ETL load keeps the aging accurate by construction.
A weekly refresh against a daily-loaded base would underreport every
row's age by up to six days; the underlying `exception_date` is still
correct, but the analyst-facing "how old is this break" will not be.

If your ETL load fails or is skipped, REFRESH the matview anyway so
aging stays calibrated against the dashboard's view of "today" — the
underlying check rows are unchanged but their age advances.

### Adding new materialized views

When a future check view's read cost crosses the same threshold,
materialize it under the same contract: declare it `MATERIALIZED`
in `schema.sql`, add the `REFRESH MATERIALIZED VIEW <name>;` line to
the `demo apply` block in `cli.py`, document it under this section
with its own refresh-cadence semantics, and announce the operator-
facing change in the release notes.

---

## ETL examples

These templates show how a Data Integration Team member populates the
two tables from upstream systems. Every column is annotated with **why**
to populate it — pick the columns your downstream consumers need.

### Example 1 — populating customer DDA postings from core banking

A core-banking system typically exposes a `gl_postings` table or
equivalent. Map it like this:

```sql
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, memo, metadata
)
SELECT
    p.posting_id,
    p.transfer_id,
    p.transfer_type,
    'internal_initiated'                AS origin,
    p.account_number                    AS account_id,
    a.account_name,                                     -- WHY: drives display in tables and tooltips
    a.gl_control_account                AS control_account_id,
                                                        -- WHY: drives ledger / sub-ledger drift roll-up
    a.account_role                      AS account_type,
                                                        -- WHY: filters and per-product views
    a.is_bank_owned                     AS is_internal,
                                                        -- WHY: separates the bank's accounts from external counterparties
    p.signed_amount,
    ABS(p.signed_amount)                AS amount,      -- WHY: display + amount filters
    CASE WHEN p.posting_status = 'P' THEN 'success' ELSE 'failed' END,
                                                        -- WHY: drift checks must exclude failed legs
    p.posting_timestamp                 AS posted_at,
    p.posting_timestamp::date           AS balance_date, -- WHY: fast date filters without expression-cast in WHERE
    p.memo,
    JSON_OBJECT('source' VALUE 'core_banking')          -- WHY: provenance — Fraud / AML filter on this
FROM core_banking.gl_postings p
JOIN core_banking.accounts a ON a.account_number = p.account_number
WHERE p.posting_date >= CURRENT_DATE - INTERVAL '7 days';
```

### Example 2 — populating daily balance snapshots

```sql
INSERT INTO daily_balances (
    account_id, account_name, control_account_id, account_type,
    is_internal, balance_date, balance, metadata
)
SELECT
    b.account_number                    AS account_id,
    a.account_name,
    a.gl_control_account                AS control_account_id,
    a.account_role                      AS account_type,
    a.is_bank_owned                     AS is_internal,
    b.balance_date,
    b.eod_balance                       AS balance,     -- WHY: drift check stored side
    JSON_OBJECT('source' VALUE 'core_banking')
FROM core_banking.account_balances b
JOIN core_banking.accounts a ON a.account_number = b.account_number;
```

### Example 3 — recording per-ledger limits in `daily_balances.metadata`

Limits live on the LEDGER (top-level) row, day by day. To enforce a
$100k/day ACH outflow cap on ledger `gl-2010` starting 2025-09-01:

```sql
UPDATE daily_balances
SET metadata = JSON_OBJECT(
    'source' VALUE 'core_banking',
    'limits' VALUE JSON_OBJECT(
        'ach' VALUE 100000,
        'wire' VALUE 50000,
        'internal' VALUE 25000
    )
)
WHERE account_id = 'gl-2010'
  AND balance_date >= DATE '2025-09-01';
```

The limit-breach view reads each transaction's daily aggregate and
joins to the relevant ledger's daily_balances row:

```sql
SELECT t.account_id, t.balance_date, t.transfer_type,
       SUM(ABS(t.signed_amount))             AS outbound_total,
       JSON_VALUE(db.metadata, '$.limits.' || t.transfer_type)::numeric AS daily_limit
FROM transactions t
JOIN daily_balances db
  ON db.account_id   = t.control_account_id
 AND db.balance_date = t.balance_date
WHERE t.signed_amount < 0
  AND t.status = 'success'
GROUP BY t.account_id, t.balance_date, t.transfer_type, db.metadata
HAVING SUM(ABS(t.signed_amount))
     > JSON_VALUE(db.metadata, '$.limits.' || t.transfer_type)::numeric;
```

### Example 4 — populating PR sales with merchant cross-check metadata

PR sales need extra fields in `metadata` so Phase H can build a
sale-vs-settlement merchant cross-check:

```sql
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, account_id, account_name,
    control_account_id, account_type, is_internal,
    signed_amount, amount, status, posted_at, balance_date, metadata
)
SELECT
    'sale-' || s.sale_id                AS transaction_id,
    'sale-xfer-' || s.sale_id           AS transfer_id,
    'sale'                              AS transfer_type,
    'pr-sub-' || s.merchant_id          AS account_id,
    m.merchant_name                     AS account_name,
    'pr-merchant-ledger'                AS control_account_id,
    'merchant_dda'                      AS account_type,
    TRUE                                AS is_internal,
    s.amount                            AS signed_amount,
    ABS(s.amount)                       AS amount,
    'success'                           AS status,
    s.sale_timestamp                    AS posted_at,
    s.sale_timestamp::date              AS balance_date,
    JSON_OBJECT(
        'source'              VALUE 'core_banking',
        'card_brand'          VALUE s.card_brand,
        'cashier'             VALUE s.cashier,
        'payment_method'      VALUE s.payment_method,
        'merchant_account_id' VALUE 'pr-sub-' || s.merchant_id,
                                          -- WHY: Phase H cross-checks the
                                          -- sale's recorded merchant against
                                          -- the recipient account when funds
                                          -- eventually settle. Don't skip.
        'merchant_name'       VALUE m.merchant_name,
        'merchant_type'       VALUE m.merchant_type,
        'settlement_id'       VALUE s.settlement_id
    )
FROM core_banking.merchant_sales s
JOIN core_banking.merchants m ON m.merchant_id = s.merchant_id;
```

### Example 5 — bank-statement ingest (Phase H)

When the GL Reconciliation team's bank-statement-comparison view lands
in Phase H, it consumes statement lines as `transactions` rows with
`is_internal = FALSE`, source-tagged in metadata:

```sql
INSERT INTO transactions (
    transaction_id, transfer_id, transfer_type, origin,
    account_id, account_name, control_account_id, account_type,
    is_internal, signed_amount, amount, status,
    posted_at, balance_date, external_system, memo, metadata
)
SELECT
    'fed-' || f.statement_line_id       AS transaction_id,
    'fed-' || f.batch_id                AS transfer_id,
    'ach'                               AS transfer_type,
    'external_force_posted'             AS origin,
    'ext-frb-master-snb'                AS account_id,
    'FRB Master — SNB'                  AS account_name,
    NULL                                AS control_account_id,
    'external_counter'                  AS account_type,
    FALSE                               AS is_internal,
    f.signed_amount,
    ABS(f.signed_amount)                AS amount,
    'success'                           AS status,
    f.statement_timestamp               AS posted_at,
    f.statement_date                    AS balance_date,
    'FRB'                               AS external_system,
    f.statement_memo                    AS memo,
    JSON_OBJECT(
        'source'            VALUE 'fed_statement',
        'statement_line_id' VALUE f.statement_line_id    -- WHY: traceability back to the original Fed statement line
    )
FROM fed_feed.statement_lines f
WHERE f.statement_date = CURRENT_DATE - 1;
```

---

## Going deeper — Data Integration Handbook walkthroughs

The walkthroughs below convert this contract into task-shaped guides.

- [How do I populate `transactions` from my core banking system?](walkthroughs/etl/how-do-i-populate-transactions.md) —
  the canonical mapping walkthrough.
- [How do I prove my ETL is working before going live?](walkthroughs/etl/how-do-i-prove-my-etl-is-working.md) —
  pre-deploy validation invariants (net-to-zero, drift recompute,
  no orphan parent chains) + a "what dashboard you should see"
  checklist.
- [How do I tag a force-posted external transfer correctly?](walkthroughs/etl/how-do-i-tag-a-force-posted-transfer.md) —
  the `origin` field + `parent_transfer_id` chain mechanics.
- [How do I add a metadata key without breaking the dashboards?](walkthroughs/etl/how-do-i-add-a-metadata-key.md) —
  the extension contract.
- [What do I do when the demo passes but my prod data fails?](walkthroughs/etl/what-do-i-do-when-demo-passes-but-prod-fails.md) —
  symptom-organized debugging recipes.

The full landing page lives at `docs/handbook/etl.md` (lands in
H.8.5.E).

---

## Forbidden SQL patterns

Anything in this list MUST NOT appear in the demo schema (emitted by
`quicksight-gen demo schema --all`), dataset SQL, or computed view
bodies. The dialect compatibility constraint is a hard wall.

| Forbidden | Use instead |
|---|---|
| `JSONB`, `JSON` data types | `TEXT` with `IS JSON` constraint |
| `metadata ->> 'key'` | `JSON_VALUE(metadata, '$.key')` |
| `metadata -> 'key'` | `JSON_QUERY(metadata, '$.key')` |
| `metadata @> '{...}'` | `JSON_EXISTS(metadata, '$.key ? (@ == "value")')` |
| `metadata ? 'key'` | `JSON_EXISTS(metadata, '$.key')` |
| GIN index on JSON column | B-tree on a first-class column (promote the metadata key if it needs an index) |
| Postgres extensions (`pg_trgm`, `uuid-ossp`, etc.) | none — pick a portable alternative |
| Array column types (`text[]`, etc.) | a child table or JSON array in `metadata` |
| Range column types | two columns (start, end) |
| `DISTINCT ON (...)` | `ROW_NUMBER() OVER (...)` + filter |
| `ILIKE` | `LOWER(col) LIKE LOWER(pattern)` |
| Postgres-flavored window-function quirks | SQL standard window syntax only |

If you need a feature this list forbids, discuss before writing — there
is almost always a portable alternative, and the alternative should be
the only thing that lands in the repo.
