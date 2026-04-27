# How do I map my production database to the two base tables?

*Customization walkthrough — Developer / Product Owner. Foundational. Read this first.*

## The story

You've stood up the demo, clicked through the dashboards, and
decided you want this product against your own data. Now you're
sitting in front of your bank's production database and asking
the load-bearing question: **how much work is this, actually?**

The honest answer: the visual layer (32+ datasets, 14 exception
checks, drill-downs, filters, theming) binds to a contract that
is two tables wide. Everything you see in the demo reads from
`transactions` and `daily_balances`. If you can land your data
into those two shapes — once, by your morning cut — every
dashboard works without further plumbing on the dashboard side.

The work that *isn't* trivial is the upstream ETL projection
itself: deciding which of your source tables map to a leg in
`transactions`, getting the sign convention right on
`signed_amount`, populating `parent_transfer_id` for chained
transfers, tagging force-posts. That work belongs to your data
integration team and lives in the
[Data Integration Handbook](../../handbook/etl.md). This
walkthrough is the *strategic* read for the product owner: what
your source system needs to expose, what shape the contract takes,
and the signals that you have a workable fit.

## The question

"My bank has a core banking system, a card processor feed, a
Fed statement file, and an in-house sweep engine. Can I get
**this product** running on **that data**, and what do I need
to know before I commit?"

## Where to look

Two reference points before you write a line of mapping code:

- **[Schema_v6.md → The minimum viable feed](../../Schema_v6.md#the-minimum-viable-feed)** —
  the 11 mandatory columns on `transactions` + 6 on
  `daily_balances`. Read these first. Anything beyond the
  minimum is conditional and can wait for v2.
- **`quicksight-gen demo etl-example --all -o etl-examples.sql`** —
  emits 11 canonical INSERT-pattern blocks (6 PR + 5 AR), each
  with a `-- WHY:` header and a `-- Consumed by:` pointer to
  the dashboard view that reads it. Reading these end-to-end
  takes about fifteen minutes and tells you exactly what shapes
  your projection has to land.

The contract is deliberately small. If you find yourself
proposing a third base table, push back: every persona we've
shipped (PR merchant settlement, AR treasury, CMS, the Phase K
Fraud / AML work) reads from these same two tables.

## What you'll see in the demo

After `quicksight-gen demo apply --all`, your demo Postgres
holds:

- **`transactions`** — every money-movement leg, one row per
  leg. Multiple legs of one financial event share a
  `transfer_id` and net to zero (the double-entry invariant).
- **`daily_balances`** — one row per `(account_id,
  balance_date)`. The `balance` column is what your ETL writes;
  the dashboard recomputes `SUM(signed_amount)` and surfaces
  the delta as Drift.
- **AR-only dimension tables** — `ar_ledger_accounts`,
  `ar_subledger_accounts`, `ar_ledger_transfer_limits`. These
  are configuration, not feed data; you populate them once
  during setup and update only when account structure changes.

That's it. No `pr_sales`, no `pr_settlements`, no
`ledger_postings`, no per-persona staging tables. Every
exception check, every drill-down, every aging bucket reads
from `transactions` and `daily_balances`.

## What it means

For your source-system-to-base-table mapping, three patterns
cover the common cases:

### Pattern 1 — Core banking → `transactions` + `daily_balances`

Your core banking system has a `gl_postings` (or equivalent)
detail table — one row per posting leg already. This is the
natural match for `transactions`. Your nightly EOD `account_balance`
snapshot maps to `daily_balances`. Most of the projection is a
column rename plus the sign-convention conversion.

This is the canonical case. The
[How do I populate `transactions` from my core banking system?](../etl/how-do-i-populate-transactions.md)
walkthrough has the full SQL projection.

### Pattern 2 — Card processor / external feed → `transactions` (`external_txn`)

Your card processor sends a daily settlement file. Each row is
the processor's view of money landing in your account. These
become `transactions` rows with `transfer_type = 'external_txn'`,
`origin = 'external_force_posted'`, and a populated
`external_system` (e.g., `BankSync`, `PaymentHub`).

You don't need a separate table for these. The dashboard's
matching logic (PR side) and force-post detection (AR side)
both work off these same rows distinguished by
`transfer_type` + `origin`.

### Pattern 3 — Sweep engine / internal transfer log → `transactions` (multi-leg)

Your CMS sweep engine emits one record per sweep operation —
"move $X from sub-ledger A to concentration master B". That
single record becomes **two** `transactions` rows (a debit leg
on A, a credit leg on B) sharing one `transfer_id`. The legs
must net to zero. The dashboard's drift checks read this directly.

Multi-leg projection is where the most ETL teams get tripped
up. Read
[How do I prove my ETL is working before going live?](../etl/how-do-i-prove-my-etl-is-working.md)
— Invariant 1 (every transfer's legs net to zero) is the
universal pre-flight check that catches multi-leg projection
bugs immediately.

## Drilling in

A few decisions to surface explicitly with your team before
you commit:

- **Sign convention.** `signed_amount > 0` means money IN to
  the account; `< 0` means money OUT. If your upstream uses
  the opposite convention (some core systems use bank's-
  bookkeeping where debits are positive on asset accounts and
  negative on liability accounts), you flip the sign in the
  ETL projection — *not* in a downstream view. Every dashboard
  check assumes our sign convention; flipping at the projection
  boundary keeps that assumption honest everywhere downstream.
- **`balance_date` is denormalized from `posted_at` deliberately.**
  The dashboard datasets do fast date-range scans on
  `balance_date` — populating it as a separate column (rather
  than expression-casting `posted_at::date` on every query) is
  a deliberate redundancy for query speed. Your ETL writes one
  extra column; the dashboard reads it without a cast.
- **`account_type` describes role, not structural level.** Six
  canonical values: `gl_control`, `dda`, `merchant_dda`,
  `external_counter`, `concentration_master`, `funds_pool`.
  Structural level (control vs. sub-ledger) derives from
  `control_account_id IS NULL`. Don't pack the level into the
  type field — see
  [Schema_v6.md → Canonical account_type values](../../Schema_v6.md#canonical-account_type-values).
- **`metadata` is the extension point, not a schema migration.**
  Your bank wants to surface a custom field (a transaction
  reference number, a regulatory flag, a per-merchant tier
  code). Add it as a JSON key in `metadata`; read it from
  dataset SQL via `JSON_VALUE`. No DDL change, no rebuild. See
  [How do I add a metadata key without breaking the dashboards?](../etl/how-do-i-add-a-metadata-key.md)
  for the ETL-side write pattern; the dashboard-side read
  pattern is in the *How do I add an app-specific metadata key?*
  walkthrough later in this handbook.

## Next step

Once you've decided this product fits your data:

1. **Stand up the schema.** `quicksight-gen demo schema -o
   schema.sql` writes the canonical DDL to a file you can
   inspect. Run it against a dev Postgres to land the empty
   tables.
2. **Hand the projection task to your data integration team.**
   The
   [Data Integration Handbook](../../handbook/etl.md) is
   their entry point. Walk them through the
   minimum-viable-feed columns, the sign convention, and the
   pre-flight invariants. Their first deliverable is one
   day's load against `transactions` + `daily_balances`.
3. **Validate with the dashboard.** Once a slice is loaded,
   open the AR Exceptions and PR Exceptions sheets. KPIs at 0
   with no drilldown rows means the feed landed cleanly. KPIs
   spiking unexpectedly is the signal to walk
   [What do I do when the demo passes but my prod data fails?](../etl/what-do-i-do-when-demo-passes-but-prod-fails.md)
   with your ETL team.
4. **Configure the deploy for your AWS account.** Once the
   data side works, the deployment side is one config file
   away — that's the *How do I configure the deploy for my AWS
   account?* walkthrough later in this handbook.

## Related walkthroughs

- [Data Integration Handbook → How do I populate transactions?](../etl/how-do-i-populate-transactions.md) —
  the ETL-engineer view: the actual SQL projection from
  `core_banking.gl_postings` to `transactions`.
- [Data Integration Handbook → How do I prove my ETL is working?](../etl/how-do-i-prove-my-etl-is-working.md) —
  the universal pre-flight invariants (net-zero, drift-recompute,
  parent-chain integrity) your ETL team runs before declaring a
  load complete.
- [Data Integration Handbook → How do I add a metadata key?](../etl/how-do-i-add-a-metadata-key.md) —
  the ETL-engineer view of metadata key extension. The
  customization counterpart (dashboard-side read pattern) is
  later in this handbook.
- [Schema_v6 → Getting Started for Data Teams](../../Schema_v6.md#getting-started-for-data-teams) —
  the column-level contract, including the per-column failure
  modes ("if you skip this, what dashboard breaks?").
