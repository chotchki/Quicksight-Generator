# QuickSight Analysis Generator

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analysis, dashboard) importable via the AWS CLI. Designed for easy mutation — change Python code or ask Claude to adjust, re-run, get new JSON.

## Quick Reference

- **Language**: Python 3.11+ (3.13 in use)
- **Package manager**: pip / setuptools, venv at `.venv/`
- **Entry point**: `python -m quicksight_gen` or `quicksight-gen` (installed script)
- **CLI framework**: Click
- **Output**: JSON files in `out/` (datasource [demo only], theme, datasets, analysis, dashboard)

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Generate all JSON
quicksight-gen generate -c config.yaml -o out/

# Generate with a theme preset
quicksight-gen generate -c config.yaml -o out/ --theme-preset sasquatch-bank

# Demo: write schema DDL / seed SQL / apply to a database
quicksight-gen demo schema -o demo/schema.sql
quicksight-gen demo seed -o demo/seed.sql
quicksight-gen demo apply -c config.yaml -o out/

# Run unit tests (fast, no AWS)
pytest

# Run end-to-end tests against a deployed dashboard (requires AWS creds)
./run_e2e.sh                  # generate + deploy + all e2e
./run_e2e.sh --skip-deploy api      # API tests only
./run_e2e.sh --skip-deploy browser  # browser tests only
```

## Generated Output

```
out/
  datasource.json             # QuickSight data source (demo apply only)
  theme.json                  # Shared blue/grey theme
  financial-analysis.json     # Consolidated analysis (financial + payment recon)
  financial-dashboard.json    # Published dashboard (public link-sharing)
  datasets/
    qs-gen-merchants-dataset.json
    qs-gen-sales-dataset.json
    qs-gen-settlements-dataset.json
    qs-gen-payments-dataset.json
    qs-gen-settlement-exceptions-dataset.json
    qs-gen-payment-returns-dataset.json
    qs-gen-external-transactions-dataset.json
    qs-gen-payment-recon-dataset.json
```

## Project Structure

```
src/quicksight_gen/
  __main__.py        # Entry point (delegates to cli.main)
  cli.py             # Click CLI: generate, demo schema/seed/apply
  config.py          # Config dataclass (incl. late_threshold_days), loads from YAML or env vars
  constants.py       # Shared sheet IDs and dataset identifier constants
  models.py          # Dataclasses mapping to QuickSight API JSON structures
  theme.py           # Theme presets (default blue/grey + sasquatch-bank green/gold)
  datasets.py        # All dataset definitions (6 financial + 2 reconciliation)
  demo_data.py       # Deterministic demo data generator (sasquatch coffee shops)
  analysis.py        # Consolidated analysis: 5 tabs (Sales, Settlements, Payments, Exceptions, Payment Recon)
  visuals.py         # Visual definitions for financial analysis tabs (Sales, Settlements, Payments, Exceptions)
  filters.py         # Filter groups and controls for financial analysis tabs
  recon_analysis.py  # (Gutted — recon consolidated into analysis.py)
  recon_visuals.py   # Payment Reconciliation visuals: KPIs, bar chart, dual tables with mutual filtering
  recon_filters.py   # Payment Reconciliation filters: date range, match status, external system, days outstanding
demo/
  schema.sql         # PostgreSQL DDL for demo database (tables, views, indexes)
tests/
  test_models.py     # Unit tests for models, tags, config, dataset builders
  test_generate.py   # Integration tests: full pipeline, cross-refs, explanations
  test_recon.py      # Unit tests for payment recon visuals and filters
  test_theme_presets.py  # Theme preset registry, serialization, analysis name integration
  test_demo_data.py      # Demo data determinism, row counts, FK integrity, scenarios
  test_demo_sql.py       # Schema/seed SQL structure, CLI command tests
  e2e/                   # End-to-end tests (skipped unless QS_GEN_E2E=1)
    conftest.py            # Skip logic, AWS clients, config loader (looks at run/config.yaml)
    browser_helpers.py     # Embed URL gen, Playwright WebKit ctx, sheet/visual waits
    test_deployed_resources.py    # API: dashboard/analysis/theme/datasets exist + healthy
    test_dashboard_structure.py   # API: definition matches expected sheets/visuals/params
    test_dataset_health.py        # API: import mode + key columns
    test_dashboard_renders.py     # Browser: page loads, 5 sheet tabs visible
    test_sheet_visuals.py         # Browser: per-sheet visual count + title spot-checks
    test_drilldown.py             # Browser: Settlements→Sales, Payments→Settlements
    test_recon_mutual_filter.py   # Browser: external txn click filters payments table
    test_filters.py               # Browser: date-range filter narrows Sales Detail
run_e2e.sh           # One-shot: regenerate JSON + deploy.sh + pytest tests/e2e
```

## Domain Model

### Financial Pipeline
**Merchants -> Sales -> Settlements -> Payments**

- Merchants make sales at locations
- Sales are bundled into settlements (settlement type depends on merchant type)
- Settlements are paid to merchants
- Key concerns: unsettled sales (exceptions) and returned payments

### Payment Reconciliation
**Internal Payments <-> External System Transactions**

- Only payments leave the internal system, so only payments reconcile against external systems
- Multiple external systems (e.g., BankSync, PaymentHub, ClearSettle) aggregate 1+ internal payments into a single external transaction
- A match is valid only when the external transaction total exactly equals the sum of linked internal payments — no partial matches
- Match statuses: **matched**, **not_yet_matched**, **late**
- "Late" threshold is config-driven (`late_threshold_days`, default 30) — users can also use the days-outstanding slider interactively
- Mutual table filtering: clicking an external transaction filters to its payments; clicking a payment filters back to its transaction

## Architecture Decisions

- All models use Python dataclasses with `to_aws_json()` methods that produce the exact dict shape for AWS CLI `create-data-source`, `create-theme`, `create-data-set`, `create-analysis`
- Helper `_strip_nones()` recursively cleans None values from serialized output
- Config accepts a pre-existing DataSource ARN for production use; for demo mode, `datasource_arn` is auto-derived from `demo_database_url` and a `datasource.json` is generated
- Datasets use custom SQL queries (PostgreSQL syntax, e.g. `CURRENT_DATE - col::date` instead of `DATEDIFF`)
- Generated resource IDs use kebab-case with a configurable prefix (default `qs-gen-`)
- All resources tagged with `ManagedBy: quicksight-gen`; extra tags via `extra_tags` in config
- Every sheet has a plain-language description and every visual has a subtitle explaining what it shows — the end customer may not be technical

## Conventions

- Type hints throughout
- One module per concern; recon visuals/filters are in separate modules but consolidated into the single analysis
- Theme presets: `default` (blue/grey) and `sasquatch-bank` (forest green/bank gold); add new presets to the `PRESETS` dict in `theme.py`
- Default theme: blues and greys, high contrast, titles >= 16px, body >= 12px
- The end customer doesn't know exactly what they want — keep the code easy to mutate and iterate on

## E2E Test Conventions

- Two layers: API (boto3) and browser (Playwright WebKit, headless). Both gated behind `QS_GEN_E2E=1`.
- Embed URL must be generated against the **dashboard region** (not the QuickSight identity region us-east-1) and is **single-use** — fixtures are function-scoped.
- DOM selectors rely on QuickSight's `data-automation-id` attributes: `analysis_visual`, `analysis_visual_title_label`, `selectedTab_sheet_name`, `sn-table-cell-{row}-{col}`, `date_picker_{0|1}`, `sheet_control_name`. Sheet tabs use `[role="tab"]`.
- Tab switches are racy: `click_sheet_tab` snapshots prior visual titles and waits for them to disappear before callers query the new sheet.
- Filter / drill-down assertions poll for the visual state to change (e.g., row count drop) rather than sleeping.
- Below-the-fold tables virtualize their cells — call `scroll_visual_into_view(page, title, timeout_ms)` before asserting on cell content or clicking a row.
- Failure screenshots saved to `tests/e2e/screenshots/` (gitignored).
- Tunables via env vars: `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT`, `QS_E2E_USER_ARN`, `QS_E2E_IDENTITY_REGION`.

## Demo data conventions

- Every visual should have non-empty data in the demo. For each new visual that relies on a scenario (drift, unmatched, failed, etc.), add a `TestScenarioCoverage` assertion in `test_demo_data.py` that guarantees ≥N rows of that shape — counts alone don't catch "zero scenario rows slipped through".
- Generators must stay deterministic (`random.Random(42)`); tests depend on exact output.
- Write the coverage assertion **before** the visual, not after. It's the fastest way to notice when generator pool-sizing or branching makes a scenario silently vanish.
