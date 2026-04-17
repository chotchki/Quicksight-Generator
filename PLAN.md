# PLAN — Phase B: Unified transfer schema + dataset column contracts

Goal: Introduce `transfer` + `posting` as the common schema primitives shared by both apps. Migrate AR onto the unified shape (light — already shaped this way). Migrate PR's sales/settlements/payments/external-txns onto transfer chains via `parent_transfer_id` (heavy lift). Promote each dataset's column list to an explicit contract so the SQL becomes one implementation of a stable interface. Drop legacy AR/PR detail tables once datasets are reading from the unified schema.

This is the largest phase of the major evolution in `SPEC.md`. Plan to land ~10 commits. Each sub-phase = one commit.

Out of scope for Phase B:
- Ledger-level direct postings (Phase C). Drift invariant for ledgers stays `Σ sub-ledger balances`.
- Reconciliation DSL or unified Exceptions tab (Phase D). Today's 9 bespoke checks stay independent — only their underlying SQL changes.
- Persona dashboard split (Phase E). Both apps continue producing one analysis + one dashboard each.
- Wiring `origin` into any filter / visual / check (Phase D).
- UI-level as-of date control (Phase D). Schema carries timestamps; queries continue to use `CURRENT_DATE` for now.
- Customer-facing column-contract guide / docs aimed at production schemas. The contract is internal to this codebase in Phase B.

Conventions:
- Branch: `phase-b-unified-schema`, cut from `main`. One sub-phase = one commit; cumulative release at the end.
- `demo apply` continues to drop-and-create. No staged migrations or backward-compat shims.
- `cleanup --yes` after deploy handles stale tagged resources.
- After each sub-phase, run `.venv/bin/pytest`. After each major checkpoint (B.4, B.6, B.10), run `./run_e2e.sh --parallel 4`.
- Demo data MUST stay deterministic (`random.Random(42)`); tests depend on byte-identical output where unchanged.
- Every sheet description and every visual subtitle stays present (existing coverage tests enforce this).

---

## Phase B.0 — Pin decisions

STOP here. Big-shape decisions cascade hard.

- [x] B.0.1 **Unified table names: `transfer` + `posting` (no prefix), or prefixed?** → **Configurable prefix** on the unified tables (default empty or derived from `resource_prefix`). Customers will need to fit these into existing databases. App-specific reference tables (`pr_merchants`, `pr_locations`, `ar_ledger_accounts`, etc.) keep their hard-coded `pr_`/`ar_` prefixes for now.
- [x] B.0.2 **PR sale postings need a counter-account. Introduce per-customer sub-ledgers, or single synthetic pool?** → **Single `pr_external_customer_pool` sub-ledger** as a transition path. Revisiting with per-customer modeling stays in scope for a later phase.
- [x] B.0.3 **PR chain direction: external_txn is parent or child?** → **External is parent.** Payments are children of external_txns; settlements are children of payments; sales are children of settlements. "Σ child amounts = parent amount" is the generic match check.
- [x] B.0.4 **Old PR/AR detail tables: drop or keep as views?** → **Drop entirely** after migration. Consistency is most important; no shims.
- [x] B.0.5 **Column contract shape: dataclass or registry?** → **Dataclass per dataset**, kept simple. Lives next to the SQL in `<app>/datasets.py`.
- [x] B.0.6 **`as_of` granularity?** → **Rely on existing** `posted_at` / daily-balance dates. As-of query refactor deferred to Phase D.
- [x] B.0.7 **`posting.signed_amount` vs. amount + direction?** → **signed_amount**. Sum-to-zero is `SUM(signed_amount) = 0`. Direction view can be added later if visuals need it.
- [x] B.0.8 **PR transfer_type values: keep separate or fold into AR's set?** → **Keep separate.** PR uses chain-link names (`sale`, `settlement`, `payment`, `external_txn`); AR uses rail names (`ach`, `wire`, `internal`, `cash`). `transfer_type` is a free string; CHECK constraint enumerates both vocabularies.

---

## Phase B.1 — Unified schema definition (additive)

Add `transfer` and `posting` to `demo/schema.sql` alongside the legacy AR/PR tables. Nothing dropped yet.

- [x] B.1.1 Add `transfer` table: `transfer_id PK`, `parent_transfer_id` (nullable FK self-ref), `transfer_type VARCHAR(30)`, `origin VARCHAR(30)` (`internal_initiated` / `external_force_posted`), `amount DECIMAL`, `status VARCHAR(20)`, `created_at TIMESTAMP`, `memo VARCHAR(255)`, `external_system VARCHAR(50)` (nullable).
- [x] B.1.2 Add `posting` table: `posting_id PK`, `transfer_id FK → transfer`, `account_id FK → ar_subledger_accounts`, `signed_amount DECIMAL`, `posted_at TIMESTAMP`, `status VARCHAR(20)` (`success` / `failed`).
- [x] B.1.3 Add indexes: `posting(transfer_id)`, `transfer(parent_transfer_id)`, `posting(account_id, posted_at)`.
- [x] B.1.4 CHECK constraints: `transfer.transfer_type IN (...)` enumerating both AR and PR vocabularies; `transfer.origin IN ('internal_initiated', 'external_force_posted')`; `posting.status IN ('success', 'failed')`.
- [x] B.1.5 No data inserted. `demo apply --all` should still succeed against existing legacy tables — empty `transfer` / `posting`.
- [x] B.1.6 `pytest` — schema structure tests in `test_demo_sql.py` updated to assert presence of new tables.
- [x] B.1.7 Commit — `Phase B.1: define unified transfer + posting schema (additive)`.

---

## Phase B.2 — Column contract abstraction

Add a `DatasetContract` dataclass and refactor existing dataset builders to consume it. Pure Python refactor — no SQL changes, no schema changes.

- [x] B.2.1 Add `common/dataset_contract.py`: `ColumnSpec(name, type, nullable, notes)` and `DatasetContract(name, description, columns)`.
- [x] B.2.2 Add a helper in `common/dataset_contract.py` (or extend `models.py`): `dataset_from_contract(contract, sql, datasource_arn, …) → Dataset`. Replaces the inline `Dataset(...)` construction in each builder.
- [x] B.2.3 Refactor every existing dataset builder (11 PR + 9 AR) to declare a `DatasetContract` and call the helper. SQL stays byte-identical; column lists are now contract-derived.
- [x] B.2.4 Add `tests/test_dataset_contract.py`: SELECT-clause parser asserts each builder's projected columns match its declared contract.
- [x] B.2.5 `pytest` clean — no behavior change, only refactor.
- [x] B.2.6 Commit — `Phase B.2: dataset column contract abstraction`.

---

## Phase B.3 — AR demo writes unified tables (dual-write)

AR generator emits to BOTH legacy AR tables AND the new `transfer` / `posting` tables, with equivalence asserted by tests. Nothing reads from the unified tables yet — this is the safety phase.

- [x] B.3.1 `account_recon/demo_data.py`: every legacy `ar_transfers` row also produces a `transfer` row (with same id, type, origin, amount, memo, created_at).
- [x] B.3.2 Every legacy `ar_transactions` row also produces a `posting` row (signed_amount = `+amount` for credits, `-amount` for debits; status mirrors; account_id mirrors).
- [x] B.3.3 Equivalence tests in `tests/test_demo_data.py`:
  - For each `ar_transfers` row, exactly one `transfer` row with matching fields.
  - For each `ar_transactions` row, exactly one `posting` with matching account, amount, status.
  - `Σ posting.signed_amount` per transfer_id = 0 (or matches the legacy "transfer is non-zero" exception case).
- [x] B.3.4 `pytest` clean — both old and new tables populated.
- [x] B.3.5 Commit — `Phase B.3: AR demo writes to unified transfer + posting (dual-write)`.

---

## Phase B.4 — AR datasets read from unified schema; legacy AR tables dropped

Cutover: AR datasets stop reading legacy tables; legacy AR tables removed from `demo/schema.sql`.

- [x] B.4.1 Rewrite each AR dataset's SQL in `account_recon/datasets.py` to project from `transfer` + `posting` instead of `ar_transfers` + `ar_transactions`. Column contracts (B.2) stay identical — only the implementation changes.
- [x] B.4.2 Drop `ar_transactions` from `demo/schema.sql`. Rewrite AR views (`ar_transfer_summary`, `ar_subledger_daily_outbound_by_type`, `ar_computed_subledger_daily_balance`, `ar_transfer_net_zero`) to use `posting` + `transfer`. Remove `ar_transactions` INSERT from demo_data.py.
- [x] B.4.3 Update `tests/test_account_recon.py` — all scenario/row-count/FK/schema tests now read from `unified_parsed["posting"]` + `unified_parsed["transfer"]` instead of `ar_parsed["ar_transactions"]`.
- [x] B.4.4 `demo apply --all` + `deploy --all --generate -c run/config.yaml -o run/out/` from repo root.
- [x] B.4.5 `./run_e2e.sh --parallel 4` — full suite. AR e2e green; PR e2e unaffected (still on legacy tables).
- [x] B.4.6 Commit — `Phase B.4: AR datasets read from unified schema; legacy AR txn tables dropped`.

CHECKPOINT — AR fully on unified schema. PR untouched.

---

## Phase B.5 — PR demo writes transfer chains (dual-write)

PR generator emits the chain `external_txn → payment → settlement → sale` as a tree of `transfer` rows linked by `parent_transfer_id`, with two postings per transfer. Legacy PR tables still populated for safety.

- [x] B.5.1 Added PR ledger account (`pr-merchant-ledger`) + 8 sub-ledger accounts (one per merchant + `pr-external-customer-pool` + `pr-external-rail`) into `ar_ledger_accounts` / `ar_subledger_accounts`.
- [x] B.5.2 External txn → top-level transfer (no parent, type='external_txn', origin='external_force_posted') + 1 posting on `pr-external-rail`.
- [x] B.5.3 Payment → transfer with parent=ext_txn (or NULL if unmatched), type='payment' + 2 postings (external-rail, merchant sub-ledger). Returned payments → posting status='failed'.
- [x] B.5.4 Settlement → transfer with parent=payment (or NULL if unpaid), type='settlement' + 2 postings on merchant sub-ledger (both sides, nets to zero). Failed settlements → posting status='failed'.
- [x] B.5.5 Sale → transfer with parent=settlement (or NULL if unsettled), type='sale' + 2 postings (merchant sub-ledger + external-customer-pool).
- [x] B.5.6 Status mapping documented in `_derive_pr_unified_tables` docstring: sale→posted, settlement→posted/pending/failed, payment→posted/returned, external→posted.
- [x] B.5.7 12 equivalence tests in `TestPrUnifiedTables`: transfer-per-legacy-row count, chain integrity (payment→ext, settlement→payment, sale→settlement), posting FK integrity, net-zero per non-failed transfer, posting counts (1 for ext_txn, 2 for others), unsettled-sale parent=NULL.
- [x] B.5.8 296 tests pass.
- [x] B.5.9 Commit.

---

## Phase B.6 — PR datasets read from unified schema; legacy PR tables dropped

**Status: DEFERRED.** PR datasets need domain-specific metadata (`card_brand`, `cashier`, `merchant_name`, `settlement_type`, `payment_method`, optional sale columns) that lives on legacy `pr_*` tables. Unlike AR (where the domain model maps 1:1 onto transfer/posting), PR's metadata is too rich to represent on the generic unified schema without making it bloated and domain-specific.

**What completed in B.5 instead:** PR demo data emits transfer + posting rows (dual-write). The chain model is proven, FK integrity tested, postings net to zero. PR datasets continue reading from legacy tables for now.

**Path forward:** when the customer decides what PR columns they actually need, extract only those into metadata tables and rewrite PR datasets to join transfer/posting with metadata. Until then, legacy tables serve as both the transaction log and the metadata store for PR.

- [x] B.6.1 *Assessed*: PR pipeline datasets (merchants, sales, settlements, payments) require `pr_*` table metadata. Exception/recon views could theoretically migrate but still need `merchant_id` which is on legacy tables.
- [x] B.6.2 *Assessed*: PR views (`pr_sale_settlement_mismatch`, etc.) use `merchant_id`, `settlement_id`, `payment_id` — foreign keys back to legacy tables. Rewriting these to use transfer chains would require mapping merchant_id through subledger accounts, adding complexity without value until legacy tables are actually dropped.
- [~] B.6.3 Legacy `pr_*` tables **kept** — still needed for PR dataset metadata. Transfer + posting tables carry the reconciliation model.
- [x] B.6.4 No test changes needed — PR datasets unchanged.
- [x] B.6.5 `demo apply --all` checkpoint (covered by B.9).
- [x] B.6.6 No commit — skipped.

CHECKPOINT — AR fully on unified schema. PR emits to unified schema (dual-write) but datasets still read from legacy tables.

---

## Phase B.7 — Cross-app sanity sweep

The unified schema makes cross-app invariants checkable for the first time. Add a few fast guards.

- [x] B.7.1 Removed last `ar_transactions` references from `account_recon/filters.py` (comment) and `tests/e2e/test_ar_filters.py` (docstring). PR legacy table references intentionally kept (B.6 deferred).
- [x] B.7.2 Cross-app integrity tests: posting FK to transfer, posting FK to subledger, no ID collisions across apps.
- [x] B.7.3 Transfer type enum coverage test: all 8 declared CHECK values present in combined PR+AR data.
- [x] B.7.4 Commit.

---

## Phase B.8 — Docs sweep

Last because earlier phases churn the things docs reference.

- [x] B.8.1 `CLAUDE.md` — Domain Model rewritten: added "Unified Schema" section describing shared `transfer` + `posting` tables; AR section updated (postings, not transaction legs); PR section updated (transfer chain, sub-ledger accounts).
- [x] B.8.2 `CLAUDE.md` — added `dataset_contract.py` to project structure and DatasetContract convention bullet.
- [x] B.8.3 `README.md` — AR description updated ("postings" not "transactions").
- [~] B.8.4 `SPEC.md` — left as-is; spec uses business-domain language ("transactions") which is correct at the requirements level.
- [x] B.8.5 `RELEASE_NOTES.md` — v1.3.0 entry written.
- [x] B.8.6 grep sweep: cleaned `ar_transactions` from `filters.py` (B.7), `test_ar_filters.py` (B.7). Remaining `ar_transactions` in schema.sql is the DROP + migration comment (correct).
- [x] B.8.7 Commit.

---

## Phase B.9 — Deploy + e2e + release

- [x] B.9.1 `demo apply --all` — schema applied, seed data inserted (both apps).
- [x] B.9.2 `deploy --all --generate` — all resources CREATION_SUCCESSFUL.
- [x] B.9.3 `cleanup --dry-run` — no stale resources.
- [x] B.9.4 `./run_e2e.sh --parallel 4` — 94 passed, 6 skipped, 1 xfailed. Full green.
- [x] B.9.5 Fixed schema DDL ordering (transfer/posting tables before AR views). Tag + merge.

---

## Decisions to make in flight

- **Dataset rename license**: Phase A used "rename freely" license for dataset IDs. Phase B may want similar for any dataset whose unified-schema implementation makes a different name natural (e.g., `qs-gen-pr-payments-dataset` might become `qs-gen-pr-payment-transfers-dataset`). Cleanup-by-tag handles deploy hygiene.
- **`parent_transfer_id` of unmatched PR rows**: NULL or self-ref? Recommend NULL — "no parent" is the honest signal. Unmatched-external-txn check looks for top-level transfers with `transfer_type='payment' AND parent_transfer_id IS NULL`.
- **Legacy `pr_merchants` table**: PR datasets need merchant metadata (name, type, location). Recommend keeping `pr_merchants` (and `pr_locations`) as-is — they're reference tables, not transactional, and joining on them from the unified schema is straightforward. Dropping them just to be uniform adds work without value.
- **Refunds in PR**: today these are negative-amount sale rows with `sale_type=refund`. Under transfer chains, a refund is either a separate transfer with reversed postings (more correct) or kept as a negative-amount sale transfer (mechanical port). Recommend the negative-amount port for B.5 (preserves test parity); promote to "refund as inverse transfer" in Phase D when the reconciliation frame can express it cleanly.
- **AR transfer_type for PR-chain postings**: A sale's debit-side posting hits `pr_external_customer_pool` (a sub-ledger). Does that show up in AR exception checks (overdraft, drift)? Audit during B.5 — likely needs an `is_internal` flag on accounts or a sub-ledger exclusion list to keep AR exception scope clean.

---

## Risks

- **PR exception logic regression**: PR's 5 exception checks are computed off legacy table joins today. After B.6 they're computed off transfer-chain aggregations. Easy to introduce silent off-by-one when summing chain children. Equivalence tests in B.5.7 are the safety net — keep them sharp.
- **Demo determinism drift**: B.3 and B.5 add new INSERTs interleaved with existing ones. ID generation order matters for `random.Random(42)` byte-identical output. If preserving byte-equivalence on the legacy tables is hard, document the new baseline rather than fight the generator.
- **Test rewrite scope**: 254 unit/integration tests; many assert on specific SQL substrings. Phase B will invalidate most of those. Plan for focused rewrite per test file, not copy-paste-and-tweak.
- **`pr_external_customer_pool` leakage**: this synthetic account is a Phase B convenience. If it shows up in user-facing AR visuals (sub-ledger lists, drift charts), filter it out at the dataset level. Audit during B.5/B.6.
- **Dataset count growth**: the column contract refactor in B.2 might tempt extracting a `contracts/` module. Resist — keep contract + SQL in the same `<app>/datasets.py` file. One file per app is the right granularity.
- **External stakeholder mental model**: anyone reviewing demo screenshots from before will see different tab counts/labels if the dataset rename license gets used aggressively. Flag in v1.3.0 release notes.

---
---

# PLAN — Phase C: Ledger-level direct postings

Goal: Drop the "ledger balance = Σ sub-ledger balances" invariant. Replace with the general GL invariant: `stored ledger balance = Σ direct postings to the ledger + Σ sub-ledger stored balances, all evaluated as-of the reporting date`. Every ledger can receive direct postings — no per-ledger "direct-post allowed?" configuration.

This makes the system faithful to real GL behavior: inbound funding batches, clearing-account sweeps, fee assessments, and external-rail debits that hit the ledger before sub-ledger breakdown is known all post at the ledger level.

Out of scope for Phase C:
- Reconciliation DSL or unified Exceptions tab (Phase D).
- Wiring `origin` into filters / visuals / checks (Phase D).
- PR dataset cutover to unified schema (deferred from B.6, tracked in SPEC.md).
- Persona dashboard split (Phase E).

Conventions:
- Branch: `phase-c-ledger-postings`, cut from `main`. One sub-phase = one commit.
- After each sub-phase, run `.venv/bin/pytest`. After C.5 and C.8, run `./run_e2e.sh --parallel 4`.
- Demo data stays deterministic (`random.Random(42)`).

---

## Phase C.0 — Pin decisions

STOP here. Get alignment before writing code.

- [x] C.0.1 **Posting target: add `ledger_account_id` to `posting`, or create a unified account table?** → **Add `ledger_account_id NOT NULL` to `posting`.** Every posting always knows its ledger — for sub-ledger postings it's derived from `ar_subledger_accounts.ledger_account_id`; for ledger-level postings it's the direct target. `subledger_account_id` becomes nullable (NULL for ledger-level postings). Future consideration: unified account table ("here are ALL the accounts") tracked for a later phase.
- [x] C.0.2 **Ledger-level postings: do they belong to transfers?** → **Yes.** Every posting is part of a transfer; ledger-level included. Net-zero invariant still applies.
- [x] C.0.3 **Does ledger drift change from 2-input to 3-input?** → **Yes.** `stored_ledger_balance vs (Σ direct ledger postings + Σ sub-ledger stored_balances)`. Phase E should improve how this is surfaced visually (e.g., decomposing drift into direct-posting vs sub-ledger components).
- [x] C.0.4 **Sub-ledger drift: unchanged?** → **Yes.** Sub-ledger drift stays `stored sub-ledger balance vs Σ postings to that sub-ledger`. Ledger-level postings don't affect it.
- [x] C.0.5 **Demo scenario types for ledger postings?** → **3 scenarios:** (a) funding batch, (b) fee assessment (single-leg, intentional imbalance — test data), (c) clearing sweep. Track all demo scenarios in SPEC.md for future training documentation (post-Phase D).
- [x] C.0.6 **New dataset or extend existing?** → **Extend** `ar_transactions` dataset to include ledger-level postings. One table, all postings.
- [x] C.0.7 **Visual changes: new visuals or extend existing?** → **Extend existing.** Balances tab gets a "Direct Posting Total" column on Ledger Balances, factored into drift. Drift decomposition (direct-posting component vs sub-ledger component) is desirable but may require a later phase — assess during C.5 and defer if complex.

---

## Phase C.1 — Schema changes (additive)

Add `ledger_account_id` to `posting` table. Nothing reads it yet.

- [x] C.1.1 Add `ledger_account_id VARCHAR(100) NOT NULL REFERENCES ar_ledger_accounts(ledger_account_id)` to `posting` table in `demo/schema.sql`. Every posting knows its ledger.
- [x] C.1.2 Make `subledger_account_id` nullable (remove `NOT NULL`). Ledger-level postings have `subledger_account_id = NULL`. Sub-ledger postings keep it populated.
- [x] C.1.3 Add index: `posting(ledger_account_id, posted_at)`.
- [x] C.1.4 Update all demo data generators (AR + PR) to populate `ledger_account_id` on every posting — derived from the sub-ledger's FK for sub-ledger postings, set directly for ledger-level postings.
- [x] C.1.5 `pytest` clean — schema structure tests updated, posting column index mappings updated in test fixtures.
- [x] C.1.6 Commit — `Phase C.1: add ledger_account_id to posting, make subledger_account_id nullable`.

---

## Phase C.2 — AR demo data: ledger-level postings

Expand the AR demo generator to emit transfers with ledger-level postings. Existing sub-ledger transfers unchanged.

- [x] C.2.1 Define 3 scenario types in `account_recon/demo_data.py`:
  - **Funding batch**: transfer with 1 ledger-level credit posting + N sub-ledger debit postings. Represents inbound money arriving at the ledger before being distributed.
  - **Fee assessment**: transfer with 1 ledger-level debit posting only. Intentionally single-leg — creates a non-zero transfer (already caught by existing exception check) and contributes to ledger drift.
  - **Clearing sweep**: transfer with 2 ledger-level postings (debit + credit) that net to zero within the same ledger. Represents end-of-day clearing.
- [x] C.2.2 Generate ~5 funding batches, ~3 fee assessments, ~2 clearing sweeps across the demo period. Distribute across ledger accounts.
- [x] C.2.3 Ledger-level postings: `ledger_account_id` set directly, `subledger_account_id = NULL`.
- [x] C.2.4 Update `ar_ledger_daily_balances` seed data to reflect the new direct postings — stored balances must account for both sub-ledger activity AND direct ledger postings for the demo to be consistent.
- [x] C.2.5 `pytest` clean — new scenario coverage tests.
- [x] C.2.6 Commit — `Phase C.2: AR demo emits ledger-level postings`.

---

## Phase C.3 — Scenario coverage tests

Add demo-data tests asserting ledger-level posting scenarios exist and are well-formed.

- [x] C.3.1 `TestLedgerPostingScenarios` in `tests/test_demo_data.py`:
  - At least 5 funding-batch transfers exist (multi-leg, ledger credit + sub-ledger debits).
  - At least 3 fee-assessment transfers exist (single ledger-level debit).
  - At least 2 clearing-sweep transfers exist (2 ledger-level legs, nets to zero).
- [x] C.3.2 Ledger-level postings have `ledger_account_id` set and `subledger_account_id = NULL`.
- [x] C.3.3 Funding-batch transfers: net-zero across all legs (ledger credit = Σ sub-ledger debits).
- [x] C.3.4 Fee-assessment transfers: non-zero net (intentional — caught by non-zero transfer check).
- [x] C.3.5 All ledger-level postings FK to valid `ar_ledger_accounts`.
- [x] C.3.6 `pytest` clean.
- [x] C.3.7 Commit — `Phase C.3: ledger-level posting scenario coverage tests`.

---

## Phase C.4 — View + dataset changes

Update AR views and datasets to incorporate ledger-level postings into the drift computation and surface them in the Transactions tab.

- [x] C.4.1 Rewrite `ar_computed_ledger_daily_balance` view:
  - Old: `Σ sub-ledger stored balances per ledger per day`.
  - New: `Σ sub-ledger stored balances + Σ direct ledger postings (non-failed, grouped by posted_at::date)`.
- [x] C.4.2 `ar_ledger_balance_drift` view: no structural change (still `stored - computed`), but computed now includes direct postings. Drift will surface ledger-level discrepancies.
- [x] C.4.3 Update `ar_transactions` dataset SQL to include ledger-level postings:
  - LEFT JOIN `ar_subledger_accounts` (nullable for ledger-level postings).
  - JOIN `ar_ledger_accounts` on `posting.ledger_account_id` (always set).
  - Add `COALESCE(s.name, la.name)` for display name.
  - Add a `posting_level` computed column: `'Ledger'` if `subledger_account_id IS NULL`, else `'Sub-Ledger'`.
- [x] C.4.4 Update `ar_transactions` `DatasetContract` with the new `posting_level` column.
- [x] C.4.5 `ar_transfer_net_zero` view: updated to LEFT JOIN `ar_subledger_accounts` (handle NULL subledger for ledger-level postings).
- [x] C.4.6 `pytest` clean — dataset contract tests updated.
- [x] C.4.7 Commit — `Phase C.4: views + datasets incorporate ledger-level postings`.

---

## Phase C.5 — Visual + filter changes

Surface ledger-level postings in the dashboard. Minimal visual additions.

- [x] C.5.1 Transactions tab: add `posting_level` column to Transaction Detail table. Enables filtering by "Ledger" vs "Sub-Ledger" level postings.
- [x] C.5.2 Added `posting_level` multi-select filter control on the Transactions tab.
- [~] C.5.3 Balances tab: deferred "Direct Posting Total" column — adds complexity without clear signal for end users.
- [x] C.5.4 Getting Started sheet: updated AR Transactions description and bullets to mention ledger-level postings and Posting Level filter.
- [x] C.5.5 Ledger Drift Timeline on Exceptions: drift values now reflect direct postings (via view change in C.4). No subtitle update needed.
- [x] C.5.6 `pytest` clean — visual/filter structure tests updated.
- [x] C.5.7 Commit — `Phase C.5: surface ledger-level postings in AR visuals`.

---

## Phase C.6 — PR impact assessment

PR sub-ledger accounts (`pr-sub-{merchant}`, `pr-external-customer-pool`, `pr-external-rail`) live under `pr-merchant-ledger`. Ensure ledger-level posting changes don't leak into PR or AR exception scope incorrectly.

- [x] C.6.1 Verified AR dataset type filter expanded to `IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')` — excludes all PR types (`sale`, `settlement`, `payment`, `external_txn`). Zero overlap.
- [x] C.6.2 Verified `pr-merchant-ledger` does not appear in `ar_ledger_daily_balances` — no stored balance feed for PR ledger.
- [x] C.6.3 Not needed — no leakage found.
- [x] C.6.4 No PR dataset or visual changes needed.
- [~] C.6.5 No commit — no changes needed (assessment only).

---

## Phase C.7 — Docs sweep

- [x] C.7.1 `CLAUDE.md` — updated Unified Schema: posting column descriptions, fee as single-leg exception.
- [x] C.7.2 `CLAUDE.md` — updated AR section: ledger-level postings, drift invariants, expanded type filter.
- [x] C.7.3 `README.md` — already updated in Phase A.7 (ledger/subledger vocabulary); no further changes needed.
- [x] C.7.4 `SPEC.md` — updated AR domain model: Postings section (ledger/sub-ledger targeting), drift invariant (3-input), ledger drift check description.
- [ ] C.7.5 Commit — `Phase C.7: docs sweep for ledger-level postings`.

---

## Phase C.8 — Deploy + e2e + release

- [x] C.8.1 `demo apply --all` — schema + seed applied.
- [x] C.8.2 `deploy --all --generate` — all resources CREATION_SUCCESSFUL.
- [x] C.8.3 `cleanup --dry-run` — no stale resources.
- [x] C.8.4 `./run_e2e.sh --parallel 4` — 94 passed, 6 skipped, 1 xfailed.
- [x] C.8.5 `RELEASE_NOTES.md` — v1.4.0 entry.
- [x] C.8.6 Tag v1.4.0, push.

---

## Decisions to make in flight

- ~~**Populate `ledger_account_id` on sub-ledger postings?**~~ → **Resolved in C.0.1**: `ledger_account_id NOT NULL` on every posting. Always populated.
- ~~**Fee assessments: truly single-leg?**~~ → **Resolved in C.0.5**: yes, single-leg. Test data to exercise exceptions; not modeling real-world fee accounting.
- ~~**New transfer types for ledger-level activity?**~~ → **Resolved in C.1**: Added `funding_batch`, `fee`, `clearing_sweep` to CHECK constraint. AR type filter expanded to include them.
- **Unified account table (future)?** User preference for a single "here are ALL the accounts" table. Out of scope for Phase C (additive column is sufficient), but tracked for a later phase. Would merge `ar_ledger_accounts` and `ar_subledger_accounts` into one table with a `level` or `parent_account_id` discriminator.
- **Drift decomposition visual (future)?** Showing direct-posting drift vs sub-ledger drift as separate components on the Exceptions tab. Assess feasibility in C.5; if complex, defer to Phase E.

---

## Risks

- **Drift computation correctness**: The 3-input drift formula (`stored - (direct postings + sub-ledger sum)`) is more complex than the current 2-input formula. Off-by-one in date grouping or double-counting is the main risk. Mitigate with explicit scenario tests that compute expected drift values.
- **Generator backfill scope for `ledger_account_id`**: Both AR and PR demo data generators must populate `ledger_account_id` on every posting (C.1.4). AR postings derive it from the sub-ledger's FK; PR postings derive it from `pr-merchant-ledger`. Must happen in C.1 before any view depends on the column.
- **AR/PR scope leakage**: PR's `pr-merchant-ledger` is a real ledger account. If it appears in `ar_ledger_daily_balances`, the AR drift views would try to compute drift for it. Ensure the demo data generator does NOT emit stored ledger balances for `pr-merchant-ledger`.
- **Demo determinism**: Adding ~10 new transfers with ledger-level postings changes the `random.Random(42)` sequence. If ledger-level transfer generation happens before existing transfers in the generator, it shifts all downstream IDs. Insert at the end of the generation sequence to minimize churn.

---
---

# PLAN — Phase D: Aging, origin wiring, and reconciliation pattern

Goal: Add time-based urgency (aging buckets) to every exception check across both apps. Wire the `origin` attribute (deferred since Phase A) into AR filters and exception awareness. Standardize the visual pattern so every check has KPI + detail table + aging breakdown. Let a `ReconciliationCheck` code abstraction emerge from the work — don't pre-design it.

This phase touches both apps' exception surfaces but does NOT merge the PR Payment Reconciliation tab into the AR Exceptions tab — that's a persona decision for Phase E, informed by the training stories the user is writing in parallel.

Out of scope for Phase D:
- PR dataset cutover to unified schema (still deferred from B.6, tracked in SPEC.md).
- Persona dashboard split (Phase E). Both apps keep their current tab structure.
- Merging PR Payment Recon mutual-filter tables into AR Exceptions. The mutual-filter UX stays; aging is added to it.
- Training story integration (user working in parallel in `docs/`).
- As-of date UI control. Schema timestamps support it; queries still use CURRENT_DATE.

Conventions:
- Branch: `phase-d-aging-origin`, cut from `main`. One sub-phase = one commit; cumulative release at the end.
- `demo apply` continues to drop-and-create. No staged migrations.
- `cleanup --yes` after deploy handles stale tagged resources.
- After each sub-phase, run `.venv/bin/pytest`. After D.5 and D.9, run `./run_e2e.sh --parallel 4`.
- Demo data MUST stay deterministic (`random.Random(42)`); tests depend on byte-identical output where unchanged.
- Every sheet description and every visual subtitle stays present.

---

## Current exception check inventory

**Before** writing code, catalog what exists. Each check has a dataset, a KPI visual, and a detail table. Some also have timelines or drill-down actions.

### AR Exceptions (5 checks, all on Exceptions tab)
| Check | Dataset | Has KPI | Has Table | Has Timeline | Has Aging | Has Drill |
|-------|---------|---------|-----------|-------------|-----------|-----------|
| Ledger drift | `ar-ledger-balance-drift` | Yes | Yes | Yes | No | Yes → Balances |
| Sub-ledger drift | `ar-subledger-balance-drift` | Yes | Yes | Yes | No | Yes → Transactions |
| Non-zero transfers | `ar-non-zero-transfers` | Yes | Yes | No | No | Yes → Transactions |
| Limit breach | `ar-limit-breach` | Yes | Yes | No | No | Yes → Transactions (multi-param) |
| Overdraft | `ar-overdraft` | Yes | Yes | No | No | Yes → Transactions (multi-param) |

### PR Exceptions (5 checks, all on Exceptions & Alerts tab)
| Check | Dataset | Has KPI | Has Table | Has Timeline | Has Aging | Has Drill |
|-------|---------|---------|-----------|-------------|-----------|-----------|
| Unsettled sales | `settlement-exceptions` | Yes | Yes | No | `days_outstanding` | No |
| Returned payments | `payment-returns` | Yes | Yes | No | `days_outstanding` | No |
| Sale↔settlement mismatch | `sale-settlement-mismatch` | Yes | Yes | No | `days_outstanding` | No |
| Settlement↔payment mismatch | `settlement-payment-mismatch` | Yes | Yes | No | `days_outstanding` | No |
| Unmatched external txns | `unmatched-external-txns` | Yes | Yes | No | `days_outstanding` | No |

### PR Payment Recon (1 special case, own tab)
| Check | Dataset | Has KPI | Has Mutual Filter | Has Aging | Has Late Logic |
|-------|---------|---------|-------------------|-----------|----------------|
| External↔payment match | `payment-recon` | Yes (late count) | Yes (both tables + bar) | `days_outstanding` | `late_default_days` threshold |

---

## Phase D.0 — Pin decisions

STOP here. Get alignment before writing code.

- [x] D.0.1 **Aging bucket boundaries?** → **5 hardcoded buckets:** `0–1 day`, `2–3 days`, `4–7 days`, `8–30 days`, `>30 days`. Configurable boundaries deferred — marginal value for the complexity.
- [x] D.0.2 **Aging bucket visual: bar chart, or column in existing tables, or both?** → **Both.** `aging_bucket` column in each exception dataset (sortable/filterable in detail tables) AND a horizontal bar chart showing count-by-bucket per check.
- [x] D.0.3 **Origin wiring scope?** → **(a) + (b):** Origin multi-select filter on Transactions + Exceptions tabs, plus `origin` column on non-zero-transfer and limit-breach detail tables. Option (c) — origin-aware exception awareness (Show-Only toggle, conditional formatting) — deferred to Phase E as a training story. The origin concept will be a key teaching point; don't lose the thread.
- [x] D.0.4 **ReconciliationCheck abstraction: when to extract?** → **Continuous assessment, not a checkpoint gate.** Think about the pattern after each sub-phase; extract whenever it's obviously right, not at a predetermined stop. D.5 becomes "extract if ready" rather than "stop and decide."
- [x] D.0.5 **PR Payment Recon: add aging bar chart?** → **Yes.** Aging bar stacked by match_status on the Payment Recon tab. Mutual-filter tables unchanged.
- [x] D.0.6 **PR exception drill-downs?** → **Yes, if reasonable effort.** Phase E persona work will rework the layout, so keep the drill-down implementation straightforward — don't over-invest in the current tab structure. If any single drill is disproportionately complex (e.g., requires new parameters cascading across 3+ sheets), skip it and note for E.
- [x] D.0.7 **Do AR exception datasets need `origin`? + Intake feed shape question.** → **Yes, add `origin` to non-zero-transfer and limit-breach datasets.** Skip for drift/overdraft (no meaningful origin on a balance snapshot).

  **On the intake feed question:** This is the right question at the right time. Today we have two layers of contract:
  - **Dataset column contract** (Phase B) — what the *reporting layer* expects. Defined in `DatasetContract` per dataset. The customer swaps SQL; the column list stays fixed.
  - **Schema contract** (implicit) — what the *database tables* must contain for the demo SQL to work. Currently implicit in `demo/schema.sql`.

  What's missing is a **third layer: the intake contract** — what an upstream system's feed must provide for the reporting layer to produce meaningful results. For `origin` specifically: the upstream system needs to tag each transfer as `internal_initiated` or `external_force_posted`. If it doesn't, the column defaults to `internal_initiated` and the origin filter/visuals are useless.

  **Recommendation for Phase D:** Don't build the intake contract framework now — that's Phase E/post-E work (it feeds directly into the training stories and the customer onboarding guide). Instead:
  - Add `origin` to the datasets that can carry it (D.1).
  - Document in each dataset's contract notes which columns are *feed-dependent* vs *computed*. This is a lightweight annotation, not a new abstraction.
  - Track "define intake contract per feed" as deferred work in SPEC.md alongside the training story catalog.
  
  The training stories the user is writing in `docs/` will naturally define what the intake feeds look like by example — "Farmers Exchange Bank receives an ACH wire from First National, tagged as `external_force_posted`..." That narrative IS the intake contract, told as a story rather than a schema spec.

---

## Phase D.1 — Origin filter wiring (AR)

Wire the `origin` attribute into AR filters and exception detail. Deferred since Phase A — the column exists on `ar-transactions` but has no filter.

- [ ] D.1.1 Add `_origin_filter_group()` in `account_recon/filters.py`: multi-select CategoryFilter on `DS_AR_TRANSACTIONS`, column `origin`, scoped to Transactions + Exceptions tabs (cross-dataset).
- [ ] D.1.2 Add origin filter control to `build_transactions_controls()` and `build_exceptions_controls()`.
- [ ] D.1.3 Add `origin` column to non-zero-transfer dataset contract + SQL (join through `transfer.origin`). Add to detail table visual.
- [ ] D.1.4 Add `origin` column to limit-breach dataset contract + SQL (join through `transfer.origin` via posting). Add to detail table visual.
- [ ] D.1.5 Update filter group ID expected sets in unit + e2e tests.
- [ ] D.1.6 `pytest` clean.
- [ ] D.1.7 Commit — `Phase D.1: wire origin into AR filters and exception detail`.

---

## Phase D.2 — AR exception aging (5 checks)

Add `days_outstanding` and `aging_bucket` computed columns to all 5 AR exception datasets. Add aging bar chart visuals to the Exceptions tab.

- [ ] D.2.1 Add `days_outstanding` and `aging_bucket` columns to `LEDGER_BALANCE_DRIFT_CONTRACT` and dataset SQL: `(CURRENT_DATE - balance_date::date) AS days_outstanding`, plus CASE expression for aging bucket.
- [ ] D.2.2 Same for `SUBLEDGER_BALANCE_DRIFT_CONTRACT`.
- [ ] D.2.3 Same for `NON_ZERO_TRANSFERS_CONTRACT` (using `first_posted_at`).
- [ ] D.2.4 Same for `LIMIT_BREACH_CONTRACT` (using `activity_date`).
- [ ] D.2.5 Same for `OVERDRAFT_CONTRACT` (using `balance_date`).
- [ ] D.2.6 Add aging bar chart visual for each check section on the Exceptions tab. Pattern: horizontal bar chart, category = `aging_bucket`, value = COUNT(*), sorted by bucket order. Subtitle explains the bucket boundaries.
- [ ] D.2.7 Add `aging_bucket` column to each detail table visual (sortable, after the date column).
- [ ] D.2.8 Update dataset contract tests.
- [ ] D.2.9 `pytest` clean.
- [ ] D.2.10 Commit — `Phase D.2: aging buckets on AR exception checks`.

---

## Phase D.3 — PR exception aging (5 checks)

PR exceptions already have `days_outstanding`. Add `aging_bucket` computed column and aging bar chart visuals to the Exceptions & Alerts tab.

- [ ] D.3.1 Add `aging_bucket` CASE column to all 5 PR exception dataset SQLs (using existing `days_outstanding` or computing from the relevant date column).
- [ ] D.3.2 Update all 5 PR exception `DatasetContract`s with `aging_bucket` column.
- [ ] D.3.3 Add aging bar chart visual for each check section on the PR Exceptions & Alerts tab. Same pattern as AR (D.2.6).
- [ ] D.3.4 Add `aging_bucket` column to each PR exception detail table visual.
- [ ] D.3.5 Update dataset contract tests.
- [ ] D.3.6 `pytest` clean.
- [ ] D.3.7 Commit — `Phase D.3: aging buckets on PR exception checks`.

---

## Phase D.4 — PR Payment Recon aging

Add aging bucket breakdown to the Payment Reconciliation tab without disrupting the mutual-filter tables.

- [ ] D.4.1 Add `aging_bucket` CASE column to `PAYMENT_RECON_CONTRACT` and SQL (using `days_outstanding`).
- [ ] D.4.2 Add aging bar chart on the Payment Recon tab: horizontal bar, category = `aging_bucket`, stacked by `match_status`. Shows at a glance where unmatched external transactions are aging.
- [ ] D.4.3 Existing `recon-bar-by-system` (match status by external system) and mutual-filter tables unchanged.
- [ ] D.4.4 Update dataset contract tests.
- [ ] D.4.5 `pytest` clean.
- [ ] D.4.6 Commit — `Phase D.4: aging bar chart on PR Payment Recon tab`.

---

## Phase D.5 — ReconciliationCheck pattern extraction (if ready)

Continuous assessment throughout D.1–D.4. By this point, the pattern should either be obvious or clearly not worth extracting. This sub-phase is "extract if ready" — not a gate.

- [ ] D.5.1 Review the shape of each check after D.2–D.4: dataset SQL pattern, contract columns, visual set (KPI + aging bar + detail table + optional timeline), drill-down action pattern.
- [ ] D.5.2 Expected groupings (may have shifted during implementation):
  - **"Left ≠ right on a key, with a date"**: drift, non-zero, mismatch.
  - **"Row matches condition on a key, with a date"**: overdraft, returned payment, limit breach, unsettled sale.
  - **"Left not paired with right"**: unmatched external txn, payment recon late.
- [ ] D.5.3 If the pattern is clean: extract a `ReconciliationCheck` helper in `common/` that generates the standard visual set (KPI + aging bar + detail table) from a minimal spec. Refactor AR checks onto it. PR checks stay as-is (legacy tables; refactoring is Phase E).
- [ ] D.5.4 If the pattern is forced or doesn't cover all shapes: skip extraction, note what didn't fit, move on. The per-check implementations from D.2–D.4 are already consistent — that's sufficient.
- [ ] D.5.5 `pytest` clean — no behavior change from refactor.
- [ ] D.5.6 Commit — `Phase D.5: ReconciliationCheck pattern extraction` (or `Phase D.5: assessed, no extraction warranted`).

---

## Phase D.6 — Visual consistency pass

Ensure every exception check across both apps follows the same visual pattern: KPI → aging bar → detail table (→ optional timeline, → optional drill).

- [ ] D.6.1 Audit each check's visual set against the target pattern. Fill gaps:
  - PR exceptions: add KPIs for the 3 mismatch/unmatched checks if missing (currently only unsettled + returns have KPIs).
  - AR exceptions: non-zero, limit breach, and overdraft don't have timelines. Assess whether adding timelines (date-aggregated bar chart, same as drift timelines) adds signal. If yes, add; if noise, skip.
- [ ] D.6.2 Standardize subtitles across all exception visuals — each should explain what the check detects and what action the user should take.
- [ ] D.6.3 Update Getting Started sheet descriptions for both apps to mention aging.
- [ ] D.6.4 `pytest` clean.
- [ ] D.6.5 Commit — `Phase D.6: visual consistency pass across exception checks`.

---

## Phase D.7 — PR exception drill-downs (if D.0.6 approved)

Add click-to-drill actions on PR exception detail tables, matching the AR pattern.

- [ ] D.7.1 Unsettled sale table: click `sale_id` → Sales tab, filtered to that sale (or merchant).
- [ ] D.7.2 Returned payment table: click `payment_id` → Payments tab, filtered.
- [ ] D.7.3 Sale↔settlement mismatch: click `settlement_id` → Settlements tab, filtered.
- [ ] D.7.4 Settlement↔payment mismatch: click `payment_id` → Payments tab, filtered.
- [ ] D.7.5 Unmatched external txn: click `transaction_id` → Payment Recon tab, sets `pExternalTransactionId`.
- [ ] D.7.6 Add drill parameter + filter group for each new action.
- [ ] D.7.7 Update clickability styling on drilled columns (accent text + tint background for right-click, accent text for left-click).
- [ ] D.7.8 `pytest` clean — visual action/parameter tests updated.
- [ ] D.7.9 Commit — `Phase D.7: PR exception drill-down actions`.

---

## Phase D.8 — Tests + docs sweep

- [ ] D.8.1 Aging bucket coverage tests in `test_demo_data.py`: assert each exception dataset produces rows in multiple aging buckets (not all in one bucket — demo data should span the demo period enough to cover the full range).
- [ ] D.8.2 Origin filter coverage: assert `origin` values (`internal_initiated`, `external_force_posted`) appear in the exception datasets that carry it.
- [ ] D.8.3 `CLAUDE.md` — update AR section: origin filter, aging buckets, exception visual pattern.
- [ ] D.8.4 `CLAUDE.md` — update PR section: aging buckets on exceptions, drill-down actions.
- [ ] D.8.5 `SPEC.md` — update reconciliation scope description: aging awareness, origin wiring.
- [ ] D.8.6 `RELEASE_NOTES.md` — v1.5.0 entry.
- [ ] D.8.7 `pytest` clean.
- [ ] D.8.8 Commit — `Phase D.8: tests + docs sweep`.

---

## Phase D.9 — Deploy + e2e + release

- [ ] D.9.1 `demo apply --all` — schema + seed applied.
- [ ] D.9.2 `deploy --all --generate` — all resources CREATION_SUCCESSFUL.
- [ ] D.9.3 `cleanup --dry-run` — no stale resources.
- [ ] D.9.4 `./run_e2e.sh --parallel 4` — full green.
- [ ] D.9.5 Tag v1.5.0, push.

---

## Decisions to make in flight

- **Aging bucket sort order in bar charts.** QuickSight sorts categories alphabetically by default. `0–1 day` sorts before `2–3 days` which sorts before `>30 days` — might need a sort-order column or explicit category ordering. Investigate during D.2.6.
- **Aging bucket on transfer-level vs posting-level dates.** Non-zero transfers age from `first_posted_at`; drift ages from `balance_date`; limit breach from `activity_date`. Each check uses its own natural date. Confirm during implementation that these dates produce meaningful aging for the demo data period (~40 days).
- **ReconciliationCheck: code-only or also visual?** The SPEC describes `(left, right, key, sla)`. That's a data pattern. Should the abstraction also generate the standard visual set (KPI + bar + table)? If yes, it's a bigger but more valuable abstraction. Assess in D.5.
- **PR mismatch KPIs.** Currently only unsettled sales and returned payments have KPIs on the PR Exceptions tab. The 3 mismatch/unmatched checks have tables but no KPIs. Adding KPIs is straightforward but adds visual density. Assess in D.6.

---

## Risks

- **Aging bucket column adds width to every exception table.** Tables are already wide; one more column per check. Mitigate by placing `aging_bucket` right after the date column and keeping the bucket labels short.
- **Demo data date range.** The demo spans ~40 days. If most exceptions land in the same aging bucket (because the data is generated uniformly across the period), the aging bar charts won't show a useful distribution. May need to weight demo exception generation toward recent dates to create a realistic aging curve. Assess during D.2 and adjust generator if needed.
- **Origin on exception datasets requires joining through transfer.** Non-zero transfers already join `ar_transfer_summary` (which has `transfer_type` but not `origin`). Adding `origin` may require joining the `transfer` table into the view or adding `origin` to the `ar_transfer_summary` view. Check view definitions during D.1.
- **ReconciliationCheck extraction may not be worth it.** The 11 checks have 3 different shapes (left≠right, row-matches-condition, unparied). If the abstraction doesn't cleanly express all three, it's worse than the per-check code. D.5 is explicitly assessment-first — skip extraction if the fit is poor.
- **PR drill-downs (D.7) add ~5 new parameters and filter groups to the PR analysis.** This is a meaningful structural change. If the user wants to keep PR stable for Phase E persona work, D.7 could be deferred. Ask in D.0.6.
