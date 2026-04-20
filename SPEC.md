# QuickSight Analysis Generator — Spec

## Goal

Generate AWS QuickSight dashboards that help non-technical financial users find and triage problems. Two independent dashboards (Payment Reconciliation + Account Reconciliation) ship from one codebase, share a theme, account, datasource, and CLI surface, and are deployed via boto3 (delete-then-create, idempotent).

## Users

Two audiences, with different needs:

- **Developers / Product Owners** customizing the apps onto their backends:
  - Need to swap the SQL behind each dataset without rewriting the visual / filter / drill-down layer above it
  - Edit each behavior in one place (DRY)
  - Trust a comprehensive test suite to catch regressions
  - Iterate fast — regenerate + redeploy in one command
  - Reskin via theme presets so the dashboards land inside the host system
- **Non-technical accountants** consuming the dashboards:
  - Job is to find problems and route them to the team that fixes them
  - These dashboards are unfamiliar — plain-English labels, hint text, and Getting Started rich text are critical
  - Strong accounting background; not programmers
  - Need to recognize *when* something needs investigation, not how to fix the broken upstream system

## Background

Two financial reporting apps:

- **Payment Reconciliation** — merchant-acquiring view: sales bundle into settlements; settlements pay merchants; payments leave the internal system and must match external systems aggregating those payments.
- **Account Reconciliation** — treasury / cash-management view: ledger control accounts and customer DDAs, double-entry transfers, daily balance drift detection, and limit / overdraft / suspense exception checks.

Both apps query the same datasource. In production a pre-existing datasource ARN is passed via config; in demo mode the project provisions its own datasource from `demo_database_url` and seeds a Postgres database with shared base tables.

Datasets are custom-SQL, direct query (no SPICE) — seed changes show up immediately after `demo apply`, no refresh step. Each dataset has a `DatasetContract` (column name + type list); the SQL is one implementation of the contract. The visual, filter, and drill layer binds to contract columns only — customers swap SQL, the rest stays identical. The customer's customization work is bounded by the column contract, not free-form.

## Domain Model

### Shared base layer

Both apps feed two physical tables, defined in `demo/schema.sql` and documented as a feed contract in `docs/Schema_v3.md`:

- **`transactions`** — one row per money-movement leg. Carries `transaction_id` PK, `transfer_id` (groups legs of one financial event), `parent_transfer_id` (chains transfers — used by PR for `external_txn → payment → settlement → sale`), `transfer_type`, `origin`, `account_id`, denormalized account fields (`account_name`, `account_type`, `control_account_id`, `is_internal`), `signed_amount` (positive = debit, negative = credit), `amount` (absolute), `status`, `posted_at`, `balance_date`, `external_system`, `memo`, and a `metadata TEXT` column constrained `IS JSON` for app-specific keys.
- **`daily_balances`** — one row per `(account_id, balance_date)`. Carries the same denormalized account fields as `transactions` plus `balance` (stored end-of-day) and a `metadata TEXT` JSON column. AR attaches per-day limit configuration here so the limit-breach view stays a single SELECT.

AR also reads three dimension tables that don't carry transactions: `ar_ledger_accounts`, `ar_subledger_accounts`, and `ar_ledger_transfer_limits`.

Six canonical `account_type` values discriminate which app a row belongs to:

- `gl_control` — AR GL control accounts; PR also uses for the synthetic `pr-merchant-ledger` control row
- `dda` — AR customer demand-deposit accounts
- `merchant_dda` — PR merchant accounts
- `external_counter` — external counterparties: FRB Master, payment processors, PR external customer pool / external rail
- `concentration_master` — the cash concentration target
- `funds_pool` — reserved; not currently emitted by the demo seed

`control_account_id` is a self-referential FK. Non-failed legs of a non-single-leg transfer net to zero.

JSON metadata uses portable SQL/JSON path syntax (`JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`) — no JSONB, no `->>` / `->` / `@>` / `?` operators, no GIN indexes on JSON. PostgreSQL 17+ is required for `demo apply`. The demo schema is constrained to a portable subset so the SQL ports cleanly to a more conservative target RDBMS.

### Payment Reconciliation

Pipeline: **Sales → Settlements → Payments → External Transactions**, plus a Payment Reconciliation tab that reconciles internal payments against external transactions side-by-side.

- Merchants make sales at locations
- Sales bundle into settlements; settlement type depends on merchant type
- Settlements get paid to merchants as payments
- Payments leave the internal system; only payments reconcile against external systems
- Multiple external systems (BankSync, PaymentHub, ClearSettle) aggregate 1+ internal payments into one external transaction
- A match is valid only when the external total equals the sum of linked payments — no partials
- Match statuses: `matched`, `not_yet_matched`, `late` (threshold: `late_default_days`, default 30; user-adjustable per-tab slider)
- Side-by-side mutual filtering on the Payment Reconciliation tab: clicking an external txn filters its payments; clicking a payment filters back
- All 5 PR exception checks plus the Payment Recon tab carry `aging_bucket` (5 hardcoded bands) with horizontal aging bar charts

PR rows use `account_type IN ('gl_control', 'merchant_dda', 'external_counter')`. Merchant sub-ledgers and the external customer pool / external rail roll up to the synthetic `pr-merchant-ledger` control account. PR-specific metadata (`card_brand`, `cashier`, `settlement_type`, `payment_method`, `is_returned`, `return_reason`, etc.) lives in the `metadata` JSON column and is read via `JSON_VALUE(metadata, '$.<key>')`. The transfer chain is expressed through `parent_transfer_id` linkage: `external_txn → payment → settlement → sale`.

Refunds are rows with negative `signed_amount` and `metadata.sale_type = 'refund'`; they net out within a settlement and may make a settlement (and downstream payment) negative.

### Account Reconciliation

Pipeline: **Ledger accounts → Sub-ledger accounts → Transactions → Exceptions**, with daily balance snapshots driving drift detection.

- Money: decimal, single currency to 2dp, no fractional reserves / conversions
- "Internal" / "external" describe reconciliation scope, not system ownership. External account balances aren't this app's concern (regulator territory)
- Every transfer is a set of `transactions` legs (grouped by `transfer_id`) that must net to zero. Failed legs don't count toward the net
- Legs target sub-ledger accounts OR ledger control accounts directly (funding batches, fee assessments, clearing sweeps, all CMS-driven sweeps); `account_id` and `control_account_id` express the hierarchy
- Daily balance snapshots in `daily_balances` allow drift detection: recomputed balance vs. stored balance
- Per-ledger limits live in `ar_ledger_transfer_limits` and are surfaced through the `daily_balances.metadata` JSON. A ledger may have limits defined for only some types — undefined means "no limit enforced"

Invariants surfaced as exception checks:

- **Ledger drift**: stored ledger balance = Σ direct ledger postings + Σ sub-ledger stored balances, evaluated as-of the reporting date.
- **Sub-ledger drift**: stored sub-ledger balance = Σ posted transactions on that sub-ledger that day.
- **Sub-ledger overdraft**: sub-ledger stored balance must not go below 0 on any day.
- **Transfer net-zero**: non-failed legs of a non-single-leg transfer sum to zero.
- **Sub-ledger limit breach**: Σ |outbound posted amounts of type T| for a sub-ledger on a day must not exceed its ledger's configured limit for type T.

Transactions carry `transfer_type` (`ach`, `wire`, `internal`, `cash`, `funding_batch`, `fee`, `clearing_sweep`) for limit checking, and an `origin` tag (`internal_initiated` / `external_force_posted`) that surfaces whether the row originated from the normal internal flow or was pushed in out-of-band. AR datasets filter `WHERE transfer_type IN (...)` to exclude PR transfer types from the shared base tables; drift / overdraft views also carry `account_id NOT LIKE 'pr-%'` filters as a co-residency safety net.

Transfer memos denormalize onto each transaction; the earliest transaction's memo wins for display.

#### Exceptions tab structure

Three cross-check rollups sit at the top to teach error-class recognition; the per-check details below let analysts drill the specific row that's broken; two drift timelines at the bottom surface systemic issues.

- **Cross-check rollups** (top of tab):
  - **Expected-zero EOD rollup** — union of checks where a control or sweep target should be zero at end-of-day but isn't (concentration master sweep drift, ACH origination settlement non-zero, internal transfer suspense non-zero, sweep target non-zero).
  - **Two-sided post-mismatch rollup** — union of checks where one side of a paired posting is missing or stuck (Fed-card no internal catch-up, ACH sweep no Fed confirmation, internal reversal uncredited, internal transfer stuck, GL vs. FRB master drift).
  - **Balance drift timelines rollup** — ledger drift + sub-ledger drift over time.
- **Baseline checks**: sub-ledger drift, ledger drift, non-zero transfers, sub-ledger limit breach, sub-ledger overdraft.
- **CMS-specific checks** (Phase F): sweep target non-zero, concentration master sweep drift, ACH origination settlement non-zero, ACH sweep no Fed confirmation, Fed card no internal catch-up, GL vs. FRB master drift, internal transfer stuck, internal transfer suspense non-zero, internal reversal uncredited.

Every check carries `days_outstanding` and `aging_bucket` (5 hardcoded bands: 0-1d, 2-3d, 4-7d, 8-30d, >30d) for time-based urgency triage; aging bar charts visualize the distribution.

## Demo Scenarios

Reports are hard to understand abstractly; a narrative helps evaluators see the point. Punny, inoffensive theming is encouraged. ~80/20 success/failure ratio illustrates the tool's value at catching problems. Time-distributed but low-volume.

- **Payment Reconciliation — "Sasquatch National Bank"** — merchant bank in the Pacific Northwest serving local coffee shops. Morning-focused sales. Optional-metadata and merchant-name variety drives the punny flavor. Shops: Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, Wildman's Roastery.
- **Account Reconciliation — "Sasquatch National Bank — Cash Management Suite (CMS)"** — same Pacific-Northwest bank from PR, viewed through treasury after SNB absorbed Farmers Exchange Bank's commercial book. Eight internal GL control accounts (Cash & Due From FRB, ACH Origination Settlement, Card Acquiring Settlement, Wire Settlement Suspense, Internal Transfer Suspense, Cash Concentration Master, Internal Suspense / Reconciliation, Customer Deposits — DDA Control) sit above per-customer DDAs for the three coffee retailers shared with PR (Bigfoot Brews, Sasquatch Sips, Yeti Espresso) and four commercial customers (Cascade Timber Mill, Pinecrest Vineyards, Big Meadow Dairy, Harvest Moon Bakery). Four telling-transfer flows from CMS plant both success cycles and characteristic failures: ZBA / Cash Concentration sweep → Concentration Master; daily ACH origination sweep → FRB Master Account; external force-posted card settlement → Card Acquiring Settlement; on-us internal transfer → Internal Transfer Suspense → destination DDA.

The two personas share three customer DDAs (the coffee retailers) but the rest of the data is disjoint, separated by `account_type` / `transfer_type`. Determinism is locked by a SHA256 hash assertion on the full seed SQL output — any generator change that shifts a single byte fails loudly. Re-lock by pasting the new hash in when intentional.

## Open Questions

Tracked for a future phase, not in scope for current work:

- **AR Exceptions layout** is dense (3 rollups + 14 checks + aging bars). The sheet may benefit from a persona-driven redesign rather than additive growth.
- **PR pipeline tab structure**. Under the shared-base model, Sales / Settlements / Payments are values of `transfer_type`, not separate tables. The current per-step tab structure is preserved from the pre-flatten era; whether tabs should remain entity-shaped or shift to type-filtered views is open.
- **AR co-residency safety filters** (`account_id NOT LIKE 'pr-%'` in drift / overdraft views) exist because the demo currently runs both personas against one Postgres. They can be removed once the dual-persona demo splits.
- **Unified account dimension table**. AR currently keeps `ar_ledger_accounts` and `ar_subledger_accounts` separate; a single "all accounts" table would simplify some queries and align with the denormalize-don't-add-tables north star.
