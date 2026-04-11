# QuickSight Analysis Generator

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, two analyses) importable via the AWS CLI. Designed for easy mutation — change Python code or ask Claude to adjust, re-run, get new JSON.

## Quick Reference

- **Language**: Python 3.11+ (3.13 in use)
- **Package manager**: pip / setuptools, venv at `.venv/`
- **Entry point**: `python -m quicksight_gen` or `quicksight-gen` (installed script)
- **CLI framework**: Click
- **Output**: JSON files in `out/` (datasource [demo only], theme, datasets, two analyses)

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

# Run tests
pytest
```

## Generated Output

```
out/
  datasource.json             # QuickSight data source (demo apply only)
  theme.json                  # Shared blue/grey theme
  financial-analysis.json     # Sales → Settlements → Payments pipeline
  recon-analysis.json         # Reconciliation against external systems
  datasets/
    qs-gen-merchants-dataset.json
    qs-gen-sales-dataset.json
    qs-gen-settlements-dataset.json
    qs-gen-payments-dataset.json
    qs-gen-settlement-exceptions-dataset.json
    qs-gen-payment-returns-dataset.json
    qs-gen-external-transactions-dataset.json
    qs-gen-sales-recon-dataset.json
    qs-gen-settlement-recon-dataset.json
    qs-gen-payment-recon-dataset.json
    qs-gen-recon-exceptions-dataset.json
```

## Project Structure

```
src/quicksight_gen/
  __main__.py        # Entry point (delegates to cli.main)
  cli.py             # Click CLI: generate, demo schema/seed/apply
  config.py          # Config dataclass, loads from YAML or env vars
  constants.py       # Shared sheet IDs and dataset identifier constants
  models.py          # Dataclasses mapping to QuickSight API JSON structures
  theme.py           # Theme presets (default blue/grey + sasquatch-bank green/gold)
  datasets.py        # All dataset definitions (financial + reconciliation)
  demo_data.py       # Deterministic demo data generator (sasquatch coffee shops)
  analysis.py        # Financial analysis: 4 tabs (Sales, Settlements, Payments, Exceptions)
  visuals.py         # Visual definitions for financial analysis tabs
  filters.py         # Filter groups and controls for financial analysis
  recon_analysis.py  # Reconciliation analysis: 4 tabs (Overview, Sales/Settlement/Payment Recon)
  recon_visuals.py   # Visual definitions for reconciliation analysis tabs
  recon_filters.py   # Filter groups and controls for reconciliation analysis
demo/
  schema.sql         # PostgreSQL DDL for demo database (tables, views, indexes)
tests/
  test_models.py     # Unit tests for models, tags, config, dataset builders
  test_generate.py   # Integration tests: full pipeline, cross-refs, explanations
  test_recon.py      # Unit tests for recon visuals and filters
  test_theme_presets.py  # Theme preset registry, serialization, analysis name integration
  test_demo_data.py      # Demo data determinism, row counts, FK integrity, scenarios
  test_demo_sql.py       # Schema/seed SQL structure, CLI command tests
```

## Domain Model

### Financial Pipeline
**Merchants -> Sales -> Settlements -> Payments**

- Merchants make sales at locations
- Sales are bundled into settlements (settlement type depends on merchant type)
- Settlements are paid to merchants
- Key concerns: unsettled sales (exceptions) and returned payments

### Reconciliation
**Internal Records <-> External System Transactions**

- Multiple external systems aggregate sales/settlements/payments into transactions (all accessed through the single configured datasource)
- A match is valid only when the external transaction total exactly equals the sum of internal records — no partial matches
- Match statuses: **matched**, **not_yet_matched**, **late**
- "Late" has a type-specific static threshold (e.g., sales late after N days, settlements after M days) — displayed in QuickSight but not editable
- The `days_outstanding` column and slider filter let users focus on the most overdue items

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
- One module per concern; recon modules mirror financial modules (`analysis.py`/`recon_analysis.py`, etc.)
- Theme presets: `default` (blue/grey) and `sasquatch-bank` (forest green/bank gold); add new presets to the `PRESETS` dict in `theme.py`
- Default theme: blues and greys, high contrast, titles >= 16px, body >= 12px
- The end customer doesn't know exactly what they want — keep the code easy to mutate and iterate on
