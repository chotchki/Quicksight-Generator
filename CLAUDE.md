# QuickSight Analysis Generator

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analysis) importable via the AWS CLI. Designed for easy mutation — change Python code or ask Claude to adjust, re-run, get new JSON.

## Quick Reference

- **Language**: Python 3.11+ (3.13 in use)
- **Package manager**: pip / setuptools, venv at `.venv/`
- **Entry point**: `python -m quicksight_gen` or `quicksight-gen` (installed script)
- **CLI framework**: Click
- **Output**: JSON files in `out/` (theme, datasets, analysis)

## Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Generate all JSON
quicksight-gen generate -c config.yaml -o out/

# Run tests
pytest
```

## Project Structure

```
src/quicksight_gen/
  __main__.py    # Entry point (delegates to cli.main)
  cli.py         # Click CLI: generate command writes JSON to out/
  config.py      # Config dataclass, loads from YAML or env vars
  constants.py   # Shared constants
  models.py      # Dataclasses mapping to QuickSight API JSON structures
  theme.py       # Blue/grey theme definition
  datasets.py    # Custom SQL dataset definitions (merchants, sales, settlements, payments, exceptions, returns)
  analysis.py    # Analysis shell with 4 tabs
  visuals.py     # Visual definitions for each tab
  filters.py     # Interactive controls and filter groups
tests/
  test_models.py
  test_generate.py
```

## Domain Model

Financial application flow: **Merchants -> Sales -> Settlements -> Payments**

- Merchants make sales at locations
- Sales are bundled into settlements (settlement type depends on merchant type)
- Settlements are paid to merchants
- Key concerns: unsettled sales (exceptions) and returned payments

## Architecture Decisions

- All models use Python dataclasses with `to_aws_json()` methods that produce the exact dict shape for AWS CLI `create-theme`, `create-data-set`, `create-analysis`
- Helper `_strip_nones()` recursively cleans None values from serialized output
- Config accepts a pre-existing DataSource ARN — this project does not create datasources
- Datasets use custom SQL with placeholder queries
- Generated resource IDs use kebab-case with a configurable prefix (default `qs-gen-`)

## Conventions

- Type hints throughout
- One module per concern
- Theme: blues and greys, high contrast, titles >= 16px, body >= 12px
- The end customer doesn't know exactly what they want — keep the code easy to mutate and iterate on
