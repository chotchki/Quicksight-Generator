# QuickSight Analysis Generator

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analyses, dashboards) and deploys them via boto3. Ships **two independent QuickSight apps** sharing one theme, account, datasource, and CLI surface:

- **Payment Reconciliation** — 6 sheets: Getting Started, Sales, Settlements, Payments, Exceptions, Payment Reconciliation
- **Account Reconciliation** — 5 sheets: Getting Started, Balances, Transfers, Transactions, Exceptions

The customer doesn't know exactly what they want yet. Everything is generated from code and deployed idempotently (delete-then-create) so a change is one command to roll out.

## Quick Reference

- **Language**: Python 3.11+ (3.13 in use)
- **Package manager**: pip / setuptools, venv at `.venv/`
- **Entry point**: `python -m quicksight_gen` or `quicksight-gen` (installed script)
- **CLI framework**: Click
- **Output**: JSON files in `out/` (theme, per-app analysis/dashboard, datasets, optional datasource)

## Commands

```bash
# Install dependencies (add [demo] for `demo apply`, which needs psycopg2)
pip install -e ".[dev]"
pip install -e ".[demo]"

# Generate all JSON (both apps, one theme)
quicksight-gen generate --all -c config.yaml -o out/

# Generate a single app
quicksight-gen generate payment-recon -c config.yaml -o out/
quicksight-gen generate account-recon -c config.yaml -o out/ --theme-preset sasquatch-bank-ar

# Deploy to AWS (delete-then-create; polls async resources to terminal state)
quicksight-gen deploy --all -c config.yaml -o out/

# Typical iteration loop: regenerate + deploy in one shot
quicksight-gen deploy --all --generate -c config.yaml -o out/

# Cleanup: delete ManagedBy:quicksight-gen resources not in current out/
quicksight-gen cleanup --dry-run
quicksight-gen cleanup --yes

# Demo: schema DDL / seed SQL / apply to a Postgres database
quicksight-gen demo schema --all -o demo/schema.sql
quicksight-gen demo seed   --all -o demo/seed.sql
quicksight-gen demo apply  --all -c config.yaml -o out/

# Tests
pytest                              # unit + integration, fast, no AWS
./run_e2e.sh                        # regenerate + deploy both apps + e2e (pytest-xdist -n 4)
./run_e2e.sh --parallel 8           # override worker count (1 = serial; stable ceiling ~8)
./run_e2e.sh --skip-deploy api      # API e2e only
./run_e2e.sh --skip-deploy browser  # browser e2e only
```

`demo apply` is app-scoped: `demo apply payment-recon` generates with the `sasquatch-bank` preset; `demo apply account-recon` uses `sasquatch-bank-ar`; `--all` generates both with each app's natural preset. Schema is always loaded in full (both apps share one Postgres DB, `pr_` / `ar_` table prefixes).

## Generated Output

```
out/
  datasource.json                     # demo apply only
  theme.json                          # one shared theme
  payment-recon-analysis.json
  payment-recon-dashboard.json
  account-recon-analysis.json
  account-recon-dashboard.json
  datasets/
    qs-gen-merchants-dataset.json            # 11 PR datasets
    qs-gen-sales-dataset.json
    qs-gen-settlements-dataset.json
    qs-gen-payments-dataset.json
    qs-gen-settlement-exceptions-dataset.json
    qs-gen-payment-returns-dataset.json
    qs-gen-sale-settlement-mismatch-dataset.json
    qs-gen-settlement-payment-mismatch-dataset.json
    qs-gen-unmatched-external-txns-dataset.json
    qs-gen-external-transactions-dataset.json
    qs-gen-payment-recon-dataset.json
    qs-gen-ar-ledger-accounts-dataset.json   # 21 AR datasets
    qs-gen-ar-subledger-accounts-dataset.json
    qs-gen-ar-transactions-dataset.json
    qs-gen-ar-ledger-balance-drift-dataset.json
    qs-gen-ar-subledger-balance-drift-dataset.json
    qs-gen-ar-transfer-summary-dataset.json
    qs-gen-ar-non-zero-transfers-dataset.json
    qs-gen-ar-limit-breach-dataset.json
    qs-gen-ar-overdraft-dataset.json
    qs-gen-ar-sweep-target-nonzero-dataset.json              # 9 CMS-specific checks
    qs-gen-ar-concentration-master-sweep-drift-dataset.json
    qs-gen-ar-ach-orig-settlement-nonzero-dataset.json
    qs-gen-ar-ach-sweep-no-fed-confirmation-dataset.json
    qs-gen-ar-fed-card-no-internal-catchup-dataset.json
    qs-gen-ar-gl-vs-fed-master-drift-dataset.json
    qs-gen-ar-internal-transfer-stuck-dataset.json
    qs-gen-ar-internal-transfer-suspense-nonzero-dataset.json
    qs-gen-ar-internal-reversal-uncredited-dataset.json
    qs-gen-ar-expected-zero-eod-rollup-dataset.json          # 3 cross-check rollups
    qs-gen-ar-two-sided-post-mismatch-rollup-dataset.json
    qs-gen-ar-balance-drift-timelines-rollup-dataset.json
```

`generate` (single app) prunes stale dataset JSON that belongs to neither app — so renaming or dropping a dataset doesn't leave an orphan that `deploy` would re-create. The other app's dataset files are preserved.

## Project Structure

```
src/quicksight_gen/
  __main__.py            # Entry point (delegates to cli.main)
  cli.py                 # Click CLI: generate / deploy / cleanup / demo (all with --all or app arg)
  common/
    config.py            # Config dataclass + YAML/env loader (principal_arns list, late_default_days, theme_preset)
    models.py            # Dataclasses mapping to QuickSight API JSON (to_aws_json + _strip_nones)
    theme.py             # Theme presets (default / sasquatch-bank / sasquatch-bank-ar); PRESETS registry
    deploy.py            # boto3 delete-then-create deploy with async waiters
    cleanup.py           # Tag-based cleanup of stale resources (ManagedBy:quicksight-gen)
    dataset_contract.py  # ColumnSpec, DatasetContract, build_dataset() — shared dataset constructor
    clickability.py      # Conditional-format helpers: accent text (left-click) + tint-background (right-click)
    aging.py             # Shared aging_bar_visual() — horizontal bar chart by aging bucket (used by both apps)
    rich_text.py         # XML composition helpers for SheetTextBox.Content (heading/bullets/link/inline)
  payment_recon/
    analysis.py          # 6 sheets, drill-downs, filter groups, dashboard builder
    visuals.py           # Sales / Settlements / Payments / Exceptions visuals
    recon_visuals.py     # Payment Reconciliation side-by-side tables + KPIs
    filters.py           # Pipeline-tab filter groups + controls
    recon_filters.py     # Payment Reconciliation filters (date, match status, ext system, days outstanding)
    datasets.py          # 11 custom-SQL datasets
    demo_data.py         # Sasquatch National Bank demo generator
    constants.py         # Sheet + dataset identifier constants
  account_recon/
    analysis.py          # 5 sheets, drill-downs, filter groups, dashboard builder
    visuals.py           # Balances / Transfers / Transactions / Exceptions visuals
    filters.py           # Per-tab filters + Show-Only-X toggles
    datasets.py          # 21 custom-SQL datasets (9 baseline + 9 CMS checks + 3 rollups)
    demo_data.py         # Sasquatch National Bank — CMS treasury demo generator
    constants.py         # Sheet + dataset identifier constants
demo/
  schema.sql             # Full PostgreSQL DDL (both apps — pr_ and ar_ prefixes)
tests/
  test_models.py         # Models, tags, config, dataset builders
  test_generate.py       # Full pipeline, cross-refs, explanations (PR)
  test_account_recon.py  # AR visuals, filters, datasets, analysis wiring
  test_recon.py          # Payment recon visuals + filters
  test_theme_presets.py  # Preset registry, serialization, analysis name integration
  test_dataset_contract.py # DatasetContract basics + per-builder column-match assertions
  test_demo_data.py      # Demo determinism, row counts, FK integrity, scenario coverage, cross-app integrity
  test_demo_sql.py       # Schema/seed SQL structure, CLI command tests
  e2e/                   # Two layers (API boto3 + browser Playwright WebKit); gated on QS_GEN_E2E=1
    conftest.py
    browser_helpers.py
    test_deployed_resources.py / test_ar_deployed_resources.py
    test_dashboard_structure.py / test_ar_dashboard_structure.py
    test_dataset_health.py     / test_ar_dataset_health.py
    test_dashboard_renders.py  / test_ar_dashboard_renders.py
    test_sheet_visuals.py      / test_ar_sheet_visuals.py
    test_drilldown.py          / test_ar_drilldown.py
    test_state_toggles.py      / test_ar_state_toggles.py
    test_filters.py            / test_ar_filters.py
    test_recon_mutual_filter.py
scripts/
  screenshot_getting_started.py   # Ad-hoc: screenshot both Getting Started tabs
run_e2e.sh
```

## Domain Model

### Unified Schema

Both apps share two core tables:

- **`transfer`** — one row per financial event (sale, settlement, payment, external_txn, ach, wire, internal, cash, funding_batch, fee, clearing_sweep). Linked via `parent_transfer_id` to form chains (PR) or standalone pairs (AR). Key fields: `transfer_type`, `origin`, `amount`, `status`, `external_system`, `memo`.
- **`posting`** — one row per ledger leg. FK to `transfer`; `ledger_account_id NOT NULL` (every posting knows its ledger); `subledger_account_id` nullable (NULL for direct ledger postings). `signed_amount` is positive (debit) or negative (credit). Non-failed postings within a transfer net to zero (except external_txn and fee transfers, which are intentionally single-leg).

AR datasets read exclusively from `transfer` + `posting` (the `ar_transactions` table was dropped in Phase B.4). PR datasets still read from legacy `pr_*` tables for domain-specific metadata (card_brand, settlement_type, payment_method, etc.) but also emit to `transfer` + `posting` via dual-write.

### Payment Reconciliation
**Merchants → Sales → Settlements → Payments → External Transactions**

- Merchants make sales at locations
- Sales bundle into settlements (settlement type depends on merchant type)
- Settlements get paid to merchants as payments
- Payments leave the internal system, so only payments reconcile against external systems
- Multiple external systems (BankSync, PaymentHub, ClearSettle) aggregate 1+ internal payments into one external transaction
- Match is valid only when external total exactly equals sum of linked payments — no partials
- Match statuses: **matched**, **not_yet_matched**, **late** (threshold: `late_default_days`, default 30 — slider also available)
- Mutual table filtering on the Payment Reconciliation tab: clicking an external txn filters its payments; clicking a payment filters back
- All 5 PR exception checks and the Payment Recon tab carry `aging_bucket` (same 5-band pattern as AR) with aging bar charts
- **Transfer chain** (parent → child): `external_txn → payment → settlement → sale`. PR sub-ledger accounts live under `pr-merchant-ledger` in `ar_subledger_accounts` (one per merchant + `pr-external-customer-pool` + `pr-external-rail`).

### Account Reconciliation
**Ledger accounts (with daily balances) → Sub-ledger accounts → Postings (double-entry ledger)**

- Every transfer is a set of posting legs that must net to zero
- Postings can target sub-ledger accounts OR ledger accounts directly (funding batches, fee assessments, clearing sweeps, all CMS-driven sweeps)
- Ledger drift invariant: `stored ledger balance = Σ direct ledger postings + Σ sub-ledger stored balances`
- Sub-ledger drift invariant: `stored sub-ledger balance = Σ postings to that sub-ledger` (unaffected by ledger-level postings)
- Daily balance snapshots allow drift detection: recomputed balance vs. stored balance
- Failed postings, limit breaches (ledger daily out-flow cap per sub-ledger/type), and overdrafts (sub-ledger below zero) populate the Exceptions tab
- Every exception check follows a standard visual pattern: KPI count + detail table (with `days_outstanding` and `aging_bucket` columns) + horizontal aging bar chart. Drift checks also have timelines.
- Aging buckets: 5 hardcoded bands (`1: 0-1 day`, `2: 2-3 days`, `3: 4-7 days`, `4: 8-30 days`, `5: >30 days`) — numeric prefix forces correct sort in QuickSight
- Drift timelines (ledger + sub-ledger) surface systemic issues over time
- Transfers carry an `origin` tag (`internal_initiated` / `external_force_posted`); origin multi-select filter on Transactions + Exceptions tabs
- AR views filter `WHERE transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')` to exclude PR data

#### CMS structure (Phase F)

Demo persona is **Sasquatch National Bank — Cash Management Suite (CMS)** — same SNB from PR, viewed through treasury after SNB absorbed Farmers Exchange Bank's commercial book.

- **8 internal GL control accounts**: Cash & Due From FRB, ACH Origination Settlement (`gl-1810`), Card Acquiring Settlement, Wire Settlement Suspense, Internal Transfer Suspense (`gl-1830`), Cash Concentration Master (`gl-1850`), Internal Suspense / Reconciliation, Customer Deposits — DDA Control.
- **7 customer DDAs**: 3 coffee retailers shared with PR (Bigfoot Brews, Sasquatch Sips, Yeti Espresso) + 4 commercial (Cascade Timber Mill, Pinecrest Vineyards, Big Meadow Dairy, Harvest Moon Bakery).
- **4 telling-transfer flows from CMS**: ZBA / Cash Concentration sweep → Concentration Master; daily ACH origination sweep → FRB Master Account; external force-posted card settlement → Card Acquiring Settlement; on-us internal transfer → Internal Transfer Suspense → destination DDA. Each flow plants both success cycles and characteristic failures.
- **Exceptions tab structure**: 3 cross-check rollups at the top (expected-zero EOD, two-sided post-mismatch, balance drift timelines) teach error-class recognition; per-check details below let analysts drill the specific row. 14 checks total: 5 baseline (sub-ledger drift, ledger drift, non-zero transfers, limit breach, overdraft) + 9 CMS-specific (sweep target nonzero, concentration master sweep drift, ACH orig settlement nonzero, ACH sweep no Fed confirmation, Fed card no internal catch-up, GL vs FRB master drift, internal transfer stuck, internal transfer suspense nonzero, internal reversal uncredited).

## Architecture Decisions

- All models use Python dataclasses with `to_aws_json()` methods that produce the exact dict shape for AWS QuickSight API (`create-analysis`, `create-dashboard`, `create-data-set`, `create-theme`, `create-data-source`)
- Helper `_strip_nones()` recursively cleans None values from serialized output
- Config accepts a pre-existing DataSource ARN for production use; for demo, `datasource_arn` is auto-derived from `demo_database_url` and `datasource.json` is generated
- All datasets use custom SQL in PostgreSQL syntax (no SPICE → Direct Query). Seed changes show up immediately after `demo apply` — no refresh step.
- Generated resource IDs use kebab-case with a configurable prefix (default `qs-gen-`)
- All resources tagged `ManagedBy: quicksight-gen`; `extra_tags` in config are merged in
- `cleanup` uses that tag to enumerate managed resources and deletes anything not in the current `out/`
- Every sheet has a plain-language description; every visual has a subtitle — the end customer is not technical. Coverage is enforced in unit + API e2e tests.
- Clickable cells use `common/clickability.py`: accent-colored text = left-click drill; accent text on pale-tint background = right-click menu drill

## Conventions

- Type hints throughout
- **Never hardcode hex colors in analysis code.** Resolve from `get_preset(cfg.theme_preset).<token>` at generate time (accent, primary_fg, link_tint, etc.).
- One module per concern; `payment_recon/` has `visuals.py` + `recon_visuals.py` and `filters.py` + `recon_filters.py` because the Payment Reconciliation tab is a distinct UX pattern
- Theme presets live in the `PRESETS` dict in `common/theme.py`; set `analysis_name_prefix="Demo"` on demo presets
- Default theme: blues and greys, high contrast, titles ≥ 16px, body ≥ 12px
- The end customer doesn't know exactly what they want — keep the code easy to mutate and iterate on
- Rich text on Getting Started sheets uses `common/rich_text.py`; theme-accent colors resolve to hex at generate time
- Each dataset declares a `DatasetContract` (column name + type list) in its `datasets.py`; the SQL query is one implementation. Tests assert the SQL projection matches the contract. `build_dataset()` in `common/dataset_contract.py` is the shared constructor.

## E2E Test Conventions

- Two layers: API (boto3) and browser (Playwright WebKit, headless). Both gated behind `QS_GEN_E2E=1`.
- Embed URL must be generated against the **dashboard region** (not the QuickSight identity region us-east-1) and is **single-use** — fixtures are function-scoped.
- DOM selectors rely on QuickSight's `data-automation-id` attributes: `analysis_visual`, `analysis_visual_title_label`, `selectedTab_sheet_name`, `sn-table-cell-{row}-{col}`, `date_picker_{0|1}`, `sheet_control_name`. Sheet tabs use `[role="tab"]`.
- Tab switches are racy: `click_sheet_tab` snapshots prior visual titles and waits for them to disappear before callers query the new sheet.
- Filter / drill-down assertions poll for the visual state to change (e.g., row count drop) rather than sleeping.
- Below-the-fold tables virtualize their cells — call `scroll_visual_into_view(page, title, timeout_ms)` before asserting on cell content or clicking a row.
- QS tables also virtualize vertically (~10 DOM rows at a time, regardless of page size). `count_table_rows` returns only the DOM-visible count, which saturates at ~10. For filter-narrowing assertions where before/after may exceed the viewport, use `count_table_total_rows` + `wait_for_table_total_rows_to_change` — they focus the visual, bump page size to 10000, and scroll-accumulate the true total. Slower (~1–3s); prefer the DOM helpers when the table is small.
- Failure screenshots saved to `tests/e2e/screenshots/<app>/` (gitignored). Per-app subdirs keep PR and AR screenshots separated.
- Tunables via env vars: `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT`, `QS_E2E_USER_ARN`, `QS_E2E_IDENTITY_REGION`.

## Demo Data Conventions

- Every visual should have non-empty data in the demo. For each new visual that relies on a scenario (drift, unmatched, failed, returned, limit-breach, overdraft, etc.), add a `TestScenarioCoverage` assertion in the app's demo-data tests that guarantees ≥N rows of that shape — counts alone don't catch "zero scenario rows slipped through".
- Generators must stay deterministic (`random.Random(42)`); tests depend on exact output.
- Write the coverage assertion **before** the visual, not after. It's the fastest way to notice when generator pool-sizing or branching makes a scenario silently vanish.
- Each app has its own demo persona — same Sasquatch National Bank, two operational views: PR is the merchant-acquiring side (coffee-shop settlement); AR is the treasury / CMS side (GL control accounts + customer DDAs absorbed from FEB). Don't cross-contaminate at the persona level — they share schema and three customer DDAs (the coffee retailers) but the rest of the data is disjoint.
