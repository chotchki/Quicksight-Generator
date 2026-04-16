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

- [ ] B.0.1 **Unified table names: `transfer` + `posting` (no prefix), or `qs_transfer` + `qs_posting`?** Recommend **no prefix** — these are the canonical names. App-specific prefixes (`pr_`, `ar_`) stay only on legacy tables until they're dropped.
- [ ] B.0.2 **PR sale postings need a counter-account. Introduce per-customer sub-ledgers, or use a single synthetic `pr_external_customer_pool` sub-ledger?** Per-customer modeling is out of Phase B scope. Recommend **single pool sub-ledger** — preserves the unified posting shape (must net to zero) without inventing customer modeling.
- [ ] B.0.3 **PR chain direction: external_txn is parent (payments are children) or external_txn is child (payments are parent)?** Recommend **external is parent** — matches the container narrative ("an external batch contains payments, which contain settlements, which contain sales"). The "match valid when totals equal" check becomes "Σ child amounts = parent amount" cleanly.
- [ ] B.0.4 **Old PR/AR detail tables: drop entirely after migration, or keep as views over the unified schema?** Recommend **drop entirely** in B.4 / B.6 once datasets migrate. Demo schema is internal; no callers outside this codebase. Per Phase A's no-shim philosophy.
- [ ] B.0.5 **Column contract shape: `DatasetContract` dataclass per dataset, or a registry pattern?** Recommend **dataclass per dataset** — simplest, matches existing per-builder module style. Lives next to the SQL implementation in `<app>/datasets.py`.
- [ ] B.0.6 **`as_of` granularity: timestamp on every row, or rely on existing `posted_at` / daily-balance dates?** Recommend **rely on existing** — postings carry `posted_at`, daily balances carry `as_of_date`. As-of query refactor is deferred to Phase D; schema stays as-is.
- [ ] B.0.7 **`posting.signed_amount` (single signed column) vs. `posting.amount` + `posting.direction`?** Recommend **signed_amount** — sum-to-zero is one `SUM(signed_amount) = 0`. If a visual wants directional readability, add a SQL view `posting_with_direction` later.
- [ ] B.0.8 **PR transfer_type values: keep separate (`sale`, `settlement`, `payment`, `external_txn`) or fold into AR's set (`ach`, `wire`, `internal`, `cash`)?** Recommend **separate enum** — they describe different things (PR's value names the chain link; AR's names the rail). `transfer_type` becomes a free string with a per-app vocabulary; CHECK constraint enumerates both sets.

---

## Phase B.1 — Unified schema definition (additive)

Add `transfer` and `posting` to `demo/schema.sql` alongside the legacy AR/PR tables. Nothing dropped yet.

- [ ] B.1.1 Add `transfer` table: `transfer_id PK`, `parent_transfer_id` (nullable FK self-ref), `transfer_type VARCHAR(30)`, `origin VARCHAR(30)` (`internal_initiated` / `external_force_posted`), `amount DECIMAL`, `status VARCHAR(20)`, `created_at TIMESTAMP`, `memo VARCHAR(255)`, `external_system VARCHAR(50)` (nullable).
- [ ] B.1.2 Add `posting` table: `posting_id PK`, `transfer_id FK → transfer`, `account_id FK → ar_subledger_accounts`, `signed_amount DECIMAL`, `posted_at TIMESTAMP`, `status VARCHAR(20)` (`success` / `failed`).
- [ ] B.1.3 Add indexes: `posting(transfer_id)`, `transfer(parent_transfer_id)`, `posting(account_id, posted_at)`.
- [ ] B.1.4 CHECK constraints: `transfer.transfer_type IN (...)` enumerating both AR and PR vocabularies; `transfer.origin IN ('internal_initiated', 'external_force_posted')`; `posting.status IN ('success', 'failed')`.
- [ ] B.1.5 No data inserted. `demo apply --all` should still succeed against existing legacy tables — empty `transfer` / `posting`.
- [ ] B.1.6 `pytest` — schema structure tests in `test_demo_sql.py` updated to assert presence of new tables.
- [ ] B.1.7 Commit — `Phase B.1: define unified transfer + posting schema (additive)`.

---

## Phase B.2 — Column contract abstraction

Add a `DatasetContract` dataclass and refactor existing dataset builders to consume it. Pure Python refactor — no SQL changes, no schema changes.

- [ ] B.2.1 Add `common/dataset_contract.py`: `ColumnSpec(name, type, nullable, notes)` and `DatasetContract(name, description, columns)`.
- [ ] B.2.2 Add a helper in `common/dataset_contract.py` (or extend `models.py`): `dataset_from_contract(contract, sql, datasource_arn, …) → Dataset`. Replaces the inline `Dataset(...)` construction in each builder.
- [ ] B.2.3 Refactor every existing dataset builder (11 PR + 9 AR) to declare a `DatasetContract` and call the helper. SQL stays byte-identical; column lists are now contract-derived.
- [ ] B.2.4 Add `tests/test_dataset_contract.py`: SELECT-clause parser asserts each builder's projected columns match its declared contract.
- [ ] B.2.5 `pytest` clean — no behavior change, only refactor.
- [ ] B.2.6 Commit — `Phase B.2: dataset column contract abstraction`.

---

## Phase B.3 — AR demo writes unified tables (dual-write)

AR generator emits to BOTH legacy AR tables AND the new `transfer` / `posting` tables, with equivalence asserted by tests. Nothing reads from the unified tables yet — this is the safety phase.

- [ ] B.3.1 `account_recon/demo_data.py`: every legacy `ar_transfers` row also produces a `transfer` row (with same id, type, origin, amount, memo, created_at).
- [ ] B.3.2 Every legacy `ar_transactions` row also produces a `posting` row (signed_amount = `+amount` for credits, `-amount` for debits; status mirrors; account_id mirrors).
- [ ] B.3.3 Equivalence tests in `tests/test_demo_data.py`:
  - For each `ar_transfers` row, exactly one `transfer` row with matching fields.
  - For each `ar_transactions` row, exactly one `posting` with matching account, amount, status.
  - `Σ posting.signed_amount` per transfer_id = 0 (or matches the legacy "transfer is non-zero" exception case).
- [ ] B.3.4 `pytest` clean — both old and new tables populated.
- [ ] B.3.5 Commit — `Phase B.3: AR demo writes to unified transfer + posting (dual-write)`.

---

## Phase B.4 — AR datasets read from unified schema; legacy AR tables dropped

Cutover: AR datasets stop reading legacy tables; legacy AR tables removed from `demo/schema.sql`.

- [ ] B.4.1 Rewrite each AR dataset's SQL in `account_recon/datasets.py` to project from `transfer` + `posting` instead of `ar_transfers` + `ar_transactions`. Column contracts (B.2) stay identical — only the implementation changes.
- [ ] B.4.2 Drop `ar_transfers`, `ar_transactions`, and any AR views built atop them, from `demo/schema.sql`. Update generator to skip those inserts.
- [ ] B.4.3 Update `tests/test_account_recon.py` SQL assertions for new projections.
- [ ] B.4.4 `demo apply --all` + `deploy --all --generate -c run/config.yaml -o run/out/` from repo root.
- [ ] B.4.5 `./run_e2e.sh --parallel 4` — full suite. AR e2e green; PR e2e unaffected (still on legacy tables).
- [ ] B.4.6 Commit — `Phase B.4: AR datasets read from unified schema; legacy AR txn tables dropped`.

CHECKPOINT — AR fully on unified schema. PR untouched.

---

## Phase B.5 — PR demo writes transfer chains (dual-write)

PR generator emits the chain `external_txn → payment → settlement → sale` as a tree of `transfer` rows linked by `parent_transfer_id`, with two postings per transfer. Legacy PR tables still populated for safety.

- [ ] B.5.1 Add `pr_external_customer_pool` sub-ledger account (single synthetic, per B.0.2) and any merchant-side sub-ledger accounts not already present, into the AR sub-ledger insertions.
- [ ] B.5.2 For each external_txn row: emit a top-level `transfer` (no parent, transfer_type='external_txn') + 1 posting on the external rail account.
- [ ] B.5.3 For each payment row: emit a `transfer` with `parent_transfer_id = external_txn.transfer_id` (or NULL for unmatched), transfer_type='payment', + 2 postings (debit merchant ledger account, credit external destination).
- [ ] B.5.4 For each settlement row: emit a `transfer` with `parent_transfer_id = payment.transfer_id`, transfer_type='settlement', + 2 postings (debit merchant sub-ledger, credit merchant ledger).
- [ ] B.5.5 For each sale row: emit a `transfer` with `parent_transfer_id = settlement.transfer_id`, transfer_type='sale', + 2 postings (debit `pr_external_customer_pool`, credit merchant sub-ledger).
- [ ] B.5.6 Map lifecycle status from legacy → unified (`unsettled` sale stays as a sale transfer with no settlement child; `returned` payment maps to a payment transfer with status='failed' and re-issued postings; etc.). Document the mapping in a docstring.
- [ ] B.5.7 Equivalence tests in `tests/test_demo_data.py` (PR section):
  - For every legacy PR row, exactly one corresponding `transfer` row with matching amount.
  - Chain integrity: `Σ child.amount = parent.amount` for matched chains; planted mismatches surface where the legacy tests already detect them.
  - `Σ posting.signed_amount = 0` per non-failed transfer.
- [ ] B.5.8 `pytest` clean.
- [ ] B.5.9 Commit — `Phase B.5: PR demo writes transfer chains to unified schema (dual-write)`.

---

## Phase B.6 — PR datasets read from unified schema; legacy PR tables dropped

Cutover: PR's 11 datasets stop reading legacy tables; legacy PR tables removed.

- [ ] B.6.1 Rewrite each PR dataset's SQL in `payment_recon/datasets.py` to project from `transfer` + `posting`, joining on `transfer_type` and walking `parent_transfer_id` for chain context. Column contracts unchanged where possible — only swap implementations where the contract genuinely needs to evolve.
- [ ] B.6.2 Re-implement PR exception checks against the unified schema: "settlement_payment_mismatch" becomes "transfers of type=payment whose Σ child amounts ≠ parent amount", etc. Keep the dataset-per-check shape; only the SQL changes.
- [ ] B.6.3 Drop legacy `pr_sales`, `pr_settlements`, `pr_payments`, `pr_external_transactions`, `pr_merchants` (if no longer needed), and PR views from `demo/schema.sql`. Update generator to skip those inserts.
- [ ] B.6.4 Update `tests/test_recon.py`, `tests/test_generate.py` for new SQL projections and exception logic.
- [ ] B.6.5 `demo apply --all` + `deploy --all --generate` + `./run_e2e.sh --parallel 4`. Full PR e2e green.
- [ ] B.6.6 Commit — `Phase B.6: PR datasets read from unified schema; legacy PR tables dropped`.

CHECKPOINT — both apps on unified schema. One generator path per app. ~20 datasets all on `transfer` + `posting`.

---

## Phase B.7 — Cross-app sanity sweep

The unified schema makes cross-app invariants checkable for the first time. Add a few fast guards.

- [ ] B.7.1 Codebase grep: `grep -rE 'ar_transactions|ar_transfers|pr_sales|pr_settlements|pr_payments|pr_external_transactions' src/ tests/ demo/` should return zero hits outside legacy commit history (i.e. none in current src).
- [ ] B.7.2 Add cross-app integrity test in `tests/test_demo_data.py`: `Σ posting.signed_amount` across the entire `posting` table is zero (modulo planted mismatch scenarios — list those exclusions explicitly).
- [ ] B.7.3 Add a test asserting every `transfer.transfer_type` value is in the declared CHECK enum, and every value referenced by a dataset SQL exists in actual data (catches typos in dataset filters).
- [ ] B.7.4 Commit — `Phase B.7: cross-app integrity sweeps + grep guard`.

---

## Phase B.8 — Docs sweep

Last because earlier phases churn the things docs reference.

- [ ] B.8.1 `CLAUDE.md` — Domain Model section rewritten: both apps share `transfer` + `posting`. PR is now a chain of transfers via `parent_transfer_id`. AR remains double-entry. Update Generated Output dataset list if any datasets renamed.
- [ ] B.8.2 `CLAUDE.md` — add a Conventions bullet on the column contract: "Each dataset declares a `DatasetContract`; the SQL is one implementation. Tests assert the SQL projection matches the contract."
- [ ] B.8.3 `README.md` — update both apps' tab descriptions to reflect the unified data model. Update the demo persona writeups (no behavioral change, but vocabulary shifts).
- [ ] B.8.4 `SPEC.md` — Current Spec section updated to describe the unified schema. Suggestions block stays (it's forward-planning for Phases C–E).
- [ ] B.8.5 `RELEASE_NOTES.md` — draft v1.3.0 entry. Highlights: unified `transfer` + `posting` schema, dataset column contracts, PR migrated onto transfer chains, no UI changes, one-time cleanup of stale dataset resources.
- [ ] B.8.6 Final grep sweep: any stale references to `ar_transactions`, `pr_sales`, etc. in docs/comments/docstrings.
- [ ] B.8.7 Commit — `Phase B.8: docs sweep for unified schema + column contracts`.

---

## Phase B.9 — Deploy + e2e + release

- [ ] B.9.1 `cd run && ../.venv/bin/quicksight-gen demo apply --all -c config.yaml -o out/`
- [ ] B.9.2 `cd /Users/chotchki/workspace/quicksight && .venv/bin/quicksight-gen deploy --all --generate -c run/config.yaml -o run/out/`
- [ ] B.9.3 `.venv/bin/quicksight-gen cleanup --dry-run -c run/config.yaml -o run/out/` then `--yes` to sweep stale tagged resources from any renamed datasets.
- [ ] B.9.4 `./run_e2e.sh --parallel 4` — full suite.
- [ ] B.9.5 Tag `v1.3.0`, push branch, merge to main (fast-forward), push tag.

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
