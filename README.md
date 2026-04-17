# QuickSight Analysis Generator

[![CI](https://github.com/chotchki/Quicksight-Generator/actions/workflows/ci.yml/badge.svg)](https://github.com/chotchki/Quicksight-Generator/actions/workflows/ci.yml)

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analyses, dashboards) and deploys them via boto3. It currently ships two independent QuickSight apps:

- **Payment Reconciliation** — sales → settlements → payments → external-system matching for a merchant bank.
- **Account Reconciliation** — stored daily balances, transfers, and postings for a double-entry ledger.

Both apps share one theme, one AWS account, one datasource, and the same CLI surface (`quicksight-gen generate|deploy|demo|cleanup`). Change the Python (or ask Claude), re-run `deploy --generate`, get a new dashboard.

## Why this exists

The customer for these reports doesn't know exactly what they want yet. Rather than click through the QuickSight console and lose the work when requirements change, everything is generated from code and deployed idempotently (delete-then-create). Iteration is one command.

## The two apps

### Payment Reconciliation — 6 tabs

| Tab | What it shows |
|---|---|
| Getting Started | Landing page — heading + per-sheet highlights; demo scenario block when seeded. |
| Sales Overview | KPIs + by-merchant / by-location bar charts + detail table. |
| Settlements | KPIs + bar by merchant type + detail table. Click a row to drill into Sales. |
| Payments | KPIs + pie by status + detail table. Click a row to drill into Settlements. Right-click `external_transaction_id` to drill into Payment Reconciliation. |
| Exceptions & Alerts | Unsettled sales, returned payments, sale↔settlement and settlement↔payment mismatches, and unmatched external transactions. Compact half-width tables. |
| Payment Reconciliation | KPIs + match-status bar + dual mutually-filterable tables (external transactions ↔ internal payments). Click a row in either to filter the other. |

### Account Reconciliation — 5 tabs

| Tab | What it shows |
|---|---|
| Getting Started | Landing page — heading + per-sheet highlights; demo scenario block when seeded. |
| Balances | Ledger and sub-ledger account balance tables. Click an account to drill into its transactions. |
| Transfers | One row per `transfer_id` with net-zero flags. Click to drill into transactions. |
| Transactions | Raw ledger (one row per leg, with an `origin` tag for later filtering), filtered by date / type / Show-Only-Failed. |
| Exceptions | Five independent checks side-by-side: ledger drift, sub-ledger drift, non-zero transfers, daily limit breaches, sub-ledger overdrafts. Two drift timelines at the bottom. |

### Shared conventions

- **Clickable cells look clickable.** Accent-colored text = left-click drill; accent text on a pale tint background = right-click menu drill.
- Every sheet has a plain-language description; every visual has a subtitle. Coverage is asserted in unit + API e2e tests.
- All resources tagged `ManagedBy: quicksight-gen`; extra tags via `extra_tags` in config.

## Quick start

### Prerequisites

- Python 3.11+
- An AWS account with QuickSight Enterprise enabled
- Either a pre-existing QuickSight datasource ARN **or** a PostgreSQL database URL for demo mode

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

```yaml
aws_account_id: "123456789012"
aws_region: "us-east-2"

# Pre-existing QuickSight datasource ARN.
# Not required when demo_database_url is set (auto-derived).
datasource_arn: "arn:aws:quicksight:us-east-2:123456789012:datasource/your-datasource-id"

# Optional: prefix for all generated resource IDs (default: qs-gen)
resource_prefix: "qs-gen"

# Optional: which theme preset to use. One of: default, sasquatch-bank, farmers-exchange-bank
theme_preset: "default"

# Optional: IAM principals granted permissions on generated resources.
# Accepts a single string or a list; one ResourcePermission is emitted per entry.
principal_arns:
  - "arn:aws:quicksight:us-east-1:123456789012:user/default/admin"

# Optional: default value for any "late" / "days outstanding" filter (default: 30)
late_default_days: 30

# Optional: additional tags on every generated resource
extra_tags:
  Environment: production
  Team: finance

# Optional: PostgreSQL URL for demo apply
# demo_database_url: "postgresql://user:pass@localhost:5432/quicksight_demo"
```

All values can also be set via `QS_GEN_`-prefixed environment variables (e.g. `QS_GEN_AWS_ACCOUNT_ID`). Env vars override YAML.

### Generate and deploy

```bash
# Generate both apps' JSON
quicksight-gen generate --all -c config.yaml -o out/

# Deploy everything (delete-then-create, idempotent)
quicksight-gen deploy --all -c config.yaml -o out/

# Or combine: regenerate + deploy in one shot (typical iteration loop)
quicksight-gen deploy --all --generate -c config.yaml -o out/

# Deploy a single app
quicksight-gen generate payment-recon -c config.yaml -o out/
quicksight-gen deploy  payment-recon -c config.yaml -o out/
```

`deploy` polls async resources (analyses, dashboards) until they reach a terminal state. Resources with the `ManagedBy: quicksight-gen` tag that aren't in the current output aren't touched — clean those up explicitly:

```bash
quicksight-gen cleanup --dry-run       # list stale tagged resources
quicksight-gen cleanup --yes           # delete them without prompting
```

### What you get

```
out/
  theme.json
  payment-recon-analysis.json
  payment-recon-dashboard.json
  account-recon-analysis.json
  account-recon-dashboard.json
  datasource.json                        # demo apply only
  datasets/
    qs-gen-merchants-dataset.json              # 11 PR datasets
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
    qs-gen-ar-ledger-accounts-dataset.json     # 9 AR datasets
    qs-gen-ar-subledger-accounts-dataset.json
    qs-gen-ar-transactions-dataset.json
    qs-gen-ar-ledger-balance-drift-dataset.json
    qs-gen-ar-subledger-balance-drift-dataset.json
    qs-gen-ar-transfer-summary-dataset.json
    qs-gen-ar-non-zero-transfers-dataset.json
    qs-gen-ar-limit-breach-dataset.json
    qs-gen-ar-overdraft-dataset.json
```

## Demo mode

A deterministic demo generator seeds both apps end-to-end so you can see them work without wiring up real data.

```bash
# Emit SQL only (no DB connection needed)
quicksight-gen demo schema --all -o demo/schema.sql
quicksight-gen demo seed   --all -o demo/seed.sql

# Apply schema + seed to PostgreSQL, then generate QuickSight JSON
# Requires: demo_database_url in config.yaml and `pip install -e ".[demo]"`
quicksight-gen demo apply --all -c config.yaml -o out/
```

`demo apply` creates tables + views, inserts the sample data, writes a `datasource.json` derived from the database URL, and generates all QuickSight JSON. Both apps share one Postgres schema; Payment Recon tables use the `pr_` prefix, Account Recon tables use `ar_`.

Datasets are all Direct Query (no SPICE), so seed changes show up immediately after a fresh `demo apply` — no refresh step needed.

### Demo scenarios

- **Payment Recon — Sasquatch National Bank.** Six fictional Seattle coffee shops (Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, Wildman's Roastery). Sales flow into settlements and payments; planted unsettled sales, returned payments, amount mismatches, and orphan external transactions populate every exception table.
- **Account Recon — Farmers Exchange Bank.** Five ledger accounts (Big Meadow Checking, Harvest Moon Savings, Orchard Lending Pool, Valley Grain Co-op, Harvest Credit Exchange) move money between ten sub-ledger accounts over ~40 days using four transfer types. Disjoint planted drift, failed legs, limit breaches, and overdrafts keep every Exceptions table populated.

## Theming

| Preset | Palette | Analysis name prefix |
|---|---|---|
| `default` | Navy / blue / grey | — |
| `sasquatch-bank` | Forest green + bark brown + bank gold | `Demo — ` |
| `farmers-exchange-bank` | Valley green + harvest gold + earth | `Demo — ` |

Set `theme_preset:` in `config.yaml` (or pass `--theme-preset` to `generate` / `deploy --generate`). Add a new preset by declaring a `ThemePreset` in `src/quicksight_gen/common/theme.py` and registering it in `PRESETS`.

Rich-text on the Getting Started sheets (headings, bullets, hyperlinks) uses the preset's accent color, resolved to hex at generate time.

## Project structure

```
src/quicksight_gen/
    __main__.py         # python -m quicksight_gen entry point
    cli.py              # Click CLI — generate / deploy / cleanup / demo
    common/
        config.py       # Config dataclass + YAML/env loader
        models.py       # Dataclasses mapping to QuickSight API JSON
        theme.py        # Theme presets (default, sasquatch-bank, farmers-exchange-bank)
        deploy.py       # Python deploy (delete-then-create, async waiters)
        cleanup.py      # Tag-based cleanup of stale resources
        clickability.py # Conditional-format helpers (plain + menu-link accent styles)
        rich_text.py    # XML helpers for SheetTextBox.Content (heading/bullets/…)
    payment_recon/
        analysis.py     # 6 sheets, drill-downs, filter groups, dashboard
        visuals.py      # Sales / Settlements / Payments / Exceptions visuals
        recon_visuals.py# Payment Reconciliation side-by-side tables + KPIs
        filters.py      # Pipeline-tab filter groups + controls
        recon_filters.py# Payment Reconciliation filters
        datasets.py     # 11 custom-SQL datasets
        demo_data.py    # Sasquatch Bank demo data generator
        constants.py    # Sheet + dataset identifier constants
    account_recon/
        analysis.py     # 5 sheets, drill-downs, filter groups, dashboard
        visuals.py      # Balances / Transfers / Transactions / Exceptions visuals
        filters.py      # Per-tab filters + Show-Only-X toggles
        datasets.py     # 9 custom-SQL datasets
        demo_data.py    # Farmers Exchange Bank demo data generator
        constants.py    # Sheet + dataset identifier constants
demo/
    schema.sql          # Full PostgreSQL DDL (both apps)
tests/
    test_models.py, test_generate.py, test_recon.py, test_account_recon.py,
    test_theme_presets.py, test_demo_data.py, test_demo_sql.py
    e2e/                # Two-layer e2e (API + browser); skipped unless QS_GEN_E2E=1
run_e2e.sh              # One-shot: generate + deploy + e2e
config.example.yaml
```

## Tests

```bash
pytest                  # unit + integration (fast, no AWS)
./run_e2e.sh            # regenerate + deploy both apps + e2e (pytest-xdist -n 4)
./run_e2e.sh --parallel 8            # override worker count (1 = serial; stable ceiling ~8)
./run_e2e.sh --skip-deploy api       # only API e2e
./run_e2e.sh --skip-deploy browser   # only browser e2e
```

Coverage:

- **Unit / integration (254 tests)**: models, tags, config, CLI, demo determinism + FK integrity + scenario coverage, theme preset registry, dataset builders, visual builders, filter groups, cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet scoping), explanation coverage, schema + seed SQL structure.
- **E2E (75 tests)**: two layers gated by `QS_GEN_E2E=1`.
  - *API layer (boto3)* — resource existence, status, dashboard structure, dataset import health.
  - *Browser layer (Playwright WebKit, headless)* — dashboard loads via pre-authenticated embed URL, sheet tabs, per-sheet visual counts, drill-downs, mutual-filter reconciliation tables, date-range filter narrowing, Show-Only-X toggles.

E2E tunables (env vars): `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT`, `QS_E2E_USER_ARN`, `QS_E2E_IDENTITY_REGION`. Failure screenshots land in `tests/e2e/screenshots/<app>/` (gitignored).

## Known limitations

### Drill-down parameters stack across tab-switches

QuickSight has no API to clear a parameter on tab-switch. When a drill-down sets a parameter on its destination sheet (e.g. clicking a `settlement_id` on Settlements navigates to Sales and sets `pSettlementId`), the parameter stays set even after the user tabs away and back — the destination sheet stays filtered to that one value.

**Workaround:** refresh the dashboard tab in the browser to clear all parameter filters.

Captured as an `xfail(strict=False)` characterization test in `tests/e2e/test_filter_stacking.py` so the behavior is documented and would surface if AWS ever fixes it.

## Customising

### Change the SQL

Edit the dataset builders in `<app>/datasets.py`. Each dataset has a `sql` string and a `columns` list — swap in your real schema.

### Add a visual or tab

1. Add the builder function in `<app>/visuals.py`.
2. Wire it into the sheet layout in `<app>/analysis.py`.
3. Add a subtitle (coverage tests enforce this).
4. Run `pytest`.

### Add a filter

1. Add the `FilterGroup` builder in `<app>/filters.py` (or `recon_filters.py` for PR).
2. Add a matching `FilterControl`.
3. Register it on the relevant sheet's `FilterControls` in `analysis.py`.
4. `pytest` will flag any broken `SourceFilterId` references.

### Add a theme preset

Declare a `ThemePreset` in `common/theme.py` and add it to the `PRESETS` dict. Set `analysis_name_prefix="Demo"` if it should tag analyses with a demo prefix.

### Ask Claude

The codebase is intentionally easy to mutate. Ask Claude to add visuals, reshape the layout, adjust filters, update SQL for your schema, or add conditional formatting — it'll edit the Python and re-run tests.
