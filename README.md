# QuickSight Analysis Generator

[![CI](https://github.com/chotchki/Quicksight-Generator/actions/workflows/ci.yml/badge.svg)](https://github.com/chotchki/Quicksight-Generator/actions/workflows/ci.yml)
[![Coverage](https://raw.githubusercontent.com/chotchki/Quicksight-Generator/badges/coverage-badge.svg)](https://github.com/chotchki/Quicksight-Generator/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/quicksight-gen.svg)](https://pypi.org/project/quicksight-gen/)

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analyses, dashboards) and deploys them via boto3. It currently ships five independent QuickSight apps:

- **L1 Reconciliation Dashboard** — generic L1 SHOULD-constraint surface (drift / overdraft / limit breach / expected EOD balance / stuck pending / stuck unbundled, plus supersession audit). 11 sheets. Configured by an **L2 instance YAML** rather than per-app code — the same dashboard renders against any institution that declares its accounts / rails / templates / chains / limit schedules in L2 form. The newest app (M.2b); the L2-fed pattern is the recommended path for new integrators.
- **Payment Reconciliation** — sales → settlements → payments → external-system matching for a merchant bank.
- **Account Reconciliation** — stored daily balances, transfers, and postings for a double-entry ledger.
- **Investigation** — compliance / AML triage: recipient fanout, volume anomalies, money-trail provenance, and account-network graphs over the shared base ledger.
- **Executives** — board-cadence statistics: account coverage (open vs active), transaction volume over time, money moved (gross + net) over time. Reads only the shared base tables — no Executives-specific schema.

All five apps share one theme registry, one AWS account, one datasource, and the same CLI surface (`quicksight-gen generate|deploy|demo|cleanup`). Change the Python (or ask Claude), re-run `deploy --generate`, get a new dashboard.

## Demo Docs

The demo ships with four task-shaped handbooks, one per persona team at Sasquatch National Bank. Deployed to GitHub Pages at **[chotchki.github.io/Quicksight-Generator](https://chotchki.github.io/Quicksight-Generator/)**.

- **[L1 Reconciliation Dashboard](https://chotchki.github.io/Quicksight-Generator/handbook/l1/)** — the generic L2-fed dashboard. 11 sheets covering 5 baseline L1 invariants + 2 aging-watch invariants + supersession audit + per-account-day walk + raw posting ledger. Switch the L2 instance to switch the persona prose without touching dashboard code.
- **[GL Reconciliation Handbook](https://chotchki.github.io/Quicksight-Generator/handbook/ar/)** — how the Accounting Operations team works the AR Exceptions sheet. Morning rollups + per-check drill-downs for 17 exception classes.
- **[Payment Reconciliation Handbook](https://chotchki.github.io/Quicksight-Generator/handbook/pr/)** — how the Merchant Support team answers "where's my money?" calls. 7 walkthroughs organized by operator question.
- **[Investigation Handbook](https://chotchki.github.io/Quicksight-Generator/handbook/investigation/)** — how the Compliance / Investigation team triages AML cases. 4 walkthroughs, one per sheet's question — the app is question-shaped rather than pipeline-staged or rotation-driven.
- **[Data Integration Handbook](https://chotchki.github.io/Quicksight-Generator/handbook/etl/)** — how the Data Integration Team maps an upstream system into `transactions` + `daily_balances`, validates the load, and extends the metadata contract. 5 foundational / extension / debug walkthroughs.

Source lives in `src/quicksight_gen/docs/` (shipped with the wheel — extract with `quicksight-gen export docs -o ./somewhere/`); rebuild locally with `mkdocs serve`.

## Why this exists

The customer for these reports doesn't know exactly what they want yet. Rather than click through the QuickSight console and lose the work when requirements change, everything is generated from code and deployed idempotently (delete-then-create). Iteration is one command.

## The five apps

### L1 Reconciliation Dashboard — 11 tabs

The newest app and the recommended path for new integrators. Configured by an L2 instance YAML — declare your institution once (accounts, rails, transfer templates, chains, limit schedules, per-rail aging caps), and the same dashboard renders against you. Switching the L2 instance switches the prose on every TextBox without touching dashboard code.

| Tab | What it shows |
|---|---|
| Getting Started | Welcome + L2 coverage inventory (account counts, rail counts, etc) — both pulled from the L2 instance's prose. |
| Drift | Leaf + parent account balance drift detail tables. Right-click any row → Daily Statement for that account-day. |
| Drift Timelines | KPI for largest single-day drift + 2 LineCharts (one line per `account_role`) tracking Σ ABS(drift) over the visible date range. |
| Overdraft | KPI + violations table for internal accounts holding negative money at EOD. Right-click → Daily Statement. |
| Limit Breach | KPI + per-(account, day, transfer_type) breach table. Caps inlined from L2 LimitSchedules at schema-emit time. |
| Pending Aging | Stuck-Pending transactions past their rail's `max_pending_age`. KPI + 5-bucket horizontal aging bar (`0-6h`, `6-24h`, `1-3d`, `3-7d`, `>7d`) + detail. Right-click → Transactions. |
| Unbundled Aging | Posted legs with `bundle_id IS NULL` past their rail's `max_unbundled_age`. Same KPI + bar + detail shape with 4 day-scale buckets. |
| Supersession Audit | Logical keys with multiple `entry` versions — the rewrite trail (Inflight / BundleAssignment / TechnicalCorrection). Reads from BASE tables (not Current*) since Current* hides the audit-relevant prior entries. |
| Today's Exceptions | UNION across all 5 baseline invariant views scoped to the most recent business day. KPI + by-check bar + detail sorted by magnitude. Drill-source for the canonical analyst journey. |
| Daily Statement | Per-account-day walk: 5 KPIs (Opening / Debits / Credits / Closing / Drift) + every Money record posted that day. Right-click any leg → Transactions filtered to that transfer. |
| Transactions | Raw posting ledger (`<prefix>_current_transactions` matview — supersession-aware). 5 dropdown filters for analyst-driven slicing. |

Reads from per-instance `<prefix>_*` views/matviews emitted by `common.l2.emit_schema(instance)`. See [L1 Invariants](https://chotchki.github.io/Quicksight-Generator/L1_Invariants/) for the per-view contract + SHOULD-constraint motivation.

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
| Transactions | Raw ledger (one row per leg, with an `origin` tag for filtering), filtered by date / type / posting-level / origin / Show-Only-Failed. |
| Exceptions | Cross-check rollups at the top (expected-zero EOD, two-sided post mismatch, balance-drift timelines), then per-check details: ledger / sub-ledger drift, non-zero transfers, limit breaches, overdrafts, and seven Cash Management Suite checks (ZBA sweep, ACH origination non-zero EOD, missing Fed confirmations, force-posted card without internal catch-up, GL-vs-Fed Master drift, stuck-in-suspense, reversed-but-not-credited). Aging bars on every check. |

### Investigation — 5 tabs

| Tab | What it shows |
|---|---|
| Getting Started | Landing page — heading + roadmap of the four question-shaped sheets below. |
| Recipient Fanout | Who is receiving money from too many distinct senders? 3 KPIs (qualifying recipients / distinct senders / total inbound) + ranked table; threshold slider sets where "too many" starts. |
| Volume Anomalies | Which sender → recipient pair just spiked above its rolling baseline? Backed by `inv_pair_rolling_anomalies` matview (rolling 2-day SUM per pair + population z-score). KPI flagged-pair count + σ distribution chart + ranked table; σ slider gates KPI + table while the chart shows the full population. |
| Money Trail | Where did this transfer originate, and where does it go? Backed by `inv_money_trail_edges` matview (recursive `WITH RECURSIVE` walk over `parent_transfer_id` flattened to one row per multi-leg edge). Sankey as the headline + hop-by-hop table beside it; chain-root dropdown + max-hops + min-hop-amount controls. |
| Account Network | What does this account's money network look like, on either side? Same matview, account-anchored. Two side-by-side directional Sankeys (inbound on the left, outbound on the right, anchor visually meeting in the middle) + touching-edges table. Walk-the-flow drill: right-click any table row or left-click any Sankey node to walk the anchor to the counterparty and re-render around the new center. |

### Executives — 4 tabs

Greenfield app built on the typed tree primitives — board-cadence rollups over the shared `transactions` + `daily_balances` base tables, no Executives-specific schema.

| Tab | What it shows |
|---|---|
| Getting Started | Landing page — heading + per-sheet highlights. |
| Account Coverage | Open vs Active account KPIs + bar chart by `account_type` + detail table. The Active KPI + Active bar carry a visual-pinned `activity_count >= 1` filter so they read as "accounts that moved money in the period" while the Open KPI/bar count every row — same dataset, different scope. |
| Transaction Volume Over Time | Total transfers + average daily KPIs + daily stacked bar by `transfer_type` + per-type bar. Per-transfer pre-aggregation (`WITH per_transfer AS`) collapses multi-leg transfers so a 2-leg $100 movement counts as one $100 transfer, not two $200. |
| Money Moved | Gross + net amount KPIs + daily stacked bar by `transfer_type` + per-type bar. Same per-transfer pre-aggregation; net = inflows − outflows from the bank's perspective. |

### Shared conventions

- **Clickable cells look clickable.** Accent-colored text = left-click drill; accent text on a pale tint background = right-click menu drill.
- Every sheet has a plain-language description; every visual has a subtitle. Coverage is asserted in unit + API e2e tests.
- All resources tagged `ManagedBy: quicksight-gen`; extra tags via `extra_tags` in config.

## Quick start

### Prerequisites

- Python 3.12+
- An AWS account with QuickSight Enterprise enabled
- Either a pre-existing QuickSight datasource ARN **or** a PostgreSQL **17+** database URL for demo mode (the schema uses SQL/JSON path syntax)

### Install from PyPI

For consumers — using a pre-existing QuickSight datasource ARN:

```bash
pip install quicksight-gen
```

For demo mode (Postgres 17+, requires `psycopg2-binary`):

```bash
pip install "quicksight-gen[demo]"
```

### Setup from source

For development on this repo:

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

# Optional: which theme preset to use. One of: default, sasquatch-bank,
# sasquatch-bank-investigation
theme_preset: "default"

# Optional: IAM principals granted permissions on generated resources.
# Accepts a single string or a list; one ResourcePermission is emitted per entry.
principal_arns:
  - "arn:aws:quicksight:us-east-1:123456789012:user/default/admin"

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
# Generate all four apps' JSON
quicksight-gen generate --all -c config.yaml -o out/

# Deploy everything (delete-then-create, idempotent)
quicksight-gen deploy --all -c config.yaml -o out/

# Or combine: regenerate + deploy in one shot (typical iteration loop)
quicksight-gen deploy --all --generate -c config.yaml -o out/

# Deploy a single app
quicksight-gen generate payment-recon  -c config.yaml -o out/
quicksight-gen generate account-recon  -c config.yaml -o out/
quicksight-gen generate investigation  -c config.yaml -o out/
quicksight-gen generate executives     -c config.yaml -o out/
quicksight-gen deploy   payment-recon  -c config.yaml -o out/
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
  investigation-analysis.json
  investigation-dashboard.json
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
    qs-gen-ar-ledger-accounts-dataset.json     # 21 AR datasets
    qs-gen-ar-subledger-accounts-dataset.json
    qs-gen-ar-transactions-dataset.json
    qs-gen-ar-ledger-balance-drift-dataset.json
    qs-gen-ar-subledger-balance-drift-dataset.json
    qs-gen-ar-transfer-summary-dataset.json
    qs-gen-ar-non-zero-transfers-dataset.json
    qs-gen-ar-limit-breach-dataset.json
    qs-gen-ar-overdraft-dataset.json
    qs-gen-ar-sweep-target-nonzero-dataset.json
    qs-gen-ar-concentration-master-sweep-drift-dataset.json
    qs-gen-ar-ach-orig-settlement-nonzero-dataset.json
    qs-gen-ar-ach-sweep-no-fed-confirmation-dataset.json
    qs-gen-ar-fed-card-no-internal-catchup-dataset.json
    qs-gen-ar-gl-vs-fed-master-drift-dataset.json
    qs-gen-ar-internal-transfer-stuck-dataset.json
    qs-gen-ar-internal-transfer-suspense-nonzero-dataset.json
    qs-gen-ar-internal-reversal-uncredited-dataset.json
    qs-gen-ar-expected-zero-eod-rollup-dataset.json
    qs-gen-ar-two-sided-post-mismatch-rollup-dataset.json
    qs-gen-ar-balance-drift-timelines-rollup-dataset.json
    qs-gen-inv-recipient-fanout-dataset.json   # 5 Investigation datasets
    qs-gen-inv-volume-anomalies-dataset.json
    qs-gen-inv-money-trail-dataset.json
    qs-gen-inv-account-network-dataset.json
    qs-gen-inv-anetwork-accounts-dataset.json
```

## Demo mode

A deterministic demo generator seeds all four apps end-to-end so you can see them work without wiring up real data. Investigation and Executives both ride on the shared `transactions` + `daily_balances` base tables — no app-specific schema; the existing PR + AR + Investigation scenario seeds already plant enough movement that Executives' rollups (account coverage, daily transfer volume, money moved) populate without a separate seed.

```bash
# Apply schema + seed to PostgreSQL, then generate QuickSight JSON.
# Requires: demo_database_url in config.yaml and `pip install -e ".[demo]"`.
# Per-prefix DDL + seed are emitted at apply time from the L2 instance
# YAML — no separate `demo schema` / `demo seed` files (those CLI
# commands were retired in P.1 along with the v5 schema.sql).
quicksight-gen demo apply --all -c config.yaml -o out/
```

`demo apply` creates the per-prefix base tables + matviews, inserts the L2-shape seed data (every L1 SHOULD-violation kind plus the Investigation fanout plant), refreshes every dependent matview in dependency order, writes a `datasource.json` derived from the database URL, and generates all QuickSight JSON. Every app feeds two per-prefix base tables — `<prefix>_transactions` (every money-movement leg) and `<prefix>_daily_balances` (per-account end-of-day snapshots) — emitted by `common/l2/schema.py::emit_schema(l2_instance)`. The `account_type` and `transfer_type` columns discriminate which app a row belongs to. See [`Schema_v6.md`](src/quicksight_gen/docs/Schema_v6.md) for the full feed contract, canonical type values, metadata key catalog, and ETL examples.

**PostgreSQL 17+ is required** for `demo apply`: the schema uses SQL/JSON path syntax (`JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`) for the `metadata TEXT` columns, and the portable subset forbids the Postgres-only `->>` / `->` / `@>` / `?` operators and JSONB.

Datasets are all Direct Query (no SPICE), so seed changes show up immediately after a fresh `demo apply` — no refresh step needed.

### Demo scenarios

- **Payment Recon — Sasquatch National Bank (merchant settlement).** Six fictional Seattle coffee shops (Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., Cryptid Coffee Cart, Wildman's Roastery). Sales flow into settlements and payments; planted unsettled sales, returned payments, amount mismatches, and orphan external transactions populate every exception table.
- **Account Recon — Sasquatch National Bank (treasury / GL).** Same bank from the treasury side, after SNB absorbed Farmers Exchange Bank's commercial book. Eight internal GL control accounts (Cash & Due From FRB, ACH Origination Settlement, Card Acquiring Settlement, Wire Settlement Suspense, Internal Transfer Suspense, Cash Concentration Master, Internal Suspense / Reconciliation, Customer Deposits — DDA Control) plus per-customer DDAs for three coffee retailers (Bigfoot Brews, Sasquatch Sips, Yeti Espresso) and four commercial customers (Cascade Timber Mill, Pinecrest Vineyards, Big Meadow Dairy, Harvest Moon Bakery). The Cash Management Suite drives four telling-transfer flows — ZBA / Cash Concentration sweeps, daily ACH origination sweeps to the FRB Master Account, external force-posted card settlements, and on-us internal transfers through Internal Transfer Suspense. Each flow plants both success cycles and characteristic failures so every Exceptions check (including the cross-check rollups) surfaces distinct rows.
- **Investigation — Sasquatch National Bank (compliance / AML).** Three converging scenarios on a single anchor account, **Juniper Ridge LLC**, so every Investigation sheet has a non-empty answer and the sheets connect: a fanout cluster (12 individual depositors × 2 ACH transfers each → Juniper, drives Recipient Fanout past the default 5-sender threshold), an anomaly pair (Cascadia Trust Bank — Operations wires Juniper $300–$700 routine amounts for 8 days then a single $25,000 spike, drives Volume Anomalies past the default 2σ threshold), and a 4-hop layering chain (Cascadia → Juniper → Shell A → Shell B → Shell C with $250 residue per hop, drives Money Trail with a non-trivial Sankey). Account Network anchored on Juniper shows the full picture — depositor inbounds on the left, shell outbounds on the right.
- **Executives — Sasquatch National Bank (board / leadership cadence).** No new seed data — Executives is a roll-up of every successful transfer the PR / AR / Investigation seeds already plant. Account Coverage compares "open" (every account that exists) against "active" (`activity_count >= 1` in the period); Transaction Volume Over Time and Money Moved chart daily / per-type rollups. The mix of `merchant_dda` (PR coffee retailers), `dda` (AR commercial customers), `external_counter` (FRB Master, processors, individual depositors), and `gl_control` rows shows up directly in the per-type bars.

## Theming

| Preset | Palette | Analysis name prefix |
|---|---|---|
| `default` | Navy / blue / grey | — |
| `sasquatch-bank` | Forest green + bark brown + bank gold | `Demo — ` |
| `sasquatch-bank-investigation` | Slate blue + amber alert | `Demo — ` |

Set `theme_preset:` in `config.yaml` (or pass `--theme-preset` to `generate` / `deploy --generate`). Add a new preset by declaring a `ThemePreset` in `src/quicksight_gen/common/theme.py` and registering it in `PRESETS`.

Rich-text on the Getting Started sheets (headings, bullets, hyperlinks) uses the preset's accent color, resolved to hex at generate time.

## Project structure

```
src/quicksight_gen/
    __main__.py         # python -m quicksight_gen entry point
    cli.py              # Click CLI — generate / deploy / cleanup / demo / export
    common/
        config.py       # Config dataclass + YAML/env loader
        models.py       # Dataclasses mapping to QuickSight API JSON
        ids.py          # Typed ID newtypes (SheetId / VisualId / FilterGroupId / ParameterName)
        theme.py        # Theme presets (default, sasquatch-bank, sasquatch-bank-investigation)
        persona.py      # DemoPersona — single source of truth for whitelabel-substitutable Sasquatch strings
        deploy.py       # Python deploy (delete-then-create, async waiters)
        cleanup.py      # Tag-based cleanup of stale resources
        dataset_contract.py  # ColumnSpec / DatasetContract / build_dataset()
        drill.py        # Cross-app deep-link URL builder
        clickability.py # Conditional-format helpers
        rich_text.py    # XML helpers for SheetTextBox.Content
        tree/           # Typed tree primitives (Phase L). App / Analysis / Dashboard / Sheet, typed Visual subtypes (KPI / Table / BarChart / Sankey), typed Filter wrappers (CategoryFilter / NumericRangeFilter / TimeRangeFilter), Parameter + Filter Controls, Drill actions, Datasets + Columns + Dim/Measure factories, CalcFields. Object-ref cross-references (visuals → datasets, filter groups → visuals, drills → sheets); auto-IDs at emit time for internal IDs; emit-time validation walks. All four apps are tree-built — see CLAUDE.md "Tree pattern" for the L1 / L2 / L3 layer model.
    apps/
        payment_recon/  # app.py (6 sheets), datasets.py (11 datasets), demo_data.py, constants.py
        account_recon/  # app.py (5 sheets), datasets.py (13 datasets), demo_data.py, constants.py
        investigation/  # app.py (5 sheets), datasets.py (5 datasets — 2 backed by matviews), constants.py
        executives/     # app.py (4 sheets), datasets.py (2 datasets, per-transfer pre-aggregated). Greenfield on tree primitives — no constants.py.
    docs/               # Unified mkdocs site source — concepts/, reference (handbook/), walkthroughs/, for-your-role/, scenarios/, Schema_v6.md, Training_Story.md, _diagrams/, _macros/ (extract via `quicksight-gen export docs`). Renders against any L2 instance via mkdocs-macros + HandbookVocabulary.
tests/
    test_models.py, test_generate.py, test_investigation.py, test_executives.py,
    test_tree.py, test_tree_validator.py, test_kitchen_app.py, test_persona.py,
    test_drill.py, test_dataset_contract.py, test_theme_presets.py, test_export.py, ...
    e2e/                # Two-layer e2e (API + browser) for all four apps; skipped unless QS_GEN_E2E=1
run_e2e.sh              # One-shot: generate + deploy + e2e
config.example.yaml
```

## Tests

```bash
pytest                  # unit + integration (fast, no AWS)
./run_e2e.sh            # regenerate + deploy all four apps + e2e (pytest-xdist -n 4)
./run_e2e.sh --parallel 8            # override worker count (1 = serial; stable ceiling ~8)
./run_e2e.sh --skip-deploy api       # only API e2e
./run_e2e.sh --skip-deploy browser   # only browser e2e
```

Coverage:

- **Unit / integration**: models, tags, config, CLI, demo determinism + FK integrity + scenario coverage (per-app SHA256 seed-hash locks), theme preset registry, dataset builders, visual builders, filter groups, cross-reference validation (dataset ARNs, filter bindings, visual ID uniqueness, sheet scoping), explanation coverage, schema + seed SQL structure.
- **E2E**: two layers gated by `QS_GEN_E2E=1`.
  - *API layer (boto3)* — resource existence, status, dashboard structure (per-sheet visual counts, parameter / filter-group source-of-truth checks), dataset import health.
  - *Browser layer (Playwright WebKit, headless)* — dashboard loads via pre-authenticated embed URL, sheet tabs, per-sheet visual counts + spot-checked titles, drill-downs, mutual-filter reconciliation tables, date-range filter narrowing, Show-Only-X toggles, Investigation slider + dropdown filters.

E2E tunables (env vars): `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT`, `QS_E2E_USER_ARN`, `QS_E2E_IDENTITY_REGION`. Failure screenshots land in `tests/e2e/screenshots/<app>/` (gitignored).

## Known limitations

### Drill-down parameters stack across tab-switches

QuickSight has no API to clear a parameter on tab-switch. When a drill-down sets a parameter on its destination sheet (e.g. clicking a `settlement_id` on Settlements navigates to Sales and sets `pSettlementId`), the parameter stays set even after the user tabs away and back — the destination sheet stays filtered to that one value.

**Workaround:** refresh the dashboard tab in the browser to clear all parameter filters.

Captured as an `xfail(strict=False)` characterization test in `tests/e2e/test_filter_stacking.py` so the behavior is documented and would surface if AWS ever fixes it.

## Customising

### Change the SQL

Edit the dataset builders in `<app>/datasets.py`. Each dataset has a `sql` string and a `DatasetContract` (column name + type list) — unit tests assert the SQL projection matches the contract, so the contract is the safety net when rewriting.

The dataset SQL reads from two shared base tables (`transactions`, `daily_balances`) plus the AR-only dimension tables. To wire your production data in, ETL into the same shape: see [`Schema_v6.md`](src/quicksight_gen/docs/Schema_v6.md) for column specifications, the canonical `account_type` / `transfer_type` values, the JSON metadata key catalog, and end-to-end ETL examples.

### Add a visual or tab

1. Open `apps/<app>/app.py` and find the relevant sheet's populator function (e.g. `_populate_account_coverage`).
2. Place the visual on a layout row: `row.add_kpi(...)`, `row.add_table(...)`, `row.add_bar_chart(...)`, `row.add_sankey(...)`. Pass `title=`, `subtitle=`, and the typed `Dim`/`Measure` slots — the tree validates dataset / column references at emit time.
3. Subtitle is required (coverage tests enforce this).
4. Run `pytest` — typed cross-reference errors fail at the wiring site, not deep in the generated JSON.

### Add a filter

1. In `apps/<app>/app.py`, build a `FilterGroup`: `fg = FilterGroup.with_category_filter(...)` (or `with_numeric_range_filter` / `with_time_range_filter`). Pass the typed `Dim` ref directly — no string IDs.
2. Scope it: `fg.scope_sheet(sheet_obj)` for sheet-wide; `fg.scope_visuals(visual_a, visual_b)` for visual-pinned.
3. For UI controls, attach the filter's `default_control` to a sheet via `sheet.filter_controls.append(...)`.
4. `pytest` walks the tree and flags missing references at emit time.

### Add a theme preset

Declare a `ThemePreset` in `common/theme.py` and add it to the `PRESETS` dict. Set `analysis_name_prefix="Demo"` if it should tag analyses with a demo prefix.

### Ask Claude

The codebase is intentionally easy to mutate. Ask Claude to add visuals, reshape the layout, adjust filters, update SQL for your schema, or add conditional formatting — it'll edit the Python and re-run tests.
