# PLAN — Phase A: Vocabulary

Goal: rename AR's `parent` / `child` vocabulary to `ledger` / `sub-ledger` across code, SQL, QuickSight labels, and docs; and add an `origin` attribute to transactions as a no-behavior-change tag for later phases to consume. Lowest-risk, highest-clarity phase of the major evolution described in `SPEC.md` — pure rename with a small additive column.

Out of scope for Phase A:
- Ledger-level direct postings (Phase C). Ledger accounts still only aggregate from sub-ledger balances; the drift invariant stays `stored parent balance = Σ children`.
- Unified `transfer` / `posting` schema (Phase B). PR sales/settlements/payments keep their current shape.
- Any reconciliation-DSL refactor (Phase D). Today's 9 bespoke exception checks stay as-is, just renamed where they reference parent/child.
- Wiring `origin` into any filter, visual, or exception check. Column-only addition.
- Any change to PR. PR has zero occurrences of `parent` / `child`; it is untouched.

Conventions:
- Branch: `phase-a-vocabulary`, cut from `main`. One phase step = one commit; cumulative release at the end.
- `demo apply` drops-and-creates schema, so there is no migration artifact to ship — rename in `demo/schema.sql` is atomic with the code rename. No backward-compatibility shims.
- `cleanup --yes` handles stale tagged resources (old dataset IDs) after deploy. Document the one-time cleanup in the release notes.
- After each phase step, run `pytest`. After A.1–A.5 land, `demo apply` + `deploy --generate` + `./run_e2e.sh` once to catch anything the unit suite missed. Before tagging, run e2e again.
- Every label change must preserve the sheet's plain-language description and every visual's subtitle (existing coverage tests enforce this).

## Vocabulary decisions (pin before any code moves)

These are the canonical renames this plan applies. Deviations get called out in A.0 below.

| Old | New | Notes |
|---|---|---|
| parent account | ledger account | user-facing + identifier |
| child account | sub-ledger account | user-facing |
| child drift | sub-ledger drift | user-facing (SPEC called this out explicitly) |
| parent drift | ledger drift | user-facing |
| `ar_parent_accounts` (table) | `ar_ledger_accounts` | |
| `ar_parent_daily_balances` | `ar_ledger_daily_balances` | |
| `ar_parent_transfer_limits` | `ar_ledger_transfer_limits` | |
| `ar_accounts` | `ar_subledger_accounts` | renamed for symmetry; see A.0 to confirm |
| `parent_account_id` (column) | `ledger_account_id` | |
| `parent_name` | `ledger_name` | |
| `account_id` (in ar_subledger_accounts / ar_transactions) | `subledger_account_id` | see A.0 |
| `ar_computed_parent_daily_balance` (view) | `ar_computed_ledger_daily_balance` | |
| `ar_computed_account_daily_balance` | `ar_computed_subledger_daily_balance` | |
| `ar_parent_balance_drift` | `ar_ledger_balance_drift` | |
| `ar_account_balance_drift` | `ar_subledger_balance_drift` | |
| `ar_child_daily_outbound_by_type` | `ar_subledger_daily_outbound_by_type` | |
| `ar_child_limit_breach` | `ar_subledger_limit_breach` | |
| `ar_child_overdraft` | `ar_subledger_overdraft` | |
| Dataset IDs `qs-gen-ar-parent-*`, `qs-gen-ar-account-*` | `qs-gen-ar-ledger-*`, `qs-gen-ar-subledger-*` | SPEC says rename freely |
| Constants `DS_AR_PARENT_*`, `DS_AR_ACCOUNTS`, `DS_AR_ACCOUNT_*` | `DS_AR_LEDGER_*`, `DS_AR_SUBLEDGER_*` | |
| Parameter `pArParentAccountId` | `pArLedgerAccountId` | drill-down parameter |
| Filter IDs `filter-ar-parent-*`, `filter-ar-child-*`, `fg-ar-parent-*`, `fg-ar-child-*` | `filter-ar-ledger-*`, `filter-ar-subledger-*`, `fg-ar-ledger-*`, `fg-ar-subledger-*` | |

`origin` attribute (new): added to `ar_transactions` only in Phase A. Schema column `origin VARCHAR(30) NOT NULL DEFAULT 'internal_initiated'`. Permitted values: `'internal_initiated'`, `'external_force_posted'`. Demo data assigns `'internal_initiated'` to ~90% of rows and `'external_force_posted'` to ~10%; generator stays deterministic.

---

## Phase A.0 — Pin decisions

STOP here. Three calls needed before any rename lands, since they cascade.

- [ ] A.0.1 **Rename `ar_accounts` → `ar_subledger_accounts`, or keep as `ar_accounts`?** The rename is more consistent (and matches the dataset-ID-rename-freely license), but `ar_accounts` is "neutral" and already reads clearly in context. Recommend **rename to `ar_subledger_accounts`** — Phase A is the one window where this cost is close to zero (no saved consumers), and leaving it as the odd one out costs clarity in every future query.
- [ ] A.0.2 **Rename `account_id` column → `subledger_account_id`, or keep as `account_id`?** Same reasoning. Recommend **keep as `account_id`** — it is the FK *target* column in `ar_subledger_accounts` and the FK *source* column in `ar_transactions`, and renaming it cascades to every SQL projection in every dataset. The long-form name in the table name carries the sub-ledger meaning; inside the table, `account_id` is unambiguous. Revisit in Phase B if the unified transfer schema wants a stricter contract.
- [ ] A.0.3 **`origin` values: `internal_initiated`/`external_force_posted`, or `internal`/`external`?** SPEC direction B used the long form. Recommend **long form** — the meaningful distinction is about *ordering* and *context*, not source-of-money; a terser `external` would get confused with "external merchant transaction" in PR. Extra bytes are worth the unambiguity.

Record the three decisions inline below this section (struck-through `old → new` lines or a short "pinned" note) before starting A.1.

---

## Phase A.1 — Schema DDL rename

Pure text rename of `demo/schema.sql`. Drop-and-create on `demo apply` means the change is atomic with the Python rename in A.2–A.4; no staged migration needed.

- [ ] A.1.1 Update the DROP section at the top to reference new names (or both old + new DROP IF EXISTS — safe on fresh DBs, useful if someone has an old schema loaded).
- [ ] A.1.2 Rename all tables (`ar_parent_accounts`, `ar_parent_daily_balances`, `ar_parent_transfer_limits`, and optionally `ar_accounts` per A.0.1).
- [ ] A.1.3 Rename all columns (`parent_account_id` → `ledger_account_id`, `parent_name` → `ledger_name`; and optionally `account_id` → `subledger_account_id` per A.0.2).
- [ ] A.1.4 Rename all views to match (5 views — see vocabulary table).
- [ ] A.1.5 Rename all indexes (`idx_ar_accounts_parent` → `idx_ar_subledger_accounts_ledger`, `idx_ar_parent_daily_balances_date` → `idx_ar_ledger_daily_balances_date`, etc).
- [ ] A.1.6 Update every SQL comment that references parent/child vocabulary to the new terms.
- [ ] A.1.7 Sanity check: `grep -iE 'parent|child' demo/schema.sql` should return only the intentional narrative in view header comments (if any remain), not any identifiers.
- [ ] A.1.8 Commit — `Phase A.1: schema DDL rename parent/child → ledger/subledger`.

**STOP** — do not run `demo apply` yet. Code in A.2+ still references the old names; the app will not generate valid JSON until A.2–A.4 land together. Bundle A.1–A.4 into one deploy cycle.

---

## Phase A.2 — Constants + dataset module rename

`constants.py` is the lynchpin — almost every other AR module imports from it. Start here so the rest of the rename is a mechanical compile-error-driven walk.

- [ ] A.2.1 Rename constants in `account_recon/constants.py`: `DS_AR_PARENT_ACCOUNTS` → `DS_AR_LEDGER_ACCOUNTS`, `DS_AR_PARENT_BALANCE_DRIFT` → `DS_AR_LEDGER_BALANCE_DRIFT`, `DS_AR_ACCOUNTS` → `DS_AR_SUBLEDGER_ACCOUNTS`, `DS_AR_ACCOUNT_BALANCE_DRIFT` → `DS_AR_SUBLEDGER_BALANCE_DRIFT`. Update the constant values (dataset IDs) accordingly — `qs-gen-ar-ledger-*`, `qs-gen-ar-subledger-*`.
- [ ] A.2.2 Rename dataset builders in `account_recon/datasets.py` to match (`build_ar_parent_accounts_dataset` → `build_ar_ledger_accounts_dataset`, etc.). Update the SQL each builder emits to reference the new table / column / view names from A.1.
- [ ] A.2.3 Update each dataset's `columns=[...]` declaration for the renamed columns.
- [ ] A.2.4 Compile-check: `.venv/bin/python -c "from quicksight_gen.account_recon import datasets, constants"` should succeed.
- [ ] A.2.5 Commit — `Phase A.2: rename AR constants + dataset builders`.

---

## Phase A.3 — Demo data generator rename

`demo_data.py` has 83 occurrences — mostly SQL INSERT generation against the renamed tables/columns, plus internal Python variable names. Rename both.

- [ ] A.3.1 Rename INSERT statements and any raw SQL inside `account_recon/demo_data.py` to the new names.
- [ ] A.3.2 Rename Python-side identifiers: internal function names (`_generate_parent_accounts` → `_generate_ledger_accounts`, etc), variable names (`parent_accounts`, `parent_id`, `child_id`), tuple fields, and docstrings.
- [ ] A.3.3 Keep determinism (`random.Random(42)`); the output row *values* should be byte-identical to pre-rename (same IDs, same amounts, same dates). Only table/column names in the generated SQL change.
- [ ] A.3.4 Skim the generated `seed.sql` diff: confirm the only changes are identifier renames, not data shifts. `.venv/bin/quicksight-gen demo seed account-recon -o /tmp/seed-new.sql && diff -u demo/seed.sql /tmp/seed-new.sql | head -50` should show pure text substitutions.
- [ ] A.3.5 Commit — `Phase A.3: rename AR demo-data generator to ledger/subledger vocabulary`.

---

## Phase A.4 — Analysis / visuals / filters rename

The bulk of the string work: 140 occurrences in `visuals.py`, 45 in `analysis.py`, 39 in `filters.py`. Includes user-facing titles and subtitles — these carry the most behavioral weight because they are what the end customer reads.

- [ ] A.4.1 `account_recon/visuals.py`:
  - Rename visual IDs (`ar-balances-kpi-parents` → `ar-balances-kpi-ledgers`, `ar-balances-parent-table` → `ar-balances-ledger-table`, etc.).
  - Rename field IDs inside visuals (`ar-bal-parent-id` → `ar-bal-ledger-id`, `ar-bal-parent-name` → `ar-bal-ledger-name`).
  - Rewrite every `Title=...` and `Subtitle=...` call whose text contains "parent" or "child". Example: `Title("Parent Account Balances")` → `Title("Ledger Account Balances")`; `Subtitle("Each parent account's stored vs computed daily balance. Computed = Σ of its children's stored balances...")` → `Subtitle("Each ledger account's stored vs computed daily balance. Computed = Σ of its sub-ledgers' stored balances...")`.
  - Rename the drill-down parameter constant at the top of the file (`P_AR_PARENT` → `P_AR_LEDGER`) and its value (`pArParentAccountId` → `pArLedgerAccountId`).
  - Update the module docstring (lines 1–25) to use new vocabulary.
- [ ] A.4.2 `account_recon/filters.py`:
  - Rename filter-group builder functions (`_parent_account_filter_group` → `_ledger_account_filter_group`, `_child_account_filter_group` → `_subledger_account_filter_group`).
  - Rename `fg_id`, `filter_id`, and `title` values (`fg-ar-parent-account` → `fg-ar-ledger-account`, `filter-ar-parent-account` → `filter-ar-ledger-account`, `"Parent Account"` → `"Ledger Account"`, and the same for child → sub-ledger).
  - Update Show-Only-X toggle titles if any reference child/parent ("Show Only Drift" does not; "Show Only Overdraft" does not — most toggles are orthogonal).
- [ ] A.4.3 `account_recon/analysis.py`:
  - Update any filter-group ID references that match A.4.2's renames.
  - Rewrite Getting Started rich-text content (if it mentions parent/child) — use `common/rich_text.py` the same way the existing text is authored.
  - Update every sheet description.
- [ ] A.4.4 `account_recon/__init__.py`: if it re-exports anything renamed above, update.
- [ ] A.4.5 `.venv/bin/pytest tests/test_account_recon.py` — will fail, but failures should be mechanical (strings / IDs). Fix the production code if any failure is logic (shouldn't happen), update the test if it's a vocabulary assertion (expected).
- [ ] A.4.6 Commit — `Phase A.4: rename AR analysis/visuals/filters to ledger/subledger vocabulary`.

**STOP** — after A.4, check the Getting Started rich-text content by eye. Customer-facing text is the one place silent vocabulary drift (e.g., "parent" surviving in a text block) would be most visible. Pre-flight that block explicitly.

---

## Phase A.5 — Tests update

205 occurrences across 9 test files. Mostly string assertions against IDs, titles, and filter labels; some test data setup referencing old column names.

- [ ] A.5.1 `tests/test_account_recon.py` — update every expected-string assertion, visual ID check, filter title check, dataset ID check. This is the biggest concentration (159 hits).
- [ ] A.5.2 `tests/test_demo_sql.py` and `tests/test_demo_data.py` — update table/column/view name assertions.
- [ ] A.5.3 E2E tests under `tests/e2e/`:
  - `test_ar_dashboard_structure.py` — sheet IDs stay, filter group IDs and parameter IDs change.
  - `test_ar_dataset_health.py` — dataset IDs change, column names change.
  - `test_ar_sheet_visuals.py` — visual titles change (user-visible strings).
  - `test_ar_drilldown.py` — parameter name changes (`pArParentAccountId` → `pArLedgerAccountId`), click-target titles change.
  - `test_ar_state_toggles.py` — most toggle titles are vocabulary-neutral; sweep anyway.
  - `test_ar_filters.py` — filter control titles change ("Parent Account" → "Ledger Account").
  - `browser_helpers.py` and `conftest.py` — 2 hits each; probably variable names in helper fixtures.
- [ ] A.5.4 Run full unit/integration suite: `.venv/bin/pytest`. Green before moving to A.6.
- [ ] A.5.5 Commit — `Phase A.5: update tests to ledger/subledger vocabulary`.

---

## Phase A.6 — Add `origin` attribute to transactions

Additive-only. No filter, no visual wiring, no exception check uses it yet. This plants the column so Phase B / Phase D / future e2e coverage has something real to read.

- [ ] A.6.1 `demo/schema.sql`: add `origin VARCHAR(30) NOT NULL DEFAULT 'internal_initiated' CHECK (origin IN ('internal_initiated', 'external_force_posted'))` to `ar_transactions`. Place the column after `transfer_type` for semantic grouping.
- [ ] A.6.2 `account_recon/demo_data.py`: generator emits `origin` on every transaction. Default `internal_initiated` for ~90%; sprinkle `external_force_posted` on ~10% at a deterministic offset (e.g., "every 10th transaction whose `transaction_id` hashes to an even value"). Add a new `TestScenarioCoverage` assertion in `test_demo_data.py` guaranteeing ≥ N rows of each `origin` value (per the CLAUDE.md convention: "Write the coverage assertion before the visual, not after").
- [ ] A.6.3 `account_recon/datasets.py`: add `origin` to the `ar_transactions` dataset's `columns=[...]` list and to the dataset's `SELECT` projection. No changes to any other dataset.
- [ ] A.6.4 Transactions detail visual: add `origin` as a visible column. This is a pure-display tweak — no drill, no filter, no conditional format. Worth doing in A.6 so the column is "real" in the UI, not just schema; also confirms end-to-end wiring works.
- [ ] A.6.5 `tests/test_demo_data.py` — scenario coverage for origin distribution. `tests/test_account_recon.py` — dataset column contract includes `origin`. Both green.
- [ ] A.6.6 Commit — `Phase A.6: add origin attribute to transactions (internal_initiated / external_force_posted)`.

**STOP** — confirm before moving on: `origin` is tag-only in Phase A. No filter-control, no exception check, no drill-down targeting. If the idea of wiring it to a filter starts feeling compelling, defer that to a Phase A.6.5 sub-task — but do not expand scope under the "while I'm here" impulse.

---

## Phase A.7 — Docs sweep

Last because earlier phases churn the things the docs reference.

- [ ] A.7.1 `CLAUDE.md` — update the Domain Model → Account Reconciliation section to use ledger/sub-ledger vocabulary. Update the Generated Output dataset list (new IDs). Update the Project Structure section if any file names changed (none expected).
- [ ] A.7.2 `README.md` — update the "Account Reconciliation — 5 tabs" table, the dataset list, the drift-check descriptions. Preserve the plain-language tone.
- [ ] A.7.3 `SPEC.md` — this already describes Phase A's intent, but the *current* spec sections above the Suggestions block still use parent/child. Sweep those to the new vocabulary, since they're documenting the as-of-today state which now matches the new names.
- [ ] A.7.4 `RELEASE_NOTES.md` — draft v1.2.0 entry. Highlight: vocabulary rename (user-visible across every AR tab), `origin` column added for future use, no behavioral changes. Call out the one-time cleanup requirement (stale tagged resources from old dataset IDs).
- [ ] A.7.5 Search for any stray "parent" / "child" vocabulary in code comments, docstrings, or rich-text blocks: `grep -irE 'parent|child' src/quicksight_gen/account_recon tests demo/schema.sql` should return zero non-intentional hits.
- [ ] A.7.6 Commit — `Phase A.7: docs sweep for ledger/subledger vocabulary + origin column`.

---

## Phase A.8 — Deploy + e2e verification + release

- [ ] A.8.1 `cd run && ../.venv/bin/quicksight-gen demo apply --all -c config.yaml -o out/` — applies new schema, seeds new data, regenerates JSON.
- [ ] A.8.2 `.venv/bin/quicksight-gen deploy --all --generate -c run/config.yaml -o run/out/` — deploys updated datasets + analyses + dashboards.
- [ ] A.8.3 `.venv/bin/quicksight-gen cleanup --dry-run -c run/config.yaml -o run/out/` — confirm the dry-run lists only the old `qs-gen-ar-parent-*` / `qs-gen-ar-account-*` datasets as stale, and nothing else. Then `--yes` to sweep them.
- [ ] A.8.4 `./run_e2e.sh --parallel 4` — full e2e suite against the redeployed dashboards. Fix any browser tests that the rename missed (most likely: a hard-coded visual title string in a test that A.5.3 didn't catch).
- [ ] A.8.5 Tag `v1.2.0`, push branch `phase-a-vocabulary`, open PR.
- [ ] A.8.6 Merge to main (fast-forward preferred — this is a linear rename), push tag.

---

## Decisions to make in flight

- **Origin value strings: `internal_initiated` / `external_force_posted`, or hyphenated per SPEC prose?** Recommend underscore — SQL identifiers, string-column values in a Postgres column will flow through SQL filters and the hyphen form requires quoting in enum-style `CHECK` constraints. User-facing display can still hyphenate via the visual label if desired.
- **Do we rename `ar_accounts` → `ar_subledger_accounts` or keep as `ar_accounts`?** Decided in A.0.1; default recommendation is rename, but revisit if A.2 surfaces unexpected collateral damage.
- **Do old dataset JSON files (`qs-gen-ar-parent-accounts-dataset.json`, etc.) get pruned by `generate`?** `generate` already prunes stale dataset JSON that belongs to neither app (per CLAUDE.md). If the prune logic is name-based, it'll handle this automatically on first regenerate; if it's strict whitelist-based, the stale files will need one manual `rm out/datasets/qs-gen-ar-parent*` before redeploy. Verify in A.2 or A.8.
- **Should the `origin` column value for imported/reconciled rows in Phase B (later) back-fill based on their source system, or stay `internal_initiated` by default?** Out of scope for A, but worth flagging in the A.6 commit message so Phase B sees it.

## Risks

- **E2E label drift**: 7 AR e2e test files assert on user-visible strings (titles, filter labels). Some may miss the rename if the assertion uses a substring match (`"Balances" in title`) rather than equality. Scan for both `==` and `in` / `contains` patterns in A.5.3.
- **Hard-coded dataset IDs in e2e config or Playwright selectors**: QuickSight DOM has no dataset IDs in the rendered HTML, but e2e API-layer tests assert on dataset ARNs. These are derived from IDs at deploy time, so they will update naturally — but `test_ar_dataset_health.py` is likely the biggest concentration and deserves a careful read.
- **Rich-text block on Getting Started sheet**: XML-composed. An un-renamed "parent" in a text block won't fail any test but will read wrong. A.4.3's STOP is there to catch this.
- **External stakeholders' mental model**: if any reviewer is used to reading the old vocabulary in demos or screenshots, flag the rename in the v1.2.0 release notes so the cutover doesn't look like a regression.
