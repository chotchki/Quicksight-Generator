# Implementation Plan

This plan covers the delta between the current codebase and the updated SPEC.md. Three areas of work:

1. **New Reconciliation Analysis** — a second, separate analysis for matching internal records against external systems
2. **User-friendly explanations** — descriptions on every analysis, sheet, and visual so non-technical users can self-serve
3. **Reconciliation datasets** — new custom SQL datasets for external transactions and match results

---

## What exists today

- One analysis (`qs-gen-financial-analysis`) with 4 sheets: Sales Overview, Settlements, Payments, Exceptions & Alerts
- Six datasets: merchants, sales, settlements, payments, settlement-exceptions, payment-returns
- One theme (shared, no changes needed)
- CLI `generate` command writes theme + datasets + one analysis to `out/`
- Common `ManagedBy` tag on all resources

---

## New domain concepts from SPEC

The financial application reconciles its internal records (sales, settlements, payments) against **external system aggregations**:

- External systems aggregate internal records into **transactions** with unique identifiers. Each external transaction covers a certain number of sales, settlements, or payments and has a total amount.
- A **match** is valid only when the external transaction total equals the sum of the corresponding internal records.
- Match statuses: **matched** (totals equal), **not yet matched** (still pending), **late** (overdue per type-specific threshold).
- "Late" has a **static definition that varies by type** (e.g., a sale might be considered late after 2 business days, a settlement after 5). This definition should be displayed in the analysis but is not editable in QuickSight.

---

## Step 1: Add reconciliation dataset identifiers and constants

**File: `constants.py`**

Add constants for the new reconciliation analysis and datasets:

- `DS_EXTERNAL_TRANSACTIONS` — external system transaction records
- `DS_SALES_RECON` — sales matched against external transactions
- `DS_SETTLEMENT_RECON` — settlements matched against external transactions
- `DS_PAYMENT_RECON` — payments matched against external transactions
- `DS_RECON_EXCEPTIONS` — late/unmatched items across all types with late threshold definitions
- Sheet IDs for the reconciliation analysis: `SHEET_RECON_OVERVIEW`, `SHEET_SALES_RECON`, `SHEET_SETTLEMENT_RECON`, `SHEET_PAYMENT_RECON`

**Dependencies:** None

---

## Step 2: Add reconciliation datasets

**File: `datasets.py`**

Add five new dataset builder functions. All use placeholder SQL.

### 2a: `build_external_transactions_dataset`
Columns: `transaction_id`, `transaction_type` (sales/settlement/payment), `external_system` (which external system this came from — there are multiple, all via the single datasource), `external_amount`, `record_count`, `transaction_date`, `status`

Placeholder SQL selects from an `external_transactions` table.

### 2b: `build_sales_recon_dataset`
Columns: `transaction_id`, `external_amount`, `internal_total`, `difference`, `match_status` (matched/not_yet_matched/late), `sale_count`, `merchant_id`, `transaction_date`, `late_threshold`, `late_threshold_description`

Placeholder SQL joins `external_transactions` to aggregated `sales`, computes match status and difference.

### 2c: `build_settlement_recon_dataset`
Same structure as 2b but for settlements. Columns: `transaction_id`, `external_amount`, `internal_total`, `difference`, `match_status`, `settlement_count`, `merchant_id`, `transaction_date`, `late_threshold`, `late_threshold_description`

### 2d: `build_payment_recon_dataset`
Same structure for payments.

### 2e: `build_recon_exceptions_dataset`
All late and unmatched items across all types. Columns: `transaction_id`, `transaction_type`, `external_system`, `match_status`, `external_amount`, `internal_total`, `difference`, `days_outstanding`, `late_threshold`, `late_threshold_description`, `merchant_id`, `transaction_date`

This dataset's SQL unions the three reconciliation views filtered to non-matched statuses. The `days_outstanding` column is critical for late filtering — users will filter on this to find items that are X days overdue.

### Update `build_all_datasets`
Rename to `build_financial_datasets` and add `build_recon_datasets` returning the five new datasets. Add `build_all_datasets` that returns both lists combined.

**Dependencies:** Step 1

---

## Step 3: Build reconciliation visuals

**File: `visuals.py`** (or a new `recon_visuals.py` if the file gets too large — decision at implementation time)

### 3a: Reconciliation Overview visuals
- KPI: total matched count (across all types)
- KPI: total not-yet-matched count
- KPI: total late count (prominently highlighted — this is what users care about most)
- Pie chart: match status breakdown across all types
- Bar chart: match status by type (sales/settlement/payment)
- Bar chart: match status by external system

### 3b: Sales Reconciliation visuals
- KPI: sales matched count, sales match rate %
- KPI: sales unmatched/late count
- Bar chart: match status by merchant
- Table: sales reconciliation detail (transaction_id, external_system, external_amount, internal_total, difference, match_status, days_outstanding, late_threshold_description)

### 3c: Settlement Reconciliation visuals
Same structure as 3b for settlements.

### 3d: Payment Reconciliation visuals
Same structure as 3b for payments.

**Dependencies:** Step 1, Step 2

---

## Step 4: Build reconciliation filters

**File: `filters.py`** (or new `recon_filters.py`)

New filter groups for the reconciliation analysis:

- **Date range** — on `transaction_date`, applies to all recon sheets
- **Match status** dropdown — applies to all recon sheets
- **Transaction type** dropdown — applies to overview
- **External system** dropdown — applies to all recon sheets (multiple external systems exist)
- **Merchant** dropdown — applies to all recon sheets
- **Days outstanding** — numeric filter to show items late by at least X days, applies to all recon sheets. Lets users focus on the most overdue items.

Per-sheet control builders: `build_recon_overview_controls`, `build_sales_recon_controls`, `build_settlement_recon_controls`, `build_payment_recon_controls`

**Dependencies:** Step 1

---

## Step 5: Build reconciliation analysis

**File: new `recon_analysis.py`**

Create `build_recon_analysis(cfg: Config) -> Analysis` that produces:

- Analysis ID: `qs-gen-reconciliation-analysis`
- Name: "Reconciliation Analysis"
- 4 sheets:
  - **Reconciliation Overview** — high-level match rates and status breakdowns
  - **Sales Reconciliation** — sales matching detail
  - **Settlement Reconciliation** — settlement matching detail
  - **Payment Reconciliation** — payment matching detail
- References only the 5 reconciliation datasets
- Uses the same shared theme
- Same permissions, tags pattern as existing analysis

**Dependencies:** Steps 2, 3, 4

---

## Step 6: Add user-friendly explanations to all analyses

**Files: `analysis.py`, `recon_analysis.py`, `visuals.py`, recon visuals**

The SPEC says: "the quicksight dashboards should include easy to understand explanations to help someone understand what each analysis, sheet, visualization does."

### 6a: Sheet descriptions
Add or improve the `Description` field on every `SheetDefinition` to explain in plain language what the sheet shows and how to use it. These descriptions appear in the QuickSight UI when a user views sheet info.

Examples:
- Sales Overview: "Shows total sales volume and amounts. Use the filters above to narrow by date range, merchant, or location. The charts highlight which merchants and locations drive the most sales."
- Reconciliation Overview: "Shows how well our internal records match external system totals. Green means matched, yellow means still pending, red means late. Use this tab to spot problems at a glance."

### 6b: Visual subtitles
Add `Subtitle` with `FormatText` to every visual, providing a one-sentence explanation of what the visual shows. The existing visuals only have `Title` set — `Subtitle` is unused.

Examples:
- "Total Sales Count" KPI subtitle: "Count of all sales in the selected date range"
- "Sales Missing Settlements" table subtitle: "Sales that have not yet been bundled into a settlement — investigate if any are overdue"
- "Match Status by Type" bar chart subtitle: "Compares how many sales, settlements, and payments are matched, pending, or late"

### 6c: Late threshold explanation
On the reconciliation detail tables, the `late_threshold_description` column should be included and its visual subtitle should explain: "The 'Late Threshold' column shows the definition of 'late' for each record type — this is set by the system and cannot be changed here."

**Dependencies:** Steps 3, 5 (reconciliation visuals must exist first, but financial analysis explanations can be done in parallel with earlier steps)

---

## Step 7: Update CLI to generate both analyses

**File: `cli.py`**

Update the `generate` command to:
1. Write `out/theme.json` (unchanged)
2. Write `out/datasets/*.json` for all datasets (financial + reconciliation)
3. Write `out/financial-analysis.json` (renamed from `analysis.json` — no existing users)
4. Write `out/recon-analysis.json`
5. Update the file count in the summary message

**Dependencies:** Step 5

---

## Step 8: Update tests

**Files: `tests/test_generate.py`, `tests/test_models.py`**

### 8a: Update generate smoke tests
- Expect 11 dataset files (6 financial + 5 reconciliation) instead of 6
- Expect two analysis files instead of one
- Cross-reference tests should validate both analyses
- Tag tests should cover both analyses

### 8b: Add reconciliation-specific tests
- Reconciliation dataset ARNs are declared in the reconciliation analysis
- Visual dataset refs in the reconciliation analysis all point to declared recon datasets
- Filter scope sheet IDs in recon analysis match recon sheets
- Visual IDs are unique across the reconciliation analysis

### 8c: Explanation coverage tests
- Every sheet across both analyses has a non-empty `Description`
- Every visual across both analyses has a non-None `Subtitle`

**Dependencies:** Step 7

---

## Step 9: Update CLAUDE.md

Update the project reference doc to reflect:
- Two analyses (financial + reconciliation)
- New dataset list
- New module (`recon_analysis.py`, and possibly `recon_visuals.py` / `recon_filters.py`)
- Updated domain model section covering the reconciliation concept

**Dependencies:** Steps 7, 8

---

## Dependency graph

```
Step 1 (constants)
├── Step 2 (recon datasets)
│   └── Step 5 (recon analysis) ← Steps 3, 4
│       └── Step 7 (CLI update)
│           └── Step 8 (tests)
│               └── Step 9 (update CLAUDE.md)
├── Step 3 (recon visuals) ← Step 2
├── Step 4 (recon filters)
└── Step 6 (explanations) — can begin for financial analysis immediately;
                             recon explanations depend on Steps 3, 5
```

## Resolved questions

1. **Late thresholds**: Unmatched items become late based on their type. Datasets will include a `days_outstanding` column. The reconciliation analysis will provide a filter to show items that are X days late, and visuals should highlight/call out late items prominently.
2. **External system identifiers**: Multiple external systems, all accessed through the single configured datasource. The `external_system` column distinguishes which system a transaction came from.
3. **Match granularity**: Exact match only — the external transaction total must equal the internal sum exactly. No partial matches.
4. **Output file naming**: No existing users, so `analysis.json` becomes `financial-analysis.json` and the new reconciliation analysis goes to `recon-analysis.json`.
