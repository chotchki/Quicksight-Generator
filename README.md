# QuickSight Analysis Generator

A Python tool that programmatically generates AWS QuickSight JSON definitions for financial reporting and payment reconciliation. It outputs standalone JSON files that can be imported directly via the AWS CLI.

## Why this exists

The customer for these reports doesn't know exactly what they want yet. Rather than clicking through the QuickSight console to build analyses by hand (and losing that work when requirements change), this project generates everything from code. Change the Python, re-run, get new JSON. You can also ask Claude to modify the reports for you.

## What it generates

### Theme

| File | Description |
|---|---|
| `out/theme.json` | Blue/grey colour palette, high-contrast readability |

### Financial datasets (6)

| File | Description |
|---|---|
| `out/datasets/qs-gen-merchants-dataset.json` | Merchant ID, name, type, location |
| `out/datasets/qs-gen-sales-dataset.json` | Sale details with amount, timestamp, card info |
| `out/datasets/qs-gen-settlements-dataset.json` | Settlement status, type, amounts |
| `out/datasets/qs-gen-payments-dataset.json` | Payment status, return flag/reason |
| `out/datasets/qs-gen-settlement-exceptions-dataset.json` | Sales missing settlements (LEFT JOIN) |
| `out/datasets/qs-gen-payment-returns-dataset.json` | Returned payments detail |

### Reconciliation datasets (2)

| File | Description |
|---|---|
| `out/datasets/qs-gen-external-transactions-dataset.json` | External system transaction aggregations |
| `out/datasets/qs-gen-payment-recon-dataset.json` | Payments matched against external transactions |

### Consolidated Analysis (`out/financial-analysis.json`)

5 tabs covering the full financial pipeline and payment reconciliation.

- **Sales Overview** -- KPIs (count, amount), bar charts (by merchant, by location), sales detail table. Click a bar to filter the detail table.
- **Settlements** -- KPIs (settled amount, pending count), bar chart (by merchant type), settlement detail table. Click a bar to filter the detail table. Click a row to drill down to Sales.
- **Payments** -- KPIs (paid amount, returned count), pie chart (status breakdown), payment detail table. Click a slice to filter the detail table. Click a row to drill down to Settlements.
- **Exceptions & Alerts** -- KPIs (unsettled sales, returned payments), unsettled sales table, returned payments table
- **Payment Reconciliation** -- KPIs (matched amount, unmatched amount, late count), bar chart (match status by external system), dual mutually-filterable tables (external transactions and internal payments). Click a bar to filter both tables. Click an external transaction to see its linked payments. Click a payment to see its transaction.

All tabs have date range, merchant, and location filters. The Settlements and Exceptions tabs add a settlement status filter. The Payments tab adds a payment status filter. The Payment Reconciliation tab has its own match status, external system, and days-outstanding filters.

### Published Dashboard (`out/financial-dashboard.json`)

A published dashboard wrapping the analysis. Enables ad-hoc filtering, CSV export, and expanded sheet controls. Accessible to the configured `principal_arn`.

### Tags and explanations

All generated resources are tagged with `ManagedBy: quicksight-gen` (additional tags configurable via `extra_tags` in config). Every sheet has a plain-language description and every visual has a subtitle explaining what it shows.

## Quick start

### Prerequisites

- Python 3.11+
- An AWS account with QuickSight Enterprise enabled
- A pre-existing QuickSight datasource connected to your SQL database (not needed for demo mode)

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configure

Copy the example config and fill in your values:

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
aws_account_id: "123456789012"
aws_region: "us-east-1"

# ARN of a pre-existing QuickSight datasource.
# Not required when demo_database_url is set (auto-derived from account/region/prefix).
datasource_arn: "arn:aws:quicksight:us-east-1:123456789012:datasource/your-datasource-id"

# Optional: prefix for generated resource IDs (default: qs-gen)
resource_prefix: "qs-gen"

# Optional: IAM principal to grant permissions on all generated resources
principal_arn: "arn:aws:quicksight:us-east-1:123456789012:user/default/admin"

# Optional: days before an unmatched payment is considered "late" (default: 30)
late_threshold_days: 30

# Optional: additional tags applied to all generated resources
extra_tags:
  Environment: production
  Team: finance
```

All values can also be set via environment variables with a `QS_GEN_` prefix (e.g. `QS_GEN_AWS_ACCOUNT_ID`). Environment variables override the YAML file.

### Generate JSON

```bash
python -m quicksight_gen generate -c config.yaml -o out
```

This writes 11 JSON files to `out/` (1 theme, 8 datasets, 1 analysis, 1 dashboard). Each file is a standalone payload ready for the corresponding AWS CLI command.

### Deploy to AWS

```bash
./deploy.sh out
```

The deploy script is idempotent -- it deletes existing resources and recreates them on each run. It polls async resources (analyses, dashboards) until they reach a terminal state. Requires the AWS CLI v2 and `jq`.

To delete all generated resources without recreating:

```bash
./deploy.sh --delete out
```

You can also deploy manually:

```bash
# DataSource (only present when generated via demo apply)
aws quicksight create-data-source --region us-east-1 --cli-input-json file://out/datasource.json

# Theme
aws quicksight create-theme --region us-east-1 --cli-input-json file://out/theme.json

# Datasets (repeat for each file)
aws quicksight create-data-set --region us-east-1 --cli-input-json file://out/datasets/qs-gen-sales-dataset.json

# Analysis
aws quicksight create-analysis --region us-east-1 --cli-input-json file://out/financial-analysis.json

# Dashboard
aws quicksight create-dashboard --region us-east-1 --cli-input-json file://out/financial-dashboard.json
```

### Demo data

The project includes a demo mode that generates a complete sample dataset themed around sasquatch-run coffee shops in Seattle. This lets you see the reports in action without connecting your own data.

#### Write demo SQL files

```bash
# Write the schema DDL (CREATE TABLE/VIEW/INDEX statements)
quicksight-gen demo schema -o demo/schema.sql

# Write the seed data (INSERT statements with ~200 sales, settlements, payments, etc.)
quicksight-gen demo seed -o demo/seed.sql
```

#### Apply demo data to a PostgreSQL database

```bash
# Add your database URL to config.yaml:
#   demo_database_url: "postgresql://user:pass@localhost:5432/quicksight_demo"

# Apply schema + seed data and generate QuickSight JSON with the Sasquatch Bank theme
quicksight-gen demo apply -c config.yaml -o out
```

The `demo apply` command creates tables, views, and indexes, inserts the sample data, then generates all QuickSight JSON using the `sasquatch-bank` theme preset. It also generates a `datasource.json` file with the QuickSight data source definition derived from the database URL -- no pre-existing `datasource_arn` is needed. Requires `pip install -e ".[demo]"` for the PostgreSQL driver.

Deploy order: datasource -> theme -> datasets -> analysis -> dashboard.

#### What's in the demo data

6 merchants: Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, and Wildman's Roastery. The data includes:

- ~200 sales across franchise, independent, and cart merchant types
- ~35 settlements (daily, weekly, monthly) with completed, pending, and failed statuses
- ~30 payments including 5 returned payments with different return reasons
- ~17 external transactions across 3 systems (BankSync, PaymentHub, ClearSettle)
- Payment reconciliation: matched, not yet matched, and late statuses
- 10 unsettled sales to populate the exceptions tab

#### Theme presets

The `--theme-preset` / `-t` flag on the `generate` command selects a colour palette:

| Preset | Description |
|---|---|
| `default` | Navy/blue/grey financial palette |
| `sasquatch-bank` | Forest green, bark brown, and bank gold -- branded for Sasquatch National Bank |

```bash
quicksight-gen generate -c config.yaml -o out --theme-preset sasquatch-bank
```

The Sasquatch Bank preset also renames the analysis to "Sasquatch National Bank -- Financial Reporting".

### Run tests

```bash
pytest
```

Tests covering model serialization (including data source), tagging, end-to-end generation, cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet ID scoping), payment reconciliation visuals and filters, explanation coverage (every sheet has a description, every visual has a subtitle), theme presets, demo data generation (determinism, row counts, referential integrity, scenario coverage), data source builder, and CLI commands.

## Project structure

```
src/quicksight_gen/
    __init__.py
    __main__.py          # python -m quicksight_gen entry point
    cli.py               # Click CLI (generate, demo schema/seed/apply)
    config.py            # YAML/env config loader (incl. late_threshold_days)
    constants.py         # Sheet IDs and dataset identifier strings
    models.py            # Dataclasses mapping to QuickSight API JSON
    theme.py             # Theme presets (default + sasquatch-bank)
    datasets.py          # 8 custom SQL dataset definitions (6 financial + 2 recon)
    demo_data.py         # Deterministic demo data generator (sasquatch coffee shops)
    visuals.py           # Financial analysis visual builders (Sales, Settlements, Payments, Exceptions)
    filters.py           # Financial analysis filter groups + controls
    analysis.py          # Consolidated analysis assembly (5 tabs incl. Payment Recon)
    recon_visuals.py     # Payment Reconciliation visuals (KPIs, bar chart, dual tables)
    recon_filters.py     # Payment Reconciliation filter groups + controls
demo/
    schema.sql           # PostgreSQL DDL (tables, views, indexes)
tests/
    test_models.py       # Unit tests for models, tags, config, dataset builders
    test_generate.py     # Integration tests: full pipeline, cross-refs, explanations
    test_recon.py        # Unit tests for payment recon visuals and filters
    test_theme_presets.py # Theme preset registry and integration tests
    test_demo_data.py    # Demo data generation (determinism, FKs, scenarios)
    test_demo_sql.py     # Schema/seed SQL structure and CLI tests
config.example.yaml      # Example configuration
deploy.sh                # Idempotent AWS CLI deploy script
```

## How to customise

### Change the SQL queries

Edit `src/quicksight_gen/datasets.py`. Each dataset has a `sql` variable with the query. Replace with your real table and column names. Update the `columns` list to match.

### Add a visual

1. Add a builder function in `src/quicksight_gen/visuals.py` (financial tabs) or `src/quicksight_gen/recon_visuals.py` (Payment Recon tab)
2. Add the visual to the appropriate `build_*_visuals()` return list
3. Add a subtitle explaining what the visual shows (required by tests)
4. Run `pytest` to verify cross-references

### Add a new tab

1. Add a sheet ID constant in `src/quicksight_gen/constants.py`
2. Add a sheet builder function in `src/quicksight_gen/analysis.py`
3. Add the sheet to the `Sheets` list in `_build_financial_definition()`
4. Add a plain-language sheet description (required by tests)
5. Add visuals and filter controls as above
6. If the new tab needs existing filters, add its sheet ID to the relevant scope in `filters.py`

### Change the theme colours

Edit the presets in `src/quicksight_gen/theme.py`. Each `ThemePreset` defines the full colour palette -- accent, secondary background, text colours, data series colours, and UI palette. To add a new preset, create a `ThemePreset` instance and add it to the `PRESETS` registry.

### Add a filter

1. Add a `FilterGroup` builder in `src/quicksight_gen/filters.py` (financial tabs) or `src/quicksight_gen/recon_filters.py` (Payment Recon tab)
2. Add it to the appropriate `build_filter_groups()` or `build_recon_filter_groups()`
3. Add a corresponding `FilterControl` builder
4. Add the control to the relevant `build_*_controls()` functions
5. Run `pytest` to verify the `SourceFilterId` references resolve

### Ask Claude to make changes

This project is designed to be modified conversationally. You can ask Claude to:
- Add new datasets, visuals, tabs, or filters
- Change the theme colours or typography
- Modify the SQL queries for your schema
- Add conditional formatting or sort configurations to visuals
- Restructure the analysis layout
