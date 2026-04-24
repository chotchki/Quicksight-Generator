# QuickSight Analysis Generator

Python tool that programmatically generates AWS QuickSight JSON definitions (theme, datasets, analyses, dashboards) and deploys them via boto3. Ships **three independent QuickSight apps** sharing one theme registry, account, datasource, and CLI surface:

- **Payment Reconciliation** — 6 sheets: Getting Started, Sales, Settlements, Payments, Exceptions, Payment Reconciliation
- **Account Reconciliation** — 5 sheets: Getting Started, Balances, Transfers, Transactions, Exceptions
- **Investigation** — 5 sheets: Getting Started, Recipient Fanout, Volume Anomalies, Money Trail, Account Network

The customer doesn't know exactly what they want yet. Everything is generated from code and deployed idempotently (delete-then-create) so a change is one command to roll out.

## Quick Reference

- **Language**: Python 3.12+ (3.13 in use). 3.12 minimum is for PEP 695 generic syntax used in `common/tree.py`.
- **Package manager**: pip / setuptools, venv at `.venv/`
- **Entry point**: `python -m quicksight_gen` or `quicksight-gen` (installed script)
- **CLI framework**: Click
- **Output**: JSON files in `out/` (theme, per-app analysis/dashboard, datasets, optional datasource)

## Commands

```bash
# Install dependencies (add [demo] for `demo apply`, which needs psycopg2)
pip install -e ".[dev]"
pip install -e ".[demo]"

# Generate all JSON (all three apps, one theme)
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
# (schema ships with the wheel — `demo schema` writes a copy out for inspection.)
quicksight-gen demo schema --all -o /tmp/schema.sql
quicksight-gen demo seed   --all -o /tmp/seed.sql
quicksight-gen demo apply  --all -c config.yaml -o out/

# Tests
pytest                              # unit + integration, fast, no AWS
./run_e2e.sh                        # regenerate + deploy all three apps + e2e (pytest-xdist -n 4)
./run_e2e.sh --parallel 8           # override worker count (1 = serial; stable ceiling ~8)
./run_e2e.sh --skip-deploy api      # API e2e only
./run_e2e.sh --skip-deploy browser  # browser e2e only
```

`demo apply` is app-scoped: `demo apply payment-recon` generates with the `sasquatch-bank` preset; `demo apply account-recon` uses `sasquatch-bank-ar`; `demo apply investigation` uses `sasquatch-bank-investigation`; `--all` generates all three with each app's natural preset. Schema is always loaded in full — all three apps feed the same `transactions` + `daily_balances` base tables, plus AR-only dimension tables (`ar_ledger_accounts`, `ar_subledger_accounts`, `ar_ledger_transfer_limits`). Investigation reads the shared base tables only — no investigation-specific schema.

## Generated Output

```
out/
  datasource.json                     # demo apply only
  theme.json                          # one shared theme
  payment-recon-analysis.json
  payment-recon-dashboard.json
  account-recon-analysis.json
  account-recon-dashboard.json
  investigation-analysis.json
  investigation-dashboard.json
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
    qs-gen-inv-recipient-fanout-dataset.json                 # 5 Investigation datasets
    qs-gen-inv-volume-anomalies-dataset.json
    qs-gen-inv-money-trail-dataset.json
    qs-gen-inv-account-network-dataset.json
    qs-gen-inv-anetwork-accounts-dataset.json                # narrow dropdown source
```

`generate` (single app) prunes stale dataset JSON belonging to neither of the other two apps — so renaming or dropping a dataset doesn't leave an orphan that `deploy` would re-create. The other apps' dataset files are preserved.

## Project Structure

```
src/quicksight_gen/
  __main__.py            # Entry point (delegates to cli.main)
  cli.py                 # Click CLI: generate / deploy / cleanup / demo / export (all with --all or app arg)
  common/
    config.py            # Config dataclass + YAML/env loader (principal_arns list, theme_preset)
    models.py            # Dataclasses mapping to QuickSight API JSON (to_aws_json + _strip_nones)
    ids.py               # Typed ID newtypes (SheetId / VisualId / FilterGroupId / ParameterName / etc.)
    theme.py             # Theme presets (default / sasquatch-bank / sasquatch-bank-ar / sasquatch-bank-investigation); PRESETS registry
    persona.py           # DemoPersona dataclass + derive_mapping_yaml_text — single source of truth for whitelabel-substitutable Sasquatch strings
    deploy.py            # boto3 delete-then-create deploy with async waiters
    cleanup.py           # Tag-based cleanup of stale resources (ManagedBy:quicksight-gen)
    dataset_contract.py  # ColumnSpec, DatasetContract, build_dataset() — shared dataset constructor
    drill.py             # Cross-app deep-link URL builder (CustomActionURLOperation)
    clickability.py      # Conditional-format helpers: accent text (left-click) + tint-background (right-click)
    aging.py             # Shared aging_bar_visual() — horizontal bar chart by aging bucket
    rich_text.py         # XML composition helpers for SheetTextBox.Content (heading/bullets/link/inline)
    tree/                # Phase L typed tree primitives — see "Tree pattern" in Architecture Decisions
      structure.py         # App / Analysis / Dashboard / Sheet — top-level tree nodes + emit + validation
      visuals.py           # KPI / Table / BarChart / Sankey / TextBox typed Visual subtypes
      filters.py           # CategoryFilter / NumericRangeFilter / TimeRangeFilter + FilterGroup
      controls.py          # FilterDropdown / FilterSlider / FilterDateTimePicker / FilterCrossSheet + Parameter equivalents
      parameters.py        # StringParameter / IntegerParameter / DecimalParameter / DatetimeParameter declarations
      calc_fields.py       # CalcField — analysis-level calculated fields (typed; auto-named from tree position)
      datasets.py          # Dataset + Column tree nodes; ds["col"].dim() / .sum() / .date() chained factories
      fields.py            # Dim / Measure typed wrappers (validated against dataset contract)
      actions.py           # Drill / NavigateAction typed actions; cross-sheet target as Sheet object ref
      formatting.py        # Conditional-format primitives (color / icon / tint) used by visuals
      text_boxes.py        # SheetTextBox content helpers
      _helpers.py          # AutoSentinel + position-indexed ID resolver (visual_id / action_id / etc.)
  apps/
    payment_recon/
      app.py               # Tree-built: 6 sheets, drill-downs, filter groups, dashboard
      datasets.py          # 11 custom-SQL datasets
      demo_data.py         # Sasquatch National Bank demo generator
      etl_examples.py      # ETL shape examples (PR-flavored)
      constants.py         # SheetId / FilterGroupId / ParameterName + dataset identifiers
    account_recon/
      app.py               # Tree-built: 5 sheets, drill-downs, filter groups, dashboard
      datasets.py          # 13 custom-SQL datasets (7 baseline + 1 unified-exceptions + 3 cross-check rollups + 2 daily-statement)
      demo_data.py         # Sasquatch National Bank — CMS treasury demo generator
      etl_examples.py      # ETL shape examples (AR-flavored)
      constants.py         # SheetId / FilterGroupId / ParameterName + dataset identifiers
    investigation/
      app.py               # Tree-built: 5 sheets — Getting Started + Recipient Fanout / Volume Anomalies / Money Trail / Account Network
      datasets.py          # 5 custom-SQL datasets — fanout + anomalies (matview) + money trail (matview) + account network (matview wrapper) + accounts dropdown source
      demo_data.py         # Sasquatch Bank — Compliance / AML demo (12-depositor fanout + Cascadia $25K spike + 4-hop layering chain)
      etl_examples.py      # placeholder (no app-specific ETL keys; PR/AR examples cover the shape)
      constants.py         # SheetId / FilterGroupId / ParameterName (no VisualId — auto-derived per L.1.16)
    executives/
      app.py               # Tree-built: 4 sheets — Getting Started + Account Coverage + Transaction Volume + Money Moved (greenfield on L.1 primitives — no constants.py)
      datasets.py          # 2 custom-SQL datasets — exec_transaction_summary (per-transfer pre-aggregated) + exec_account_summary
  schema.py              # `generate_schema_sql()` — reads the canonical DDL from the package data file
  schema.sql             # Full PostgreSQL DDL — shared `transactions` + `daily_balances` base layer + AR dimension tables + AR + Investigation matviews
  docs/                  # mkdocs site source (handbook/, walkthroughs/, Schema_v3.md, Training_Story.md); extract via `quicksight-gen export docs`
  training/              # Whitelabel handbook kit (handbook/, mapping.yaml.example, QUICKSTART.md); extract via `quicksight-gen export training`
tests/
  test_models.py         # Models, tags, config, dataset builders
  test_generate.py       # Full pipeline, cross-refs, explanations (PR)
  test_account_recon.py  # AR visuals, filters, datasets, analysis wiring
  test_recon.py          # Payment recon visuals + filters
  test_investigation.py  # Investigation visuals + filters + datasets + matview SQL + sheet wiring + walk-the-flow drill shape + demo scenario coverage
  test_executives.py     # Executives sheets, datasets, filters, CLI smoke (4 sheets, 2 datasets — greenfield app)
  test_tree.py           # common/tree primitives — emit/validation walks, object-ref cross-references, auto-ID resolution
  test_tree_validator.py # tests/e2e/tree_validator.py walker unit tests
  test_kitchen_app.py    # Kitchen-sink app exercising every L.1 primitive
  test_screenshot_harness.py # tests/e2e/screenshot_harness.py walker unit tests
  test_drill.py          # Cross-app URL deep-link builder tests
  test_persona.py        # DemoPersona round-trip + mapping.yaml derivation parity
  test_export.py         # `export docs` / `export training` CLI tests
  test_theme_presets.py  # Preset registry, serialization, analysis name integration
  test_dataset_contract.py # DatasetContract basics + per-builder column-match assertions
  test_demo_data.py      # Demo determinism (SHA256 hash lock), row counts, FK integrity, scenario coverage, cross-app integrity, shared base layer projection
  test_demo_sql.py       # Schema/seed SQL structure, CLI command tests
  test_demo_etl_examples.py # ETL example demo coverage
  test_etl_examples.py   # ETL example shape tests
  test_deploy.py         # Deploy delete-then-create + waiter logic
  e2e/                   # Two layers (API boto3 + browser Playwright WebKit); gated on QS_GEN_E2E=1
    conftest.py
    browser_helpers.py
    tree_validator.py             # TreeValidator(app, page).validate_structure() — typed walker that derives expected DOM from the tree
    screenshot_harness.py         # Typed walker that drives screenshot capture from tree positions
    _kitchen_app.py               # Shared kitchen-sink app fixture for tree-validator + screenshot-harness tests
    test_deployed_resources.py    / test_ar_deployed_resources.py    / test_inv_deployed_resources.py    / test_exec_deployed_resources.py
    test_dashboard_structure.py   / test_ar_dashboard_structure.py   / test_inv_dashboard_structure.py   / test_exec_dashboard_structure.py
    test_dataset_health.py        / test_ar_dataset_health.py
    test_dashboard_renders.py     / test_ar_dashboard_renders.py     / test_inv_dashboard_renders.py     / test_exec_dashboard_renders.py
    test_sheet_visuals.py         / test_ar_sheet_visuals.py         / test_inv_sheet_visuals.py         / test_exec_sheet_visuals.py
    test_drilldown.py             / test_ar_drilldown.py             / test_inv_drilldown.py
    test_state_toggles.py         / test_ar_state_toggles.py
    test_filters.py               / test_ar_filters.py               / test_inv_filters.py
    test_pr_kpi_semantics.py      / test_ar_kpi_semantics.py         / test_ar_daily_statement.py        / test_ar_todays_exc_drill.py
    test_ar_cross_visibility.py   / test_ar_cross_sheet_param_hygiene.py
    test_recon_mutual_filter.py   / test_filter_stacking.py
scripts/
  screenshot_getting_started.py   # Ad-hoc: screenshot both Getting Started tabs
  screenshot_daily_statement.py
  generate_walkthrough_screenshots.py
  bake_sample_output.py
run_e2e.sh
```

## Domain Model

### Shared base layer (v3.0.0)

All three apps feed two base tables. PR + AR + Investigation share the same physical schema; the `account_type` column discriminates which app a row belongs to (Investigation reads `dda` + `external_counter` rows by way of its planted scenario subset). See `docs/Schema_v3.md` for the full feed contract.

- **`transactions`** — one row per money-movement leg. Carries `transaction_id` PK, `transfer_id` (groups legs of one financial event), `parent_transfer_id` (chains transfers — used by PR for `external_txn → payment → settlement → sale`), `transfer_type`, `origin`, `account_id`, denormalized account fields (`account_name`, `account_type`, `control_account_id`, `is_internal`), `signed_amount` (positive = money IN to the account, negative = money OUT), `amount` (absolute), `status`, `posted_at`, `balance_date`, `external_system`, `memo`, and a `metadata TEXT` column constrained `IS JSON` for app-specific keys (`card_brand`, `cashier`, `settlement_type`, etc.). Non-failed legs of a non-single-leg transfer net to zero.
- **`daily_balances`** — one row per `(account_id, balance_date)`. Carries the same denormalized account fields as `transactions` plus `balance` (stored end-of-day) and a `metadata TEXT` JSON column (used by AR to attach per-day limit configuration so the limit-breach view stays a single SELECT).

**Sign convention.** `signed_amount > 0` = money IN to the account; `signed_amount < 0` = money OUT; `daily_balances.balance = SUM(signed_amount)` over the account's history (the drift-check invariant). Applies to every `account_type` including `merchant_dda` — sales credit (positive), payments debit (negative). `Schema_v3.md` states the same rule from the bank's bookkeeping perspective ("+= debit, −= credit"); both are the same rule read from opposite ends of the double-entry, and the code uses the account-holder view everywhere.

Six canonical `account_type` values: `gl_control` (AR GL control accounts), `dda` (AR customer demand-deposit accounts), `merchant_dda` (PR merchant accounts), `external_counter` (FRB Master, processors, PR external customer pool / external rail), `concentration_master` (the cash concentration target), `funds_pool` (reserved; not currently emitted by the demo seed). `control_account_id` is a self-referential FK; PR sub-ledger accounts roll up to the synthetic `pr-merchant-ledger` control row.

JSON metadata uses portable SQL/JSON path syntax (`JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`) — no JSONB, no `->>` / `->` / `@>` / `?` operators, no GIN indexes on JSON. PostgreSQL 17+ required for `demo apply`. AR computed views (`ar_computed_ledger_daily_balance`, `ar_subledger_overdraft`, `ar_subledger_daily_outbound_by_type`, etc.) read from these two base tables and the AR-only dimension tables.

The legacy 12-table family (`pr_*`, `transfer`, `posting`, `ar_*_daily_balances`) was dropped in Phase G.10 and never recreated — `DROP TABLE IF EXISTS` lines remain in `schema.sql` for upgrade safety.

### Payment Reconciliation
**Merchants → Sales → Settlements → Payments → External Transactions**

- Merchants make sales at locations
- Sales bundle into settlements (settlement type depends on merchant type)
- Settlements get paid to merchants as payments
- Payments leave the internal system, so only payments reconcile against external systems
- Multiple external systems (BankSync, PaymentHub, ClearSettle) aggregate 1+ internal payments into one external transaction
- Match is valid only when external total exactly equals sum of linked payments — no partials
- Match statuses: **matched**, **not_yet_matched**, **late** (data-driven: `late` ↔ `CURRENT_TIMESTAMP > COALESCE(expected_complete_at, posted_at + INTERVAL '1 day')`; the per-row `is_late` column carries the same predicate as a `'Late'` / `'On Time'` label)
- Mutual table filtering on the Payment Reconciliation tab: clicking an external txn filters its payments; clicking a payment filters back
- All 5 PR exception checks and the Payment Recon tab carry `aging_bucket` (same 5-band pattern as AR) with aging bar charts
- **Transfer chain** (parent → child): `external_txn → payment → settlement → sale`, linked by `parent_transfer_id` in `transactions`. PR account rows in `transactions` / `daily_balances` use `account_type IN ('gl_control', 'merchant_dda', 'external_counter')`; merchant sub-ledgers and the external customer pool / external rail roll up to the synthetic `pr-merchant-ledger` control account. PR-specific metadata (`card_brand`, `cashier`, `settlement_type`, `payment_method`, `is_returned`, `return_reason`, etc.) lives in the `metadata` JSON column and is read via `JSON_VALUE(metadata, '$.<key>')`.

### Account Reconciliation
**Ledger accounts (with daily balances) → Sub-ledger accounts → Transactions (double-entry ledger)**

- Every transfer is a set of `transactions` legs (grouped by `transfer_id`) that must net to zero
- Legs can target sub-ledger accounts OR ledger control accounts directly (funding batches, fee assessments, clearing sweeps, all CMS-driven sweeps); the `account_id` and `control_account_id` columns express the hierarchy
- Ledger drift invariant: `stored ledger balance = Σ direct ledger postings + Σ sub-ledger stored balances`
- Sub-ledger drift invariant: `stored sub-ledger balance = Σ postings to that sub-ledger` (unaffected by ledger-level postings)
- Daily balance snapshots in `daily_balances` allow drift detection: recomputed balance vs. stored balance
- Failed legs, limit breaches (ledger daily out-flow cap per sub-ledger/type, configured in `ar_ledger_transfer_limits` and surfaced through the `daily_balances.metadata` JSON), and overdrafts (sub-ledger below zero) populate the Exceptions tab
- Every exception check follows a standard visual pattern: KPI count + detail table (with `days_outstanding` and `aging_bucket` columns) + horizontal aging bar chart. Drift checks also have timelines.
- Aging buckets: 5 hardcoded bands (`1: 0-1 day`, `2: 2-3 days`, `3: 4-7 days`, `4: 8-30 days`, `5: >30 days`) — numeric prefix forces correct sort in QuickSight
- Drift timelines (ledger + sub-ledger) surface systemic issues over time
- Transactions carry an `origin` tag (`internal_initiated` / `external_force_posted`); origin multi-select filter on Transactions + Exceptions tabs
- AR is the unified view of the shared base tables — every `transfer_type` (PR types included) and every `account_id` surfaces in AR datasets and views without artificial exclusion. Single-leg PR types (`sale`, `external_txn`) carry `expected_net_zero = 'not_expected'` on `ar_transfer_summary` so the Non-Zero Transfers KPI excludes them semantically rather than by hiding them. Conversely, PR datasets stay tightly persona-scoped: that's the asymmetry of the unified-AR-superset framing.

#### CMS structure (Phase F)

Demo persona is **Sasquatch National Bank — Cash Management Suite (CMS)** — same SNB from PR, viewed through treasury after SNB absorbed Farmers Exchange Bank's commercial book.

- **8 internal GL control accounts**: Cash & Due From FRB, ACH Origination Settlement (`gl-1810`), Card Acquiring Settlement, Wire Settlement Suspense, Internal Transfer Suspense (`gl-1830`), Cash Concentration Master (`gl-1850`), Internal Suspense / Reconciliation, Customer Deposits — DDA Control.
- **7 customer DDAs**: 3 coffee retailers shared with PR (Bigfoot Brews, Sasquatch Sips, Yeti Espresso) + 4 commercial (Cascade Timber Mill, Pinecrest Vineyards, Big Meadow Dairy, Harvest Moon Bakery).
- **4 telling-transfer flows from CMS**: ZBA / Cash Concentration sweep → Concentration Master; daily ACH origination sweep → FRB Master Account; external force-posted card settlement → Card Acquiring Settlement; on-us internal transfer → Internal Transfer Suspense → destination DDA. Each flow plants both success cycles and characteristic failures.
- **Exceptions tab structure**: 3 cross-check rollups at the top (expected-zero EOD, two-sided post-mismatch, balance drift timelines) teach error-class recognition; per-check details below let analysts drill the specific row. 14 checks total: 5 baseline (sub-ledger drift, ledger drift, non-zero transfers, limit breach, overdraft) + 9 CMS-specific (sweep target nonzero, concentration master sweep drift, ACH orig settlement nonzero, ACH sweep no Fed confirmation, Fed card no internal catch-up, GL vs FRB master drift, internal transfer stuck, internal transfer suspense nonzero, internal reversal uncredited).

### Investigation
**Question-shaped: Recipient Fanout / Volume Anomalies / Money Trail / Account Network**

- Reads from the same shared `transactions` base table; no investigation-specific schema, no app-specific dimension tables.
- Two materialized views back the heavier sheets: `inv_pair_rolling_anomalies` (Volume Anomalies — rolling 2-day SUM per (sender, recipient) pair + population mean / sample stddev → per-row z-score + 5-band bucket) and `inv_money_trail_edges` (Money Trail + Account Network — `WITH RECURSIVE` walk over `parent_transfer_id` flattened to one row per multi-leg edge with chain root + depth + `source_display` / `target_display` strings). Both **do not auto-refresh** — every ETL load must run `REFRESH MATERIALIZED VIEW` on each, same contract as `ar_unified_exceptions`.
- The Account Network sheet's anchor dropdown is backed by a small dedicated dataset (`inv-anetwork-accounts-ds`) that pre-deduplicates `name (id)` display strings — querying the K.4.5 matview directly for distinct anchors forces the planner to compute the concat per row before dedupe (O(matview rows)); the small-dataset wrapper does it once per distinct account.
- Walk-the-flow drills (Account Network): right-click any touching-edges table row OR left-click any directional Sankey node overwrites the `pInvANetworkAnchor` parameter with the counterparty side. Per the QuickSight URL-parameter control sync limitation (see PLAN.md tech debt), the dropdown widget may briefly lag; sheet description tells analysts "trust the chart, not the control text".
- Cross-app drills (Investigation → AR/PR) were investigated and **dropped** in K.4.7 — QuickSight doesn't sync sheet parameter controls to URL-set values. Investigation stays a self-contained app; analysts leave for AR Transactions / PR pipeline tabs by manually navigating.
- Demo persona: **Sasquatch National Bank — Compliance / Investigation team**. Three converging scenarios on a single anchor (Juniper Ridge LLC, `cust-900-0007-juniper-ridge-llc`) — a fanout cluster (12 individual depositors), an anomaly pair (Cascadia Trust Bank — Operations $25K spike vs $300–$700 baseline), and a 4-hop layering chain (Cascadia → Juniper → Shell A → Shell B → Shell C with $250 residue per hop).

## Architecture Decisions

- All models use Python dataclasses with `to_aws_json()` methods that produce the exact dict shape for AWS QuickSight API (`create-analysis`, `create-dashboard`, `create-data-set`, `create-theme`, `create-data-source`)
- Helper `_strip_nones()` recursively cleans None values from serialized output
- Config accepts a pre-existing DataSource ARN for production use; for demo, `datasource_arn` is auto-derived from `demo_database_url` and `datasource.json` is generated
- All datasets use custom SQL in PostgreSQL syntax (no SPICE → Direct Query). Seed changes show up immediately after `demo apply` — no refresh step.
- SQL is constrained to a portable subset: SQL/JSON path syntax (`JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`); no JSONB, no `->>` / `->` / `@>` / `?` operators, no GIN indexes on JSON, no Postgres extensions, no array / range types. PostgreSQL 17+ required for `demo apply`.
- Generated resource IDs use kebab-case with a configurable prefix (default `qs-gen-`)
- All resources tagged `ManagedBy: quicksight-gen`; `extra_tags` in config are merged in
- `cleanup` uses that tag to enumerate managed resources and deletes anything not in the current `out/`
- Every sheet has a plain-language description; every visual has a subtitle — the end customer is not technical. Coverage is enforced in unit + API e2e tests.
- Clickable cells use `common/clickability.py`: accent-colored text = left-click drill; accent text on pale-tint background = the cell also carries a right-click menu drill (use this style whenever a right-click action exists, even if a left-click is also wired)
- **Drill direction convention** — left clicks move you LEFT, right clicks move you RIGHT. When wiring a new drill action on a row, pick the trigger by which sheet the drill points to relative to the source: deeper / further-down-the-pipeline / further-right-in-the-tab-order goes on `DATA_POINT_MENU` (right-click); back-toward-source goes on `DATA_POINT_CLICK` (left-click). Call out both clicks in the visual's subtitle when both are wired. Existing wirings that pre-date this rule are not retroactively flipped.
- **Tree pattern (Phase L).** All four apps are tree-built. New code under `common/tree/` — `App` / `Analysis` / `Dashboard` / `Sheet` plus typed `Visual` subtypes (`KPI` / `Table` / `BarChart` / `Sankey`), typed Filter wrappers (`CategoryFilter` / `NumericRangeFilter` / `TimeRangeFilter`), Parameter + Filter `Control` wrappers, and `Drill` actions. Cross-references are object refs, not string IDs (visuals reference datasets by `Dataset` node; filter groups reference visuals by `Visual` node; drills reference sheets by `Sheet` node). Internal IDs (visual_id, filter_group_id, action_id, layout element IDs) are auto-assigned at emit time using a position-indexed scheme; URL-facing IDs (`SheetId`, `ParameterName`) and analyst-facing identifiers (`Dataset` identifier, `CalcField` name) stay explicit. `App.emit_analysis()` / `emit_dashboard()` runs validation walks (dataset references, calc-field references, parameter references, drill destinations, FilterGroup scoping). New app code uses the tree directly — `apps/<app>/app.py` is the only file that wires sheets/visuals/filters; per-app `constants.py` modules carry only the URL-facing + analyst-facing identifiers (sheet IDs, filter-group IDs, parameter names) and dataset identifiers; greenfield apps (Executives) skip `constants.py` entirely by inlining sheet IDs in `app.py`.
- **Three-layer model — L1 / L2 / L3.** The tree's existence is the test case for layer separation:
  - **L1 — `common/tree/`, `common/models.py`, `common/ids.py`, `common/dataset_contract.py`.** Persona-blind primitives. Every type knows about *dashboards* (sheets, visuals, filters, drills, dataset contracts) and nothing about Sasquatch / banks / accounts / transfers. If you grep `common/tree/` for "sasquatch" you should find zero hits — and that grep is the L1 invariant.
  - **L2 — `apps/<app>/app.py`, `apps/<app>/constants.py`.** Per-app tree assembly. Wires L1 primitives into one app's dashboard shape: which sheets, which visuals on each, which filters/drills/parameters. Talks the *domain* vocabulary ("Account Coverage", "transfer_type", "open vs active", "expected_net_zero") — domain language a CPA would recognize, but **not** persona names ("Sasquatch", "Bigfoot Brews", "FRB Master").
  - **L3 — `apps/<app>/datasets.py` SQL strings, `apps/<app>/demo_data.py`, `common/persona.py`, theme presets in `common/theme.py`.** Persona / customer flavor. SQL strings reference real column names; `demo_data.py` plants Sasquatch-flavored row values; theme presets carry brand colors; `persona.py` centralizes the Sasquatch strings so a publishing team can substitute them via `training/mapping.yaml.example`.
- **Tree IS the source of truth.** Tests walk the tree to derive expected sets — they do not maintain parallel hand-listed expectations. Examples already in the codebase:
  - Unit test: `test_executives.py::test_account_coverage_active_kpi_filter_pinned` walks `exec_app.analysis.filter_groups` to find the visual-pinned filter and asserts its scope, instead of asserting a hardcoded `(visual_id_a, visual_id_b)` tuple.
  - API e2e: `test_exec_dashboard_structure.py::TestParameters::test_all_parameters_declared` derives `expected = {str(p.name) for p in exec_app.analysis.parameters}` instead of hardcoding the parameter set.
  - Browser e2e: `test_exec_sheet_visuals.py` calls `TreeValidator(exec_app, page).validate_structure()` once instead of per-sheet visual-count + visual-title dicts; failures across sheets accumulate into one AssertionError listing every mismatch.
  - Identity assertions key off **stable analyst-facing identifiers** (visual *titles*, sheet *names*, dataset *identifiers*, parameter *names*) — never off auto-derived internal IDs (`v-table-s4-2`), which are positional and regenerate on tree restructure.

## Conventions

- Type hints throughout
- **Never hardcode hex colors in analysis code.** Resolve from `get_preset(cfg.theme_preset).<token>` at generate time (accent, primary_fg, link_tint, etc.).
- One module per concern; `apps/payment_recon/` has `visuals.py` + `recon_visuals.py` and `filters.py` + `recon_filters.py` because the Payment Reconciliation tab is a distinct UX pattern
- Theme presets live in the `PRESETS` dict in `common/theme.py`; set `analysis_name_prefix="Demo"` on demo presets
- Default theme: blues and greys, high contrast, titles ≥ 16px, body ≥ 12px
- The end customer doesn't know exactly what they want — keep the code easy to mutate and iterate on
- Rich text on Getting Started sheets uses `common/rich_text.py`; theme-accent colors resolve to hex at generate time
- Each dataset declares a `DatasetContract` (column name + type list) in its `datasets.py`; the SQL query is one implementation. Tests assert the SQL projection matches the contract. `build_dataset()` in `common/dataset_contract.py` is the shared constructor.
- **Encode invariants in the type system, not in validation tests.** When a class of bug can be made unrepresentable through typed wrappers, dataclass `__post_init__` validation, or typed constructor functions that fail at the wiring site, prefer that over a separate test that walks the generated output and asserts shape. Type-encoded invariants fail at the buggy line; output-walking tests fail in a far-off file with output that requires triangulation back to the wiring site. End-to-end behavioral tests (e2e) are still the right tool for "does the deployed thing actually render?" — the rule is specifically about correctness invariants of constructed objects (drill action shape compatibility, parameter/column-type matching, etc.).

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
- Each app has its own demo persona — same Sasquatch National Bank, three operational views: PR is the merchant-acquiring side (coffee-shop settlement); AR is the treasury / CMS side (GL control accounts + customer DDAs absorbed from FEB); Investigation is the Compliance / AML side (Juniper Ridge LLC convergence anchor + 12 individual depositors + Cascadia Trust Bank ops + 3 shell DDAs). Don't cross-contaminate at the persona level — PR and AR share base tables and three customer DDAs (the coffee retailers) but the rest of the data is disjoint, separated by `account_type` / `transfer_type`. Investigation registers its own internal + external ledger sub-tree (`inv-customer-deposits-watch` + `ext-individual-depositors` + `ext-cascadia-trust-bank`) so `demo seed investigation` is FK-safe standalone.
- Determinism is locked by a SHA256 hash assertion on the full seed SQL output (`tests/test_demo_data.py::TestDeterminism::test_seed_output_hash_is_locked` per app). Any generator change that shifts a single byte fails that test loudly — re-lock by pasting the new hash into the assertion when the change is intentional.
