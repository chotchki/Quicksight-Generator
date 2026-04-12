# Plan: Reconciliation Redesign — Payments-Only External Matching

## Summary

Only payments leave the internal system, so only payments need external reconciliation. The current 3-type recon design (sales/settlements/payments each matched against external systems) is wrong. This plan narrows reconciliation to payments only, consolidates everything into a single analysis/dashboard, and replaces the charting-heavy recon overview with dual mutually-filterable tables.

## Key Decisions (from open questions)

1. **No Sankey** — dual mutually-filterable tables (external transactions + internal payments) are the core visualization. Date and unmatched filters control the view.
2. **Payment drill-down** — an external transaction contains 1+ internal payments. Clicking a transaction shows its payments; clicking a payment can navigate back to the financial Payments sheet.
3. **Consolidate into one dashboard** — merge the recon sheet(s) into the financial analysis. Eliminates cross-analysis linking complexity; cross-sheet NavigationOperation just works.
4. **One payment per external system** — no many-to-many. Simplifies the schema and join logic.
5. **Late threshold as config** — drop the `late_thresholds` table. Move to a config value (`late_threshold_days` in config.yaml). Users can also use the days-outstanding slider to set their own cutoff interactively.

## Target State

### Single consolidated analysis/dashboard with 5 sheets:

1. **Sales Overview** (unchanged)
2. **Settlements** (unchanged)
3. **Payments** (unchanged, but gains a drill-down action to the recon sheet)
4. **Exceptions & Alerts** (unchanged)
5. **Payment Reconciliation** (new — replaces the entire separate recon analysis)

### Sheet 5: Payment Reconciliation layout

- **KPIs** (top row, thirds): Total Matched $, Total Unmatched $, Late Count
- **External Transactions table** (left/top): transaction_id, external_system, external_amount, match_status, days_outstanding — click a row to filter the payments table below
- **Internal Payments table** (right/bottom): payment_id, merchant_id, payment_amount, payment_date, external_transaction_id — click a row to filter the external transactions table above, or navigate to the Payments sheet
- **Filters**: date range, match status dropdown, external system dropdown, days outstanding slider

Mutual filtering between the two tables uses a `pExternalTransactionId` parameter: clicking an external transaction sets the parameter, which filters the payments table; clicking a payment sets the same parameter from its `external_transaction_id`, which filters back.

## Implementation Steps

### Phase 1: Schema & Demo Data

- [x] 1.1 — Update `demo/schema.sql`: remove `external_transaction_id` column from `sales` table
- [x] 1.2 — Update `demo/schema.sql`: remove `external_transaction_id` column from `settlements` table
- [x] 1.3 — Update `demo/schema.sql`: remove `transaction_type` column from `external_transactions` table (all are payments now)
- [x] 1.4 — Update `demo/schema.sql`: drop `sales_recon_view` and `settlement_recon_view`
- [x] 1.5 — Update `demo/schema.sql`: drop `late_thresholds` table entirely
- [x] 1.6 — Update `demo/schema.sql`: update `payment_recon_view` to use a hardcoded threshold (or remove — the dataset SQL can handle it)
- [x] 1.7 — Update `demo/schema.sql`: remove indexes on dropped columns (`idx_sales_ext_txn`, `idx_settlements_ext_txn`)
- [x] 1.8 — Update `demo_data.py`: remove `_build_sales_ext_txns()` and `_build_settlement_ext_txns()`
- [x] 1.9 — Update `demo_data.py`: update `_generate_external_transactions()` to only generate payment external transactions (expand to ~30-40 for richer data)
- [x] 1.10 — Update `demo_data.py`: remove `ext_txn_id` field from sales and settlements records
- [x] 1.11 — Update `demo_data.py`: remove `THRESHOLDS` constant and its INSERT generation
- [x] 1.12 — Update `demo_data.py`: remove `external_transaction_id` from sales and settlements INSERT column lists
- [x] 1.13 — Update `demo_data.py`: remove `transaction_type` from external_transactions INSERT column list
- [x] 1.14 — Run tests, fix `test_demo_data.py` and `test_demo_sql.py` failures

### Phase 2: Datasets

- [x] 2.1 — Update `datasets.py` `build_sales_dataset()`: remove `external_transaction_id` from InputColumns and SQL
- [x] 2.2 — Update `datasets.py` `build_settlements_dataset()`: remove `external_transaction_id` from InputColumns and SQL
- [x] 2.3 — Update `datasets.py` `build_external_transactions_dataset()`: remove `transaction_type` from InputColumns and SQL
- [x] 2.4 — Remove `build_sales_recon_dataset()` entirely
- [x] 2.5 — Remove `build_settlement_recon_dataset()` entirely
- [x] 2.6 — Remove `build_recon_exceptions_dataset()` entirely
- [x] 2.7 — Update `build_payment_recon_dataset()`: remove `late_thresholds` join, compute match_status using config-driven threshold, remove `late_threshold` and `late_threshold_description` columns
- [x] 2.8 — Update `build_recon_datasets()`: return only `[external_transactions, payment_recon]`
- [x] 2.9 — Add `late_threshold_days` to `Config` dataclass in `config.py` (default 30), pass it into the payment-recon dataset SQL
- [x] 2.10 — Update `constants.py`: remove `DS_SALES_RECON`, `DS_SETTLEMENT_RECON`, `DS_RECON_EXCEPTIONS`, `SHEET_SALES_RECON`, `SHEET_SETTLEMENT_RECON`
- [x] 2.11 — Run tests, fix `test_models.py` and `test_generate.py` failures

### Phase 3: Consolidate into One Analysis

- [x] 3.1 — Update `analysis.py` `_build_financial_definition()`: add recon dataset declarations (external-transactions, payment-recon) alongside the financial ones
- [x] 3.2 — Add a `pExternalTransactionId` parameter declaration alongside `pSettlementId`
- [x] 3.3 — Add parameter-bound filter groups for `external_transaction_id` on the payments dataset (scoped to recon sheet) and `transaction_id` on the payment-recon dataset (scoped to recon sheet)
- [x] 3.4 — Add a new `SHEET_PAYMENT_RECON` constant (keep the value, just use it in the financial analysis now)
- [x] 3.5 — Build the Payment Reconciliation sheet definition in `analysis.py` with the new visuals, filters, and layout
- [x] 3.6 — Add the recon sheet as sheet 5 in the financial analysis sheets list
- [x] 3.7 — Add recon filter groups to the financial analysis filter groups list (scoped to recon sheet only)
- [x] 3.8 — Run tests, verify the financial analysis JSON now includes the recon sheet

### Phase 4: Recon Visuals & Filters

- [x] 4.1 — Rewrite `recon_visuals.py`: build KPIs (matched $, unmatched $, late count) using payment-recon dataset
- [x] 4.2 — Build external transactions table visual with click action (sets `pExternalTransactionId` parameter)
- [x] 4.3 — Build internal payments table visual with click action (sets `pExternalTransactionId` from `external_transaction_id` field, and/or navigates to Payments sheet)
- [x] 4.4 — Rewrite `recon_filters.py`: date range filter (scoped to recon sheet), match status dropdown, external system dropdown, days outstanding slider
- [x] 4.5 — Build grid layout for the recon sheet (KPIs in thirds at top, tables stacked below)
- [x] 4.6 — Add drill-down action on financial Payments detail table: click a payment → navigate to Payment Reconciliation sheet, set `pExternalTransactionId`
- [x] 4.7 — Run tests, fix `test_recon.py` failures (full rewrite done)

### Phase 5: Remove Separate Recon Analysis

- [x] 5.1 — Remove `build_recon_analysis()` and `build_recon_dashboard()` from `recon_analysis.py`
- [x] 5.2 — Update `cli.py`: stop generating `recon-analysis.json` and `recon-dashboard.json`
- [x] 5.3 — Update `deploy.sh`: remove references to `recon-analysis.json` and `recon-dashboard.json` from the analysis/dashboard loops
- [x] 5.4 — `recon_analysis.py` gutted to a docstring explaining consolidation
- [x] 5.5 — Run full test suite, fix all remaining failures (123 tests passing)
- [x] 5.6 — Update `CLAUDE.md`: revise project structure, generated output listing, domain model description

### Phase 6: Deploy & Validate

- [x] 6.1 — Regenerate all JSON (`quicksight-gen generate -c config.yaml -o out/`)
- [x] 6.2 — Run `./deploy.sh --delete` to clean up old resources (important: old recon analysis/dashboard won't be recreated)
- [x] 6.3 — Run `./deploy.sh` to deploy the consolidated analysis
- [x] 6.4 — Verify financial sheets (Sales, Settlements, Payments, Exceptions) still work
- [x] 6.5 — Verify the Payment Reconciliation sheet: KPIs, dual tables, mutual filtering
- [x] 6.6 — Test drill-down: Payments sheet → Recon sheet, Recon sheet → Payments sheet
- [x] 6.7 — Update SPEC.md to mark reconciliation items as done

## Files Changed (Summary)

| File | Change |
|------|--------|
| `demo/schema.sql` | Remove sales/settlement recon views, drop ext_txn_id from sales/settlements, drop late_thresholds, simplify external_transactions |
| `demo_data.py` | Remove sales/settlement ext txns, expand payment ext txns, remove thresholds, remove ext_txn_id from sales/settlements |
| `config.py` | Add `late_threshold_days` config field |
| `datasets.py` | Remove 3 recon datasets, clean ext_txn_id from sales/settlements datasets, update payment-recon to use config threshold |
| `constants.py` | Remove unused DS_*/SHEET_* constants |
| `recon_visuals.py` | Full rewrite — dual tables + KPIs for payments-only recon |
| `recon_filters.py` | Simplify — payments-only, scoped to recon sheet |
| `analysis.py` | Add recon datasets/sheets/filters/parameters to financial analysis |
| `recon_analysis.py` | Remove or gut — no longer produces a separate analysis |
| `cli.py` | Stop generating recon-analysis.json / recon-dashboard.json |
| `deploy.sh` | Remove recon-analysis/dashboard from loops |
| `tests/test_recon.py` | Rewrite for new structure |
| `tests/test_models.py` | Update recon references |
| `tests/test_demo_sql.py` | Update for schema changes |
| `tests/test_demo_data.py` | Update for simplified data |
| `tests/test_generate.py` | Update integration tests |
| `CLAUDE.md` | Update project structure, output listing, domain model |
