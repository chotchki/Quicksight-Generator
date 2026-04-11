# QuickSight Analysis Generator

A Python tool that programmatically generates AWS QuickSight JSON definitions for financial reporting and reconciliation. It outputs standalone JSON files that can be imported directly via the AWS CLI.

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

### Reconciliation datasets (5)

| File | Description |
|---|---|
| `out/datasets/qs-gen-external-transactions-dataset.json` | External system transaction aggregations |
| `out/datasets/qs-gen-sales-recon-dataset.json` | Sales matched against external transactions |
| `out/datasets/qs-gen-settlement-recon-dataset.json` | Settlements matched against external transactions |
| `out/datasets/qs-gen-payment-recon-dataset.json` | Payments matched against external transactions |
| `out/datasets/qs-gen-recon-exceptions-dataset.json` | Cross-type reconciliation exceptions |

### Financial Analysis (`out/financial-analysis.json`)

4 tabs, 18 visuals, 5 filter groups, 15 controls.

- **Sales Overview** -- KPIs (count, amount), bar charts (by merchant, by location), sales detail table
- **Settlements** -- KPIs (settled amount, pending count), bar chart (by merchant type), settlement detail table
- **Payments** -- KPIs (paid amount, returned count), pie chart (status breakdown), payment detail table
- **Exceptions & Alerts** -- KPIs (unsettled sales, returned payments), unsettled sales table, returned payments table

All tabs have date range, merchant, and location filters. The Settlements and Exceptions tabs add a settlement status filter. The Payments tab adds a payment status filter.

### Reconciliation Analysis (`out/recon-analysis.json`)

4 tabs, 18 visuals, 6 filter groups, per-sheet controls including a days-outstanding slider.

- **Reconciliation Overview** -- KPIs (matched, pending, late counts), pie chart (status breakdown), bar charts (by type, by external system)
- **Sales Reconciliation** -- KPIs (matched, unmatched), bar chart (by merchant), detail table with match status and difference
- **Settlement Reconciliation** -- same layout as Sales Recon for settlement records
- **Payment Reconciliation** -- same layout as Sales Recon for payment records

All tabs have date range, match status, external system, merchant, and days-outstanding filters. The Overview tab adds a transaction type filter.

### Tags and explanations

All generated resources are tagged with `ManagedBy: quicksight-gen` (additional tags configurable via `extra_tags` in config). Every sheet has a plain-language description and every visual has a subtitle explaining what it shows.

## Quick start

### Prerequisites

- Python 3.11+
- An AWS account with QuickSight Enterprise enabled
- A pre-existing QuickSight datasource connected to your SQL database

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
datasource_arn: "arn:aws:quicksight:us-east-1:123456789012:datasource/your-datasource-id"

# Optional: prefix for generated resource IDs (default: qs-gen)
resource_prefix: "qs-gen"

# Optional: IAM principal to grant permissions on all generated resources
principal_arn: "arn:aws:quicksight:us-east-1:123456789012:user/default/admin"

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

This writes 14 JSON files to `out/` (1 theme, 11 datasets, 2 analyses). Each file is a standalone payload ready for the corresponding AWS CLI command.

### Deploy to AWS

```bash
./deploy.sh out
```

The deploy script is idempotent -- it creates resources on first run and updates them on subsequent runs. It requires the AWS CLI v2 and `jq`.

You can also deploy manually:

```bash
# Theme
aws quicksight create-theme --region us-east-1 --cli-input-json file://out/theme.json

# Datasets (repeat for each file)
aws quicksight create-data-set --region us-east-1 --cli-input-json file://out/datasets/qs-gen-sales-dataset.json

# Analyses
aws quicksight create-analysis --region us-east-1 --cli-input-json file://out/financial-analysis.json
aws quicksight create-analysis --region us-east-1 --cli-input-json file://out/recon-analysis.json
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

The `demo apply` command creates tables, views, and indexes, inserts the sample data, then generates all QuickSight JSON using the `sasquatch-bank` theme preset. Requires `pip install -e ".[demo]"` for the PostgreSQL driver.

#### What's in the demo data

6 merchants: Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, and Wildman's Roastery. The data includes:

- ~200 sales across franchise, independent, and cart merchant types
- ~35 settlements (daily, weekly, monthly) with completed, pending, and failed statuses
- ~30 payments including 5 returned payments with different return reasons
- ~60 external transactions across 3 systems (SquarePay, BankSync, TaxCloud)
- Reconciliation statuses: matched, not yet matched, and late
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

The Sasquatch Bank preset also renames the analyses to "Sasquatch National Bank -- Financial Reporting" and "Sasquatch National Bank -- Reconciliation".

### Run tests

```bash
pytest
```

131 tests covering model serialization, tagging, end-to-end generation, cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet ID scoping), reconciliation visuals and filters, explanation coverage (every sheet has a description, every visual has a subtitle), theme presets, demo data generation (determinism, row counts, referential integrity, scenario coverage), and CLI commands.

## Project structure

```
src/quicksight_gen/
    __init__.py
    __main__.py          # python -m quicksight_gen entry point
    cli.py               # Click CLI (generate, demo schema/seed/apply)
    config.py            # YAML/env config loader
    constants.py         # Sheet IDs and dataset identifier strings
    models.py            # Dataclasses mapping to QuickSight API JSON
    theme.py             # Theme presets (default + sasquatch-bank)
    datasets.py          # 11 custom SQL dataset definitions (financial + recon)
    demo_data.py         # Deterministic demo data generator (sasquatch coffee shops)
    visuals.py           # Financial analysis visual builders
    filters.py           # Financial analysis filter groups + controls
    analysis.py          # Financial analysis assembly (4 tabs)
    recon_visuals.py     # Reconciliation analysis visual builders
    recon_filters.py     # Reconciliation analysis filter groups + controls
    recon_analysis.py    # Reconciliation analysis assembly (4 tabs)
demo/
    schema.sql           # PostgreSQL DDL (tables, views, indexes)
tests/
    test_models.py       # Unit tests for models, tags, config, dataset builders
    test_generate.py     # Integration tests: full pipeline, cross-refs, explanations
    test_recon.py        # Unit tests for recon visuals and filters
    test_theme_presets.py # Theme preset registry and integration tests
    test_demo_data.py    # Demo data generation (determinism, FKs, scenarios)
    test_demo_sql.py     # Schema/seed SQL structure and CLI tests
config.example.yaml      # Example configuration
deploy.sh                # Idempotent AWS CLI deploy script
```

## How to customise

### Change the SQL queries

Edit `src/quicksight_gen/datasets.py`. Each dataset has a `sql` variable with a placeholder query. Replace with your real table and column names. Update the `columns` list to match.

### Add a visual

1. Add a builder function in `src/quicksight_gen/visuals.py` (financial) or `src/quicksight_gen/recon_visuals.py` (reconciliation)
2. Add the visual to the appropriate `build_*_visuals()` return list
3. Add a subtitle explaining what the visual shows (required by tests)
4. Run `pytest` to verify cross-references

### Add a new tab

1. Add a sheet ID constant in `src/quicksight_gen/constants.py`
2. Add a sheet builder function in `src/quicksight_gen/analysis.py` or `src/quicksight_gen/recon_analysis.py`
3. Add the sheet to the `Sheets` list in `build_analysis()` or `build_recon_analysis()`
4. Add a plain-language sheet description (required by tests)
5. Add visuals and filter controls as above
6. If the new tab needs existing filters, add its sheet ID to the relevant scope in `filters.py` or `recon_filters.py`

### Change the theme colours

Edit the presets in `src/quicksight_gen/theme.py`. Each `ThemePreset` defines the full colour palette -- accent, secondary background, text colours, data series colours, and UI palette. To add a new preset, create a `ThemePreset` instance and add it to the `PRESETS` registry.

### Add a filter

1. Add a `FilterGroup` builder in `src/quicksight_gen/filters.py` (financial) or `src/quicksight_gen/recon_filters.py` (reconciliation)
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
