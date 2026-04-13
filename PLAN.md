# PLAN — Dual-dashboard restructure + Account Recon

Goal: migrate the existing Payment Recon app into a multi-app structure, then add the Account Recon app. Review gates (**STOP**) are placed wherever the spec leaves layout or flow to iteration.

Conventions:
- Branch is already isolated; no git gymnastics needed between phases.
- After each task, run the unit suite; after each phase, run the full e2e suite (unless the phase explicitly hasn't touched deploy yet).
- Each **STOP** pauses for user review + potential replanning before the next phase.
- Phase 1 is pure refactor — no user-visible behavior change on Payment Recon.
- PLAN.md checkboxes are flipped as items complete. SPEC.md checkboxes are **not** touched in flight — they are swept once in Phase 7.3.
- After each phase's commit + tag, push the branch and the tag.

## Carried-forward assumptions (from SPEC follow-ups)

- Single `late_default_days` config value used as the default for every days-outstanding slider; users override interactively.
- Optional-sales-metadata columns are declared in a Python constant adjacent to the sales SQL in `payment_recon/datasets.py` (runtime DB introspection ruled out — production `generate` has no DB creds).
- Non-demo analysis titles: "Payment Reconciliation" and "Account Reconciliation". Demo-themed variants prefix with "Demo — ".
- Shared PG schema in demo DB; tables prefixed `pr_` (Payment Recon) and `ar_` (Account Recon).
- `cleanup` gathers all stale tagged resources, prints them, and asks once (y/n) before deleting. `--yes` skips the prompt; `--dry-run` only prints.
- Getting Started sheet sheet-switch links — if QuickSight text-blocks don't support hyperlinks to sibling sheets, fall back to a small navigation-button visual per target sheet (decide during 2.6).

---

## Phase 1 — Restructure into `payment_recon/` + `common/` (no feature change)

- [x] 1.1 Create `src/quicksight_gen/common/` and migrate the shared primitives: `models.py`, `theme.py`, `config.py` (update schema for `late_default_days`), `constants.py` (non-app-specific only), `tags.py` (extracted), `deploy.py` (new — see 1.6), `cleanup.py` (new — see 1.7).
- [x] 1.2 Create `src/quicksight_gen/payment_recon/` and move the existing app modules into it: `datasets.py`, `visuals.py`, `filters.py`, `analysis.py`, `recon_visuals.py`, `recon_filters.py`, `demo_data.py`, `constants.py` (app-specific sheet IDs).
- [x] 1.3 Rename "financial" → "payment-recon" everywhere: output filenames (`payment-recon-analysis.json`, `payment-recon-dashboard.json`), resource IDs, dataset prefixes where applicable, analysis default name ("Payment Reconciliation"; demo: "Demo — Payment Reconciliation").
- [x] 1.4 Restructure the Click CLI into subcommands:
  - `quicksight-gen generate payment-recon [--theme-preset …]`
  - `quicksight-gen generate --all`
  - `quicksight-gen demo schema|seed|apply payment-recon|--all`
  - Stub `account-recon` subcommand group that raises `NotImplementedError` so test shape is stable.
- [x] 1.5 Add `quicksight-gen deploy [payment-recon|account-recon|--all] [--generate] [--yes]`: Python port of `deploy.sh`, delete-then-create semantics (no update), async waiters for analyses/dashboards. `--generate` chains `generate` first so iteration is one command.
- [x] 1.6 Add `quicksight-gen cleanup [--dry-run] [--yes]`: lists QuickSight resources in the configured account+region tagged `ManagedBy: quicksight-gen` that are NOT in the current generate output; bulk y/n confirm then deletes. Explicit command only (not chained into `deploy`).
- [x] 1.7 Delete `deploy.sh` and `run_e2e.sh`'s shell calls to it; replace with the new Python command.
- [x] 1.8 Update unit tests: fix imports, expected resource IDs, output filenames, CLI subcommand shape; keep coverage green.
- [x] 1.9 Update e2e tests: change `dashboard_id` fixture to `qs-gen-payment-recon-dashboard`; update any tests referencing old analysis name. Keep test count/behavior identical.
- [x] 1.10 Update `run_e2e.sh` to call `quicksight-gen deploy --all --generate` (or equivalent) then `pytest tests/e2e`.
- [x] 1.11 Full test pass: `pytest` green + `./run_e2e.sh` green against a freshly redeployed dashboard.
- [x] 1.11a Add support for multiple principal_arn values in config.yaml so that multiple users can view the dashboards
- [x] 1.12 Run a full destroy to clean up any renamed resources.
- [x] 1.13 Redeploy and rerun 1.11.
- [x] **STOP for review.**
- [x] 1.14 git commit, tag v0.3.1, push branch + tag

---

## Phase 2 — Payment Recon domain additions

- [x] 2.1 Refund support: add `sale_type` column to `pr_sales` (values `sale`, `refund`), allow negative `amount`. Update demo seed to include refund rows (some timestamped later than the original sale, some not). Sales Detail table displays `sale_type`. Verify settlements/payments can net negative via signed sums.
- [x] 2.2 Optional sales metadata plumbing: declare taxes / tips / discount_percentage / cashier in a Python constant (`OPTIONAL_SALE_METADATA`) adjacent to the sales SQL, each with its SQL column + data type. Surface them on Sales Detail always. Auto-generate per-sheet filter controls by type (numeric→range, string→multi-select, date/timestamp→date-range).
- [x] 2.3 Payment methods as a filter: add `payment_method` to the merchants (or sales) schema, expose as a multi-select filter on Settlements and Payments tabs. No group-by.
- [x] 2.4 Expand Exceptions & Alerts:
  - Keep the existing unsettled-sales and returned-payments tables.
  - Add a Sales → Settlement mismatch table (sales linked to a settlement where Σ(linked sales) ≠ settlement amount).
  - Add a Settlement → Payment mismatch table (settlements linked to a payment where Σ(linked settlements) ≠ payment amount).
  - Move "external transactions without a payment" from the Payment Reconciliation tab into here.
  - Layout deliberately compact — minimize whitespace; use half-width / multi-column grids.
- [x] 2.5 Days-outstanding slider: *shipped then removed in review.* The slider was added per tab per the plan, but the date-range filter already covered the same need. Replaced with **Show-Only-X SINGLE_SELECT toggles** on Sales ("Show Only Unsettled"), Settlements ("Show Only Unpaid"), and Payments ("Show Only Unmatched Externally"). No slider anywhere now.
- [x] 2.6 "Getting Started" sheet as tab index 0: one auto-derived text block per downstream sheet (sourced from each sheet's existing plain-language description). Demo mode adds a 1–2 paragraph scenario flavor block at the top. Attempt inline hyperlinks; if unsupported, add a small navigation-button visual row. *Note: rich-text formatting deferred to Phase 6 — current blocks are plain text.*
- [x] 2.7 Update unit tests: refund math, optional-metadata filter derivation, new exception tables & subtitles, toggle presence on each tab, Getting Started tab at index 0, explanation coverage still 100%.
- [x] 2.8 Update e2e tests: new dashboard structure (6 tabs now including Getting Started), visual counts, new exception tables assertable, one browser test for the state toggles (replacing the slider browser test).
- [x] **STOP for review.** Review added: right-click drill-down pattern (settlement_id on Sales, external_transaction_id on Payments), side-by-side recon tables, slider → toggle pivot, orphan external transactions in demo data.
- [x] 2.9 git commit, tag v0.4.0, push branch + tag

---

## Phase 2.5 — Cross-app plumbing (pre-Phase-3 cleanup)

*Lessons from Phase 2 review: factor shared primitives into `common/` before Account Recon starts adding drill-downs and browser tests.*

- [x] 2.5.1 Move clickability text-format helpers from `payment_recon/visuals.py` to `common/clickability.py`: `link_text_format(accent)` (plain-accent cell for left-click drill) and `menu_link_text_format(accent, tint)` (accent + pale-tint for right-click drill). Update both payment_recon modules to import from there.
- [x] 2.5.2 ~~Codify the subtitle phrasing pattern for click targets~~ — skipped. A helper that appends "Click … to …" would force every subtitle through the same mold; current subtitles carry visual-specific context that a formulaic suffix would flatten.
- [x] 2.5.3 Add `scroll_visual_into_view(page, title, timeout_ms)` to `tests/e2e/browser_helpers.py`. Refactor `test_recon_mutual_filter.py` to use it instead of its inline evaluate block.
- [x] 2.5.4 Add a `TestScenarioCoverage` pattern note to `CLAUDE.md` under "Project Structure" or a new "Test Conventions" section — seed-data coverage tests go in before visuals, not after. Keep it one paragraph.
- [x] 2.5.5 Run unit tests + e2e. Commit.

---

## Phase 3 — Account Recon skeleton (all 4 tabs, rough layout)

- [x] 3.1 Create `src/quicksight_gen/account_recon/` with `datasets.py`, `visuals.py`, `filters.py`, `analysis.py`, `demo_data.py`, `constants.py`.
- [x] 3.2 Demo schema (shared PG schema, `ar_` prefixed):
  - `ar_parent_accounts` (id, name, is_internal)
  - `ar_accounts` (id, name, is_internal, parent_account_id)
  - `ar_parent_daily_balances` + `ar_account_daily_balances` (split in 3.10 — two independent stored feeds)
  - `ar_transactions` (id, account_id, transfer_id, amount, posted_at, status, memo) — memo denormalized; transfers joined via `transfer_id`
  - Views: `ar_computed_account_daily_balance`, `ar_account_balance_drift`, `ar_computed_parent_daily_balance`, `ar_parent_balance_drift`, `ar_transfer_net_zero`, `ar_transfer_summary`.
- [x] 3.3 Demo data generator for the Farmers Exchange Bank scenario — generic valley/farm/harvest naming, no trademarked game characters/places. 80/20 success/failure mix. Plant:
  - balance-drift cases (stored ≠ computed on specific days);
  - transfers whose net-of-non-failed transactions ≠ 0;
  - individual failed transactions.
- [x] 3.4 `farmers-exchange-bank` theme preset: earth tones + valley greens + harvest gold. Applies the "Demo — " prefix to the AR analysis when selected.
- [x] 3.5 Rough 4-tab layout (date-range filter only; no drill-downs/extra sliders yet):
  - **Balances** — parent accounts (name, stored daily balance, computed daily balance, drift) + child accounts table.
  - **Transfers** — transfer list with Σdebit, Σcredit, net, net-zero flag, memo.
  - **Transactions** — transactions table with status, amount, posted_at, transfer_id, memo; failed rows called out.
  - **Exceptions** — balance-drift table, non-net-zero transfer table, timeline visual (line/bar by day showing when mismatches occurred).
- [x] 3.6 Getting Started sheet for AR (same pattern as PR: auto-derived instructions + demo scenario block).
- [x] 3.7 CLI wiring: implement the `account-recon` branches on `generate`, `demo schema|seed|apply`, `deploy`; `--all` now exercises both apps.
- [x] 3.8 Unit tests for AR: visual builders, filter groups, cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet ID scoping), explanation coverage, theme preset integration, demo data determinism + row counts + scenario coverage.
- [x] **STOP for review.** (Layout iteration expected — filters, drill-downs, and visual choices all deferred to Phase 4.) *Review found: child-account daily balances not stored/reconciled — scope revision follows in 3.10.*
- [x] 3.10 Child-account balance reconciliation (scope revision — see SPEC "Reconciliation scope" bullet):
  - Schema: rename `ar_daily_balances` → `ar_parent_daily_balances`; add `ar_account_daily_balances` (account_id, balance_date, balance) seeded for internal child accounts; add view `ar_account_balance_drift` (stored − running Σ posted transactions per child per day); keep existing parent-level view.
  - Demo data: generate child daily balances for the 6 internal children across the full window; plant child-level drift on 3–4 (account, days_ago) cells **independently** from the existing parent-level plants so the two drift tables surface different rows.
  - Datasets: add `qs-gen-ar-account-balance-drift-dataset`; rename `qs-gen-ar-balance-drift-dataset` → `qs-gen-ar-parent-balance-drift-dataset` and the matching `DS_AR_BALANCE_DRIFT` constant for symmetry.
  - Visuals: on Balances, replace the plain child-accounts directory with a Child Account Balances table fed from the child-drift view (mirrors the parent table). On Exceptions, add a Child Balance Drift table next to the existing Parent Balance Drift (rename existing visual/title for clarity).
  - Tests: extend row-count and scenario-coverage tests (child-balance rows, both-sign child drift plants); schema SQL for new table + view; updated sheet/visual counts.
  - Redeploy and spot-check before commit.
- [x] 3.11 git commit, tag v0.5.0, push branch + tag

---

## Phase 4 — Account Recon iteration (post-review)

*Task list finalized at Phase 3 review. Independent parent/child drift (added in 3.10) reshapes what drill-downs, toggles, and timelines make sense — the skeleton had generic placeholders; this phase turns them into concrete workflows.*

- [x] 4.1 Filters:
  - Parent-account multi-select on Balances, Transactions, Exceptions.
  - Child-account multi-select on Balances, Transactions, Exceptions.
  - Transfer-status multi-select on Transfers.
  - Transaction-status multi-select on Transactions.
- [x] 4.2 Show-Only-X SINGLE_SELECT toggles (same pattern as PR's Phase 2 pivot — the date-range filter already covers "recency", toggles cover the "narrow to problems" intent):
  - Transfers: "Show Only Unhealthy" (net-of-non-failed ≠ 0).
  - Transactions: "Show Only Failed".
  - Balances parent table: "Show Only Drift".
  - Balances child table: "Show Only Drift".
- [x] 4.3 Drill-downs (plain-accent = left-click drill; pale-tint menu-link = right-click `DATA_POINT_MENU` drill, used when a visual already has a left-click target):
  - Balances child row (left-click on `account_id`) → Transactions filtered by account + date.
  - Balances parent row (right-click menu on `parent_account_id`) → filters child table on the same sheet to that parent's children.
  - Transfers row (left-click on `transfer_id`) → Transactions filtered by `transfer_id`.
  - Exceptions parent-drift row (left-click) → Balances child table filtered to that parent's children + date.
  - Exceptions child-drift row (left-click) → Transactions filtered by account + date.
  - Exceptions non-zero-transfer row (left-click) → Transactions filtered by `transfer_id`.
- [x] 4.4 Visual additions:
  - **Parent Drift Timeline** on Exceptions, placed alongside the existing Child Drift Timeline — two independent timelines make the two-feed story visible.
  - **Transfer Status bar chart** on Transfers (healthy / non-zero), with same-sheet click-filter into the transfers table.
  - **Transactions-by-day line chart** on Transactions grouped by status, with same-sheet click-filter into the detail table.
- [x] 4.5 Same-sheet chart filtering on every new chart (matches PR's pattern) — clicking a bar/slice filters the detail table on the same sheet.
- [x] 4.6 Unit tests: new filter groups, drill-down action shapes, visual count updates, toggle presence per tab, cross-reference validation, explanation coverage still 100%.
- [x] 4.7 API-layer e2e tests for AR: dashboard/analysis/theme/datasets exist, sheet count (5), per-sheet visual counts, parameters, filter groups, dataset import health.
- [x] 4.8 Redeploy and spot-check.
- [x] **STOP for review.** Review found: internal↔internal transfers missing from demo, and no visibility of internal/external scope on Transactions or Transfer Summary — fix bundled into 4.10.
- [x] 4.9 git commit, tag v0.6.0, push branch + tag
- [x] 4.10 Mid-phase coverage hardening (added during STOP review):
  - Mix internal↔internal transfers into every bucket of `_generate_transfers` so bugs requiring two tracked balances per transfer can't hide.
  - Surface `scope` on Transactions and `scope_type` (cross_scope / internal_only) on Transfer Summary; add `has_external_leg` to the `ar_transfer_net_zero` view.
  - Add `TestScenarioCoverage` assertions for ≥20 cross-scope + ≥15 internal-only + ≥1 internal-only-with-failed-leg transfers.

---

## Phase 5 — Account Recon: per-type daily transfer limits + child overdrafts

*Scope addition made during Phase 4 planning: parents define per-type daily transfer limits that apply to their child accounts; child balances must not go negative. Adds two more independent reconciliation checks alongside parent drift and child drift, for four total on the Exceptions tab. Placed after Phase 4 so the new visuals can reuse the drill-down patterns established there rather than co-inventing them.*

- [x] 5.1 Schema additions:
  - Add `transfer_type` column to `ar_transactions` (STRING; values `'ach' | 'wire' | 'internal' | 'cash'`). Orthogonal to debit/credit direction.
  - New table `ar_parent_transfer_limits` (parent_account_id, transfer_type, daily_limit). Upstream-fed; a given parent may have limits defined for only some types — absence means "no limit enforced".
  - Views:
    - `ar_child_daily_outbound_by_type` — Σ |amount| per (child account, date, transfer_type) across non-failed transactions on the debit side.
    - `ar_child_limit_breach` — joins outbound-by-type to parent-limits; emits rows where daily outbound for type T exceeds the parent's limit for T.
    - `ar_child_overdraft` — rows where the stored child balance < 0 for a given day.
- [x] 5.2 Demo data generator:
  - Assign a `transfer_type` to each transfer (weighted mix so all four types have traffic).
  - Seed `ar_parent_transfer_limits` for each parent on a subset of types (some strict, some lenient, some unlimited — i.e., no row at all for that type).
  - Plant ≥3 limit-breach cases (child × day × type) **disjoint** from the existing drift plants so each exception table surfaces a different set of rows.
  - Plant ≥3 overdraft cases (child × day) **disjoint** from the drift and breach plants.
  - `TestScenarioCoverage` assertions authored **before** the visuals, per the seed-before-visuals rule in `CLAUDE.md`.
- [x] 5.3 Datasets:
  - Add `qs-gen-ar-limit-breach-dataset` and `qs-gen-ar-overdraft-dataset`.
  - Extend `qs-gen-ar-transactions-dataset` with the new `transfer_type` column.
- [x] 5.4 Visuals on Exceptions tab:
  - Add Child Limit Breach table (account, date, type, outbound, limit, overage).
  - Add Child Overdraft table (account, date, stored balance).
  - KPI row grows from 3 → 5 ("Limit Breach Days", "Overdraft Days"); reflow as one-fifth columns or wrap to a second KPI row depending on readability.
  - Rework the Exceptions tables from single-column to paired half-width rows for density — four drift/breach/overdraft tables + the two timelines fit in ~half the vertical span.
- [x] 5.5 Filters:
  - Transfer-type multi-select on Transactions, Exceptions, and (if meaningful) Transfers.
  - Show-Only-Overdraft toggle on the Balances child table.
- [x] 5.6 Getting Started updates:
  - Rewrite the Exceptions description to cover all four checks (parent drift, child drift, limit breach, overdraft).
  - Update `_DEMO_SCENARIO_FLAVOR` to mention the limit and overdraft plants.
- [x] 5.7 Drill-downs:
  - Limit Breach row (left-click) → Transactions filtered by account + date + type.
  - Overdraft row (left-click) → Transactions filtered by account + date.
- [x] 5.8 Tests:
  - Schema/SQL structure tests for the new table + views.
  - Demo-data coverage + row-count assertions (breach count ≥3, overdraft count ≥3, per-type traffic, disjointness from existing plants).
  - Unit tests for new visuals / filters / drill-downs; cross-reference validation; sheet+visual-count updates.
  - API-layer e2e: new datasets exist, new filter groups present, Exceptions sheet visual count matches.
- [x] 5.9 Redeploy and spot-check.
- [x] **STOP for review.**
- [x] 5.10 git commit, tag v0.7.0, push branch + tag

---

## Phase 6 — AR browser e2e + harness updates

- [x] 6.1 Extend `tests/e2e/conftest.py` with a second dashboard fixture (`ar_dashboard_id`); keep the two fixtures independent (no parametrized dual-run). *Done in Phase 4.7 — fixtures already in place when Phase 6 opened.*
- [x] 6.2 Browser tests for AR: dashboard loads, tab count (5: Getting Started + 4), per-sheet visual counts, drill-downs from 4.3 and 5.7, filter narrowing, Show-Only-X toggles, right-click `DATA_POINT_MENU` drill. *Note: right-click `DATA_POINT_MENU` drill is covered by the API test `test_parent_drill_scoped_to_child_table_only` — Playwright right-click + menu-item-select is flaky enough that a structural assertion is the more stable guard.*
- [x] 6.3 Update `run_e2e.sh` so the one-shot runner deploys both and runs the full e2e suite. *Already calls `deploy --all --generate`; no change needed.*
- [x] 6.4 Namespace screenshot output per-app if it reduces noise (`tests/e2e/screenshots/payment_recon/`, `…/account_recon/`).
- [x] **STOP for review.**
- [x] 6.5 git commit, tag v0.8.0, push branch + tag

---

## Phase 7 — Docs + release

- [ ] 7.1 README.md: two-app overview, project structure, CLI reference (`generate` / `deploy` / `cleanup` / `demo` with `--all`), demo scenarios, theming presets.
- [ ] 7.2 CLAUDE.md: new module layout, `common/` API surface, deploy-in-Python note, two-app conventions.
- [ ] 7.3 SPEC.md sweep — the one-time pass for this document: check off every item delivered across Phases 1–6, prune follow-up questions that have been resolved, and reword any lines that drifted from the shipped design. Per the Conventions note above, SPEC boxes are not touched before this step.
- [ ] 7.4 RELEASE_NOTES.md entry — version v1.0.0 at release time - include count of lines of code, number of tests/asserts
- [ ] 7.5 Tag and push, merge to main
