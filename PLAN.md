# PLAN — Phase K: persona-driven layout work

K.1 + K.2 (+ v3.6.1 doc patch) + K.2a + K.3 shipped — see `PLAN_ARCHIVE.md` for the rolled-up summaries and `RELEASE_NOTES.md` for the per-version detail.

## K.4 — Investigative app (AML + general)
(Note before we start on this, that this is broader than just AML — call it the investigative app)
(Another note, just like the exception views, I expect this module to require some materialized views for its worst queries)

Goal: new `quicksight_gen.aml_recon` app (third app alongside PR + AR), mirroring the existing two-app pattern. Reads from the same `transactions` + `daily_balances` base tables — no schema changes (assuming K.3 has shipped, the new lateness column is already there for free). Build feasibility-driven, not equally-weighted.

- [ ] **K.4.0 — App skeleton.** New `src/quicksight_gen/aml_recon/` package mirroring `account_recon/` layout (`analysis.py`, `visuals.py`, `filters.py`, `datasets.py`, `demo_data.py`, `constants.py`, `etl_examples.py`). Wire into CLI (`generate`, `deploy`, `demo apply` accept `aml-recon` as a third app). New theme preset `sasquatch-bank-aml`. Empty Getting Started sheet + 3 stub sheets.
- [ ] **K.4.1 — Person-to-person fanout sheet.** Easiest: straight aggregation. Dataset: COUNT DISTINCT senders + SUM(amount) per recipient sub-ledger over a chosen window. Visual: KPI (total recipients with N+ distinct senders) + ranked table sorted by fanout count. Filter: window length, fanout threshold.
- [ ] **K.4.2 — Sliding-window statistical anomaly sheet.** Moderate: WINDOW functions + std-dev. Dataset: rolling SUM(amount) per sender→recipient pair over a 2-day window, with a population baseline mean + std-dev computed across the same window family; flag rows where window sum > mean + 2σ. Visual: distribution plot + flagged-rows table. Filter: σ threshold (default 2), window length (default 2 days).
- [ ] **K.4.3 — Money-trail provenance sheet.** Hardest: graph traversal. Dataset shape: recursive CTE walking up/down `parent_transfer_id` chains from a chosen starting transfer_id, **flattened to one row per edge** — `(source_account_id, target_account_id, hop_amount, depth)` — which is the input shape QuickSight's native Sankey visual consumes (Source / Destination / Weight). Visual: Sankey is the headline (one node per touched account, one link per edge, weight = hop_amount); a hop-by-hop detail table sits beside it for the rows Sankey hides plus account/transfer_id legibility. Filter: starting transfer_id, max hops, min hop amount. Fallback if a chosen chain exceeds QuickSight's Sankey node/link cap: surface the hop-by-hop table as the primary view for that query and a "chain too wide for Sankey" notice in the visual subtitle.
- [ ] **K.4.4 — AML demo data extension.** Plant scenario rows exercising each sheet: a fanout cluster (10+ senders → 1 recipient), a 2σ-anomalous window pair, and a 4-hop transfer chain. Add `TestScenarioCoverage` assertions in `test_aml_demo_data.py`. Re-lock the per-app SHA256 hash.
- [ ] **K.4.5 — Browser e2e for AML.** `tests/e2e/test_aml_*.py` mirroring AR's coverage shape. Sheet visuals render, filters scope correctly, drill-downs land.
- [ ] **K.4.6 — AML Handbook section.** New `docs/handbook/aml.md` + `docs/walkthroughs/aml/*.md`. Three walkthroughs minimum, one per sheet's core question. Add to `mkdocs.yml` nav after PR.

**Sequencing.** K.1 + K.2 shipped (v3.5.0–v3.6.0). K.3 next: schema-additive lateness column with handbook + dataset ripple; cleaner to land before greenfield app work writes more SQL against the old "operator threshold" pattern. K.4 last: greenfield app, no in-flight users to disrupt, picks up both the K.2 drill helper and the K.3 lateness column for free. Within K.4, sub-steps remain ordered fanout → sliding window → provenance, easiest first; ship each sheet incrementally so the app becomes usable after K.4.1, not only at K.4.3.

# Backlog - Phase L Candidates

## Whitelabeling Enhancements
- enhance all the demo data/handbook to be reskinable like the training material can be. don't want to break the crypto hash on the training output, so maybe a string replace after that but before its applied?

## Audit Enhancements
- How can someone show the state of the system durably?
  - This could be columns on the daily statement, show the percentage of each transaction row that matches perfectly to its other legs
  - This is to support reporting to auditors/regulators
  - should not use the pixel perfect report feature (costs too much money)
  - may just be we add to the training material to pdf print certain tabs to start
  - 

## New Persona
See Training_Story.md, the executives want data!
- another persona, metrics across the data
  - Added to the training story personas
  - how many accounts does each ledger have?
  - how many transactions over time?
  - how much money has been moved? (per transaction type too)

## Data Evaluation / Test Enhancements
- Could given a postgresql database connection evaluate a dataset to see if it already has all the exception cases in it? report out on the command line some stats?
- We should include a database warm command with the testing commands

## App Info Tab
- The last sheet in each analysis should have the following technical information to help with troubleshooting
  - Should be added as something for the technical teams to know about in the handbook
- The version of the quicksight-gen app used to generate it
  - So version mismatches are detectable
- The most recent date of the transaction and daily balance tables
  - So the ETL jobs can be troubleshooted
- The most recent timestamp materialized views were updated
  - Since that could be the source of data mismatch problems

## Test Reliability
- **Fix the 5 PR FilterControl dropdown e2e tests that hang on dropdown open.** Failing both pre- and post-K.2 (so not a K.2 regression), every run, both parallel and serial:
  - `tests/e2e/test_filters.py::test_cashier_multi_select_narrows_sales`
  - `tests/e2e/test_filters.py::test_payment_method_narrows_payments`
  - `tests/e2e/test_filters.py::test_show_only_toggle_narrows_and_clears[Sales Overview-Show Only Unsettled-…]`
  - `tests/e2e/test_filters.py::test_show_only_toggle_narrows_and_clears[Settlements-Show Only Unpaid-…]`
  - `tests/e2e/test_filters.py::test_show_only_toggle_narrows_and_clears[Payments-Show Only Unmatched Externally-…]`
  - All time out after 30s in `_open_control_dropdown` (`tests/e2e/browser_helpers.py:942`) waiting on `[data-automation-id="sheet_control_value-menu"][data-automation-context="<title>"] [role="option"], [role="listbox"] [role="option"]`. The control card is found and clicked, but the MUI listbox popover never resolves under the expected selector.
  - Diagnostic path: screenshot the page after the click but before the timeout (the helper already saves to `tests/e2e/screenshots/payment-recon/`); inspect actual DOM for the listbox; reconcile with the selector. Likely a QuickSight UI change pushed the listbox out of the `data-automation-context`-scoped popover, breaking the first half of the selector union — the `[role="listbox"] [role="option"]` fallback may be matching a stale popover from a different control.
  - Same dropdown helper works for AR (Today's Exceptions multi-selects) — comparing the two pages' DOM should isolate what's PR-specific.
  - Acceptance: all 5 pass three runs in a row at `--parallel 4`. The full e2e suite goes from 156/161 → 161/161.

## Tech Debt
- Are there more invariants that are better encoded into the type system? K.2 did this for drill-param shape compatibility (`common/drill.py`: `ColumnShape` + `DrillParam` + `DrillSourceField` + `cross_sheet_drill()` refuse mismatched wirings at construction time) and codified the rule in `CLAUDE.md`. Plenty of stringly-typed wiring still elsewhere — sheet IDs, parameter names, filter group IDs, dataset identifiers, calc-field expressions referencing column names — each is a candidate for the same treatment when the next bug class motivates it.
