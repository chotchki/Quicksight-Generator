# Release Notes

## v1.1.0

### Filter-propagation browser e2e expansion

The browser e2e suite previously spot-checked a single date-range filter on one table per app. Every other filter was trusted to work if the dashboard JSON referenced it. v1.1.0 closes that gap on the Payment Recon side, captures one documented QuickSight limitation, and parallelizes the suite so the wider coverage fits the runtime budget.

### What landed

- **Payment Recon filter-propagation coverage** (Phases 1–2):
  - Shared filter-interaction helpers in `tests/e2e/browser_helpers.py` — `set_dropdown_value`, `set_multi_select_values`, `clear_dropdown`, `set_date_range`, `count_table_rows` / `count_table_total_rows` (pagination-aware), `count_chart_categories` (canvas-aware via aria-label + legend fallback), `read_kpi_value` / `wait_for_kpi_value_to_change`, plus `wait_for_*_to_change` pollers for each.
  - Split the shared `fg-date-range` filter group into four per-sheet groups (`fg-{sales,settlements,payments,exceptions}-date-range`), each scoped to its sheet's native timestamp column. The old `CrossDataset="ALL_DATASETS"` control rendered but was inert on sheets whose dataset didn't have a `sale_timestamp` column.
  - New parametrized tests for future-window, past-window, and in-window date filtering on Sales / Settlements / Payments.
- **Documented QS navigation filter-stacking** (Phase 5): drill-down-set parameters persist across tab-switches (`A → B → A` leaves B-derived filter on A). QuickSight has no API to clear a parameter on nav. Captured as `xfail(strict=False)` in `tests/e2e/test_filter_stacking.py`, documented under "Known limitations" in README, and called out on both Getting Started sheets (accent-colored bullet).
- **Parallelized e2e suite** (Phase 6): added `pytest-xdist`, default `-n 4` in `run_e2e.sh`, `--parallel N` override. Full 101-item suite drops from ~305s serial to ~133s at `-n 4` and ~81s at `-n 8`; `-n 12` flakes (timing-sensitive date-range narrowing).
- **Dedup pass** (Phase 1.8): five DOM-probe helpers (`selected_sheet_name`, `wait_for_sheet_tab`, `first_table_cell_text`, `wait_for_table_cells_present`, `click_first_row_of_visual`) plus `sheet_control_titles` / `wait_for_sheet_controls_present` / `wait_for_visual_titles_present` extracted from per-file copies into `browser_helpers.py`.

### Known gap

Account Recon filter-propagation coverage was deferred ahead of a major spec revision that will refactor AR heavily. Existing AR e2e still covers rendering, drill-downs, and Show-Only-X toggles; filter-propagation parity with PR will return after the revision lands.

### Notes

- **253 unit/integration tests**, **101 e2e tests** (94 passed / 6 skipped / 1 xfailed) — all green.
- No schema, dataset, or generated-resource ID changes beyond the internal split of `fg-date-range` into four per-sheet filter groups. Safe in-place redeploy.
- `run_e2e.sh --parallel 8` is the recommended stable ceiling on a modern Mac; `--parallel 1` forces serial.

---

## v1.0.1

### Post-release polish

Two small UX fixes from first round of v1.0.0 testing:

- **Payment Reconciliation tab — table order swapped.** Internal Payments now renders on the left, External Transactions on the right. Reading flow goes internal → external, matching the rest of the pipeline (sales → settlements → payments → external).
- **Account Recon Transfers tab — duplicate filter removed.** The "Show Only Unhealthy" SINGLE_SELECT toggle was redundant with the "Transfer Status" multi-select (both filtered on `net_zero_status`). Dropped the toggle; the multi-select stays.

### Notes

- Tests: 253 unit/integration (was 254 — one toggle assertion folded into a no-toggle assertion), 75 e2e — all green.
- No schema, dataset, or generated-resource ID changes; safe in-place redeploy.

---

## v1.0.0

### Spec complete — dual-dashboard restructure delivered

v1.0.0 ships the full spec: two independent QuickSight apps (Payment Reconciliation + Account Reconciliation) generated from Python, deployed via boto3, tested at four layers (unit, integration, API e2e, browser e2e). Both apps share one theme, account, datasource, and CLI surface, yet are selectable individually for fast iteration (`--all` exercises both, `payment-recon` / `account-recon` targets one).

### What landed since v0.5.0

- **Account Recon Phase 4** (v0.6.0): multi-select filters per tab (parent/child account, transfer status, transaction status); Show-Only-X SINGLE_SELECT toggles (unhealthy transfers, failed transactions, drift); left-click and right-click drill-downs covering all six user-research flows; Parent Drift Timeline alongside the existing Child Drift Timeline; same-sheet chart filtering on every new chart.
- **Account Recon Phase 5** (v0.7.0): per-type daily transfer limits (ACH / wire / internal / cash) enforced against parent limits fed upstream, plus child overdraft detection. Exceptions tab grew from 3 independent checks to 5 (parent drift, child drift, non-zero transfers, limit breaches, child overdrafts) laid out as paired half-width tables + two drift timelines for maximum density.
- **Account Recon browser e2e** (v0.8.0): 16 Playwright tests mirror PR's coverage — dashboard load, per-sheet visual counts, drill-downs (Balances→Txn, Transfers→Txn, Exceptions Breach→Txn), date-range filter narrowing, all five Show-Only-X toggles. Right-click `DATA_POINT_MENU` drill is covered structurally (Playwright menu-select is flaky). Screenshots namespaced per app under `tests/e2e/screenshots/{payment_recon,account_recon}/`.
- **Rich-text Getting Started sheets** (v1.0.0, Phase 6): both apps' landing tabs use proper typography — 36px welcome, 32px section headings, 20px subheadings, accent-colored links, bulleted per-sheet summaries — via a new `common/rich_text.py` XML composition helper. Theme accent resolves to hex at generate time (QuickSight text parser doesn't accept theme tokens).
- **Docs refresh** (v1.0.0, Phase 7): README rewritten for the two-app structure; CLAUDE.md updated for the `common/` + per-app module layout; SPEC.md swept — delivered checkboxes flipped, open questions collapsed into a Decisions section.

### Stats

- **~16,030 lines of Python** (10,570 in `src/`, 5,460 in `tests/`) + 485 lines of schema DDL.
- **254 unit / integration tests**, **75 e2e tests** (329 total), **436 assert statements**.
- **2 apps** (6 + 5 = 11 sheets), **20 datasets** (11 PR + 9 AR), **3 theme presets**, **1 shared datasource**.

### Notes

- The e2e suite is gated on `QS_GEN_E2E=1` and requires AWS credentials; `pytest` alone runs the 329 fast tests with no AWS dependency.
- Dataset Direct Query (no SPICE) — seed changes show up immediately after `demo apply`, no refresh step needed.
- `cleanup --dry-run` / `cleanup --yes` sweeps stale `ManagedBy: quicksight-gen` resources not in current `out/`.

---

## v0.5.0

### Account Reconciliation — second app

Phase 3 adds a second QuickSight app, Account Reconciliation, alongside the existing Payment Reconciliation dashboard. The AR dashboard covers a bank's double-entry ledger with two independent stored-balance feeds (parent-level and child-level) and reconciles both against the underlying transactions.

### New app

- **Account Reconciliation dashboard** — 5 tabs (Getting Started + Balances, Transfers, Transactions, Exceptions). Shared date-range filter; drill-downs and multi-select filters land in Phase 4.
- **Two independent drift checks** exposed side-by-side on the Exceptions tab:
  - Parent drift — stored parent balance vs Σ of its children's stored balances (points at the parent-balance upstream feed).
  - Child drift — stored child balance vs running Σ of posted transactions (points at the child-balance feed or a ledger miss).
- **Transfer reconciliation** — transfers are not a table; they're a `transfer_id` grouping of `ar_transactions`. `ar_transfer_summary` surfaces net-zero status and a representative memo per transfer. The Exceptions tab flags transfers whose non-failed legs don't sum to zero (failed counter-leg, keying error, fee drift).
- **`farmers-exchange-bank` theme preset** — earth tones, valley greens, harvest gold. Applies the "Demo — " analysis name prefix when selected.
- **Farmers Exchange Bank demo data** — 5 parent accounts (Big Meadow Checking, Harvest Moon Savings, Orchard Lending Pool, Valley Grain Co-op, Harvest Credit Exchange) moving money between 10 child accounts over ~40 days. Planted: 3 parent-day drifts, 4 child-day drifts (disjoint from parent cells), 4 failed-leg transfers, 4 off-amount transfers, 4 fully-failed transfers.
- **CLI — two-app aware** — `generate account-recon`, `demo schema|seed|apply account-recon`, `deploy account-recon`, and `--all` exercises both apps.

### Scope clarification (SPEC)

"Internal" vs "external" describes **this application's reconciliation scope**, not system ownership. All accounts (internal + external, parent + child) appear in the same tables; external-scope accounts are present but not reconciled (that's regulators' job). Parent-level and child-level stored balances may be fed by different upstream systems, which is why the two drift checks are independent.

### Resources

- Dashboard: `qs-gen-account-recon-dashboard`
- Analysis: `qs-gen-account-recon-analysis`
- 7 AR datasets: parent_accounts, accounts, transactions, parent_balance_drift, account_balance_drift, transfer_summary, non_zero_transfers
- 5 AR tables (`ar_parent_accounts`, `ar_accounts`, `ar_parent_daily_balances`, `ar_account_daily_balances`, `ar_transactions`) + 6 views (`ar_computed_account_daily_balance`, `ar_account_balance_drift`, `ar_computed_parent_daily_balance`, `ar_parent_balance_drift`, `ar_transfer_net_zero`, `ar_transfer_summary`)

### Notes

- AR browser e2e tests and cross-sheet drill-downs deferred to Phase 5.
- Phase 3 review caught a scope gap — child balances were not reconciled in the initial skeleton. Resolved in Phase 3.10 with an independent `ar_account_daily_balances` feed and a second drift view.

---

## v0.4.0

### Payment Reconciliation domain additions

Phase 2 bundles refunds, optional sales metadata, payment-method filtering, an expanded Exceptions tab, a Getting Started landing sheet, right-click drill-downs, and state-toggle filters into a richer Payment Reconciliation experience. Dashboard goes from 5 tabs to 6.

### New features

- **Refund support** — `sale_type` column on `pr_sales` with negative amounts; refund rows flow into settlements so signed sums net correctly.
- **Optional sales metadata** — taxes / tips / discount_percentage / cashier declared in `OPTIONAL_SALE_METADATA`. Each column auto-generates a typed filter control on Sales Overview (numeric → slider, string → multi-select).
- **Payment method filter** — multi-select dropdown scoped to Settlements + Payments tabs.
- **Expanded Exceptions & Alerts** — three new mismatch tables (sale↔settlement, settlement↔payment, unmatched external transactions) alongside the existing unsettled-sales and returned-payments tables.
- **Getting Started landing sheet** — now tab index 0, with one plain-text block per downstream sheet plus a demo-scenario flavor block when `--theme-preset sasquatch-bank` is active. Rich text / hyperlink formatting deferred to Phase 6.
- **Right-click drill-downs** — Sales `settlement_id` → Settlements, Payments `external_transaction_id` → Payment Reconciliation. Source cells styled with a pale tint to cue the menu. Plain left-click drills keep their accent-only styling for a visual distinction between the two click idioms.
- **Payment Reconciliation side-by-side tables** — External Transactions and Internal Payments render half-width rather than stacked; mutual click-filter still works.
- **State toggles (Show-Only-X)** — SINGLE_SELECT dropdowns on Sales ("Show Only Unsettled"), Settlements ("Show Only Unpaid"), Payments ("Show Only Unmatched Externally"). These replace the per-tab days-outstanding slider, which turned out to overlap with the existing date-range filter.
- **Orphan external transactions in demo data** — the generator now always emits ~13 ext txns with no internal payment link plus ~4 unmatched payments, so Payments toggle, Exceptions table, and Payment Reconciliation all have data out-of-the-box.

### Changed

- Dashboard sheet count: 5 → 6 (Getting Started added at index 0).
- Filter group count: raised from ~11 to 18+ (optional-metadata filters, state toggles, drill-down parameter filters, recon filters).
- Exceptions & Alerts visual count: 4 → 7.
- Demo data: refund rows added to sales; external transactions restructured to guarantee unmatched coverage.

### Removed

- **Days-outstanding slider** — removed from every tab. The date-range filter already covered the workflow and the slider duplicated intent. Replaced by Show-Only-X toggles on the three pipeline tabs.

### Notes

- Right-click menus rely on `DATA_POINT_MENU` trigger — only one left-click action per visual is allowed, so the menu trigger is how additional click targets surface without conflicting with charts' drill-down behavior.
- Every sheet still has a plain-language description; every visual still has a subtitle. Coverage asserted in unit and API e2e tests.

---

## v0.3.0

### End-to-end test harness

A two-layer e2e harness validates a deployed dashboard, complementing the existing unit suite. Tests are skipped by default unless `QS_GEN_E2E=1` is set, so a plain `pytest` run stays AWS-free.

**API layer (boto3, ~13s):** dashboard / analysis / theme / dataset existence and status, dashboard structure (sheets, visual counts, parameters, filter groups, dataset declarations), dataset import mode and key columns.

**Browser layer (Playwright WebKit headless, ~60s):** dashboard loads via a pre-authenticated embed URL, all 5 sheet tabs render, per-sheet visual counts in the actual DOM, Settlements→Sales and Payments→Settlements drill-down navigation, Payment Reconciliation mutual table filtering (external transaction click filters payments table), and date-range filter behavior (future date range empties Sales Detail).

### One-shot runner

`./run_e2e.sh` regenerates JSON, runs `deploy.sh`, then `pytest tests/e2e` so iteration is hands-off:

```bash
./run_e2e.sh                       # full cycle
./run_e2e.sh --skip-deploy api     # skip generate+deploy, API only
./run_e2e.sh --skip-deploy browser # skip generate+deploy, browser only
```

### New features

- 33 e2e tests across 8 test files under `tests/e2e/`
- Tunable timeouts via `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT` env vars (defaults 30s / 10s)
- Failure screenshots saved to `tests/e2e/screenshots/` (gitignored)
- New `e2e` optional dependency group: `pip install -e ".[e2e]"` then `playwright install webkit`

### Notes

- Embed URL must be generated against the **dashboard region**, not the QuickSight identity region (us-east-1). Embed URLs are **single-use** so fixtures are function-scoped.
- The conftest looks for config at `config.yaml` then `run/config.yaml` then env vars.

---

## v0.2.0

### Consolidated single-analysis architecture

The separate reconciliation analysis has been merged into the financial analysis as the **Payment Reconciliation** tab. The project now generates one analysis and one dashboard (down from two of each), reducing deployment complexity and enabling cross-sheet drill-down without URL-based linking.

### Payment-only reconciliation

Reconciliation now correctly focuses on payments -- the only records that leave the internal system. Sales and settlements no longer have external transaction IDs or recon views. This eliminated 3 datasets, 2 database views, and the `late_thresholds` table.

### New features

- **Payment Reconciliation tab** with 3 KPIs (matched amount, unmatched amount, late count), a stacked bar chart (match status by external system), and dual mutually-filterable tables (external transactions and internal payments)
- **Mutual table filtering** -- click an external transaction to see its linked payments; click a payment to filter back to its transaction
- **Config-driven late threshold** (`late_threshold_days`, default 30) replaces the database table. Users can also adjust interactively via the days-outstanding slider
- **Same-sheet chart filtering** on all tabs -- clicking a bar or pie slice filters the detail table on the same sheet
- **Cross-sheet drill-down** -- click a settlement row to jump to Sales filtered by that settlement; click a payment row to jump to Settlements

### Breaking changes

- `recon-analysis.json` and `recon-dashboard.json` are no longer generated. Delete them from AWS before deploying (`./deploy.sh --delete`)
- Dataset count reduced from 11 to 8. The removed datasets: `qs-gen-sales-recon-dataset`, `qs-gen-settlement-recon-dataset`, `qs-gen-recon-exceptions-dataset`
- `external_transaction_id` removed from sales and settlements datasets/schema
- `transaction_type` removed from external_transactions dataset/schema
- `late_thresholds` table removed from demo schema
- `build_recon_analysis()` and `build_recon_dashboard()` no longer exist

### Bug fixes

- Fixed `DefaultFilterControlConfiguration` rejection by using `SINGLE_DATASET` scope with direct filter controls for single-sheet filters
- Fixed `SetParametersOperation` requiring a preceding `NavigationOperation`
- Fixed QuickSight rejecting multiple `DATA_POINT_CLICK` actions on a single visual

---

## v0.1.0

Initial release. Financial analysis with 4 tabs (Sales, Settlements, Payments, Exceptions), reconciliation analysis with 4 tabs, demo data system, theme presets, and deploy script.
