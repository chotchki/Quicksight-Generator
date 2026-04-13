# Release Notes

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
