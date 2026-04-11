# QuickSight Analysis Generator

## Overview

Python project that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analysis) importable via the AWS CLI. Designed for easy mutation — change Python code or ask Claude to adjust, re-run, get new JSON.

## Implementation Plan

### Step 1: Project scaffolding
- Create Python project structure with `pyproject.toml` and `src/quicksight_gen/` package
- Pin Python >= 3.11, add `boto3-stubs[quicksight]` for type hints and `click` for CLI
- Create a `__main__.py` entry point so the tool can run as `python -m quicksight_gen`
- Dependencies: none

### Step 2: QuickSight model layer
- Build Python dataclasses (or Pydantic models) that map to the QuickSight API structures we need to generate: `Theme`, `DataSet`, `Analysis`, `Sheet`, `Visual`, `FilterControl`, `FilterGroup`, `ColumnSchema`
- These models must serialize to the exact JSON shape the AWS CLI expects for `create-theme`, `create-data-set`, and `create-analysis`
- Include a `to_aws_json()` method on each top-level model
- Dependencies: Step 1

### Step 3: Configuration / datasource reference
- Create a config module that accepts the pre-existing DataSource ARN, AWS account ID, and AWS region as inputs (env vars, CLI args, or a small YAML/JSON config file)
- All generated resources will reference this datasource
- Dependencies: Step 1

### Step 4: Theme definition (blues and greys)
- Define a QuickSight theme using the model layer with a blue/grey palette
- Primary: dark blue for headers/titles, medium blue for accents/chart bars
- Secondary: greys for backgrounds, grid lines, secondary text
- Ensure high contrast for readability (dark text on light backgrounds)
- Apply font sizing rules: titles >= 16px, body >= 12px
- Dependencies: Step 2

### Step 5: Dataset definitions with custom SQL
Create datasets with placeholder SQL queries for each domain area. Each dataset is a separate QuickSight `DataSet` resource referencing the configured datasource.

- **5a — Merchants dataset**: merchant ID, name, type, location ID. Placeholder SQL.
- **5b — Sales dataset**: sale ID, merchant ID, location ID, amount, timestamp, metadata columns. Placeholder SQL.
- **5c — Settlements dataset**: settlement ID, merchant ID, settlement type, amount, date, status. Placeholder SQL.
- **5d — Payments dataset**: payment ID, settlement ID, merchant ID, amount, date, status, return flag/reason. Placeholder SQL.
- **5e — Settlement exceptions dataset**: query joining sales to settlements to find unsettled sales. Placeholder SQL.
- **5f — Payment returns dataset**: query filtering payments with returned status. Placeholder SQL.
- Dependencies: Step 2, Step 3

### Step 6: Analysis shell with sheets (tabs)
Define the top-level Analysis resource containing four sheets:

- **Tab 1 — Sales Overview**: sales volume and amounts across merchants/locations
- **Tab 2 — Settlements**: settlement status, amounts, breakdown by merchant type
- **Tab 3 — Payments**: payment status, amounts, returned payments
- **Tab 4 — Exceptions & Alerts**: unsettled sales, returned payments, anomalies

Apply the theme from Step 4. Each sheet is empty at this point — visuals come next.
- Dependencies: Step 2, Step 4

### Step 7: Visuals for each tab
Populate each sheet with visuals. All visuals use the theme and reference the datasets from Step 5.

- **7a — Sales Overview visuals**:
  - KPI: total sales count, total sales amount (today / this week / this month)
  - Bar chart: sales amount by merchant
  - Bar chart: sales amount by location
  - Table: recent sales detail (sortable)
  - Dependencies: Step 5a, 5b, Step 6

- **7b — Settlements visuals**:
  - KPI: total settled amount, count of pending settlements
  - Bar chart: settlement amounts by merchant type
  - Table: settlement detail with status column
  - Dependencies: Step 5c, Step 6

- **7c — Payments visuals**:
  - KPI: total paid amount, count of returned payments
  - Pie chart: payment status breakdown
  - Table: payment detail with return reason column
  - Dependencies: Step 5d, Step 6

- **7d — Exceptions & Alerts visuals**:
  - Table: sales missing settlements (from 5e)
  - Table: returned payments detail (from 5f)
  - KPI: count of unsettled sales, count of returned payments
  - Dependencies: Step 5e, 5f, Step 6

### Step 8: Controls and filters
Add interactive controls to the analysis, bound to filter groups that apply across visuals on each sheet:

- Date range picker (applies to all tabs)
- Merchant dropdown (applies to all tabs)
- Location dropdown (applies to all tabs)
- Settlement status dropdown (Settlements and Exceptions tabs)
- Payment status dropdown (Payments tab)
- Dependencies: Step 7 (all sub-steps)

### Step 9: JSON export and CLI script
- Implement the `__main__.py` CLI using `click`:
  - `generate` command: reads config, builds all models, writes JSON files to an output directory (`out/theme.json`, `out/datasets/*.json`, `out/analysis.json`)
  - `deploy` command (optional/stretch): wraps `aws quicksight create-*` CLI calls to import the generated JSON
- Each JSON file is a standalone payload ready for the corresponding AWS CLI command
- Include a shell script or Makefile with example `aws quicksight` commands for manual import
- Dependencies: Step 8, Step 3

### Step 10: Validation and testing
- Add unit tests that verify each model serializes to valid JSON matching the AWS API schema
- Add a smoke test that runs the full `generate` command and checks output files exist and parse as valid JSON
- Validate that all cross-references (dataset ARNs in visuals, theme ARN in analysis, filter-to-visual bindings) are consistent
- Dependencies: Step 9

## Dependency Graph

```
Step 1 (scaffolding)
├── Step 2 (model layer)
│   ├── Step 3 (config) ──────────────────────────────┐
│   ├── Step 4 (theme) ───────────────────────┐       │
│   │                                         │       │
│   ├── Step 5a-5f (datasets) ←───────────────┼───────┘
│   │       │                                 │
│   └── Step 6 (analysis shell + sheets) ←────┘
│               │
│           Step 7a-7d (visuals) ←── Step 5a-5f
│               │
│           Step 8 (controls/filters)
│               │
│           Step 9 (JSON export + CLI) ←── Step 3
│               │
│           Step 10 (tests)
```

## Conventions
- All generated QuickSight resource IDs use kebab-case with a `qs-gen-` prefix (e.g., `qs-gen-sales-dataset`)
- Python code uses type hints throughout
- One module per concern: `models.py`, `theme.py`, `datasets.py`, `analysis.py`, `config.py`, `cli.py`
