# QuickSight Analysis Generator

A Python tool that programmatically generates AWS QuickSight JSON definitions for financial reporting. It outputs standalone JSON files that can be imported directly via the AWS CLI.

## Why this exists

The customer for these reports doesn't know exactly what they want yet. Rather than clicking through the QuickSight console to build analyses by hand (and losing that work when requirements change), this project generates everything from code. Change the Python, re-run, get new JSON. You can also ask Claude to modify the reports for you.

## What it generates

| Resource | File | Description |
|---|---|---|
| Theme | `out/theme.json` | Blue/grey colour palette, high-contrast readability |
| Merchants dataset | `out/datasets/qs-gen-merchants-dataset.json` | Merchant ID, name, type, location |
| Sales dataset | `out/datasets/qs-gen-sales-dataset.json` | Sale details with amount, timestamp, card info |
| Settlements dataset | `out/datasets/qs-gen-settlements-dataset.json` | Settlement status, type, amounts |
| Payments dataset | `out/datasets/qs-gen-payments-dataset.json` | Payment status, return flag/reason |
| Settlement exceptions | `out/datasets/qs-gen-settlement-exceptions-dataset.json` | Sales missing settlements (LEFT JOIN) |
| Payment returns | `out/datasets/qs-gen-payment-returns-dataset.json` | Returned payments detail |
| Analysis | `out/analysis.json` | 4-tab analysis with 17 visuals, 5 filter groups, 15 controls |

### Analysis tabs

- **Sales Overview** -- KPIs (count, amount), bar charts (by merchant, by location), sales detail table
- **Settlements** -- KPIs (settled amount, pending count), bar chart (by merchant type), settlement detail table
- **Payments** -- KPIs (paid amount, returned count), pie chart (status breakdown), payment detail table
- **Exceptions & Alerts** -- KPIs (unsettled sales, returned payments), unsettled sales table, returned payments table

### Filters

All tabs have date range, merchant, and location filters. The Settlements and Exceptions tabs add a settlement status filter. The Payments tab adds a payment status filter.

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
```

All values can also be set via environment variables with a `QS_GEN_` prefix (e.g. `QS_GEN_AWS_ACCOUNT_ID`). Environment variables override the YAML file.

### Generate JSON

```bash
python -m quicksight_gen generate -c config.yaml -o out
```

This writes 8 JSON files to `out/`. Each file is a standalone payload ready for the corresponding AWS CLI command.

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

# Analysis
aws quicksight create-analysis --region us-east-1 --cli-input-json file://out/analysis.json
```

### Run tests

```bash
pytest
```

26 tests covering model serialization, end-to-end generation, and cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet ID scoping).

## Project structure

```
src/quicksight_gen/
    __init__.py
    __main__.py          # python -m quicksight_gen entry point
    cli.py               # Click CLI (generate command)
    config.py            # YAML/env config loader
    constants.py         # Sheet IDs and dataset identifier strings
    models.py            # Dataclasses mapping to QuickSight API JSON
    theme.py             # Blue/grey theme definition
    datasets.py          # 6 custom SQL dataset definitions
    visuals.py           # 17 visual builders (KPI, bar, pie, table)
    filters.py           # 5 filter groups + per-sheet controls
    analysis.py          # Top-level analysis assembly
tests/
    test_models.py       # Unit tests for model serialization
    test_generate.py     # Smoke + cross-reference validation tests
config.example.yaml      # Example configuration
deploy.sh                # Idempotent AWS CLI deploy script
```

## How to customise

### Change the SQL queries

Edit `src/quicksight_gen/datasets.py`. Each dataset has a `sql` variable with a placeholder query. Replace with your real table and column names. Update the `columns` list to match.

### Add a visual

1. Add a builder function in `src/quicksight_gen/visuals.py` (see existing ones for the pattern)
2. Add the visual to the appropriate `build_*_visuals()` return list
3. Run `pytest` to verify cross-references

### Add a new tab

1. Add a sheet ID constant in `src/quicksight_gen/constants.py`
2. Add a sheet builder function in `src/quicksight_gen/analysis.py`
3. Add the sheet to the `Sheets` list in `build_analysis()`
4. Add visuals and filter controls as above
5. If the new tab needs existing filters, add its sheet ID to the relevant scope in `src/quicksight_gen/filters.py`

### Change the theme colours

Edit the colour constants at the top of `src/quicksight_gen/theme.py`. The `DATA_COLOURS` list controls chart series colours. The `UIColorPalette` section controls backgrounds, text, and semantic colours.

### Add a filter

1. Add a `FilterGroup` builder in `src/quicksight_gen/filters.py`
2. Add it to `build_filter_groups()`
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
