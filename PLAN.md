# PLAN — Phase K: persona-driven layout work

K.1 + K.2 (+ v3.6.1 doc patch) + K.2a + K.3 shipped — see `PLAN_ARCHIVE.md` for the rolled-up summaries and `RELEASE_NOTES.md` for the per-version detail.

## K.4 — Investigation app (third app: AML + general investigation) → v4.0.0

Goal: new `quicksight_gen.apps.investigation` package (third app alongside PR + AR), mirroring the existing two-app pattern. Reads from the same `transactions` + `daily_balances` base tables — no schema changes (K.3's `expected_complete_at` is already there for free). Bundles a 4.0.0-earning re-org of `payment_recon/` + `account_recon/` under a new `apps/` namespace and a docs/training tree cleanup, so the major bump packs real structural work, not just an additive third app.

Build feasibility-driven (Sankey first because it's the only step that could fail outright; rest are aggregation / window-function SQL on shared base tables, well-trodden ground). Within the build phase, ship sheets incrementally — the app should be usable after K.4.4, not only at K.4.6.

**Locked decisions** (from review): package name `investigation`, not `aml_recon`; recursive CTE runs in the database via standard `WITH RECURSIVE` (Postgres 17 supports it; portable per the project constraint); matviews bundled into the existing `Schema_v3.md` matview section + `handbook/etl.md` REFRESH contract as each query lands; demo data is a new `investigation/demo_data.py` writing into the shared base tables; cross-app drills wired (investigation → AR Transactions for underlying rows; investigation → PR Payment Reconciliation for payment chain context). Reorg under `apps/` namespace + docs/training tree cleanup ride along to earn 4.0.0.

- [ ] **K.4.0 — Sankey feasibility spike (`spike/k4-sankey` branch).** Validate `WITH RECURSIVE` → QuickSight native Sankey on the existing PR `parent_transfer_id` chains (`external_txn → payment → settlement → sale`, already 4 hops in the seed). Steps: write the recursive CTE by hand against a `demo apply`'d Postgres and confirm `(source_account, target_account, hop_amount, depth)` projection shape; build a minimal `spike_investigation/analysis.py` with one Sankey visual on a custom-SQL dataset; deploy to AWS, render in browser, screenshot. **Acceptance:** Sankey visual renders a 4-hop chain end-to-end with one node per account and edge weights matching `hop_amount`. **If fail:** capture the failure mode (node cap? rendering bug? edge type mismatch?) and redesign K.4.6 around the fallback hop-by-hop table before any other K.4 work starts. Findings captured in this plan; spike branch either cherry-picks the validated SQL/dataset shape into K.4.6 or dies on the spike branch.
- [x] **K.4.1 — Reorg under `apps/` namespace + obsolete-script cleanup.** Mechanical re-org earning the 4.0.0 bump. Move `src/quicksight_gen/payment_recon/` → `src/quicksight_gen/apps/payment_recon/` and `account_recon/` → `src/quicksight_gen/apps/account_recon/`; update every import across src + tests + scripts to `quicksight_gen.apps.{payment_recon,account_recon}`; update `pyproject.toml` package discovery if needed (likely auto-handled by setuptools find). Drop the two obsolete training scripts that v3.4.0 superseded but didn't delete: `src/quicksight_gen/training/distribute.py` (zips the handbook — replaced by `quicksight-gen export training`'s folder copy) and `src/quicksight_gen/training/publish.py` (string substitution — duplicated by `whitelabel.py` which `export training` already uses). Result: `src/quicksight_gen/training/` becomes pure content (handbook/, QUICKSTART.md, mapping.yaml.example). `src/quicksight_gen/docs/` (operator handbook, mkdocs source) and `src/quicksight_gen/training/` (audience-organized cross-training, whitelabel-able) stay separate — different audiences, different export paths (`export docs` vs `export training`). Revisit merging the two handbook trees in Phase L once K.4 lands a few more targeted training examples; today's split is the right call. **Acceptance:** fresh `pip install -e .` succeeds; `quicksight-gen --version` runs; `mkdocs serve` builds; full pytest suite green.
- [ ] **K.4.2 — App skeleton.** New `src/quicksight_gen/apps/investigation/` mirroring `account_recon/` layout (`analysis.py`, `visuals.py`, `filters.py`, `datasets.py`, `demo_data.py`, `constants.py`, `etl_examples.py`). Wire into CLI (`generate`, `deploy`, `demo apply` accept `investigation` as a third app — alias `inv` if the full word is too long for ergonomics). New theme preset `sasquatch-bank-investigation`. Empty Getting Started sheet + 3 stub sheets named for K.4.3 / K.4.4 / K.4.5.
- [ ] **K.4.3 — Person-to-person fanout sheet** (easiest: straight aggregation). Dataset: COUNT DISTINCT senders + SUM(amount) per recipient sub-ledger over a chosen window, derived from `transactions` joined on `transfer_id`. Visual: KPI (total recipients with N+ distinct senders) + ranked table sorted by fanout count. Filter: window length, fanout threshold. Cross-app drill on a row → AR Transactions filtered to the recipient `account_id`. Likely no matview needed; revisit if the date-range filter chokes.
- [ ] **K.4.4 — Sliding-window statistical anomaly sheet** (moderate: WINDOW functions + std-dev). Dataset: rolling SUM(amount) per sender→recipient pair over a 2-day window, with a population baseline mean + std-dev computed across the same window family; flag rows where window sum > mean + 2σ. Visual: distribution plot + flagged-rows table. Filter: σ threshold (default 2), window length (default 2 days). **Materialize this view** — pair × rolling window across all transfers is the worst-case query in the app; add to `Schema_v3.md` matview section + `handbook/etl.md` REFRESH contract. Cross-app drill on a flagged row → AR Transactions filtered to the pair + window.
- [ ] **K.4.5 — Money-trail provenance sheet** (hardest, validated in K.4.0). Dataset: recursive CTE walking up/down `parent_transfer_id` chains from a starting transfer_id, flattened to one row per edge — `(source_account, target_account, hop_amount, depth)`. Visual: Sankey as the headline; hop-by-hop detail table beside it for legibility + rows Sankey hides. Filter: starting transfer_id, max hops, min hop amount. **Materialize the per-starting-transfer pre-walked edge set** if K.4.0 finds Direct Query latency unacceptable — add to matview catalogue alongside K.4.4. Fallback (if K.4.0 found Sankey can't render): hop-by-hop table is the primary, with a "chain too wide for Sankey" notice in the subtitle. Cross-app drill on an edge → PR Payment Reconciliation if the edge involves an external_txn / payment / settlement; AR Transactions otherwise.
- [ ] **K.4.6 — Investigation demo data + cross-app scenario coverage.** New `apps/investigation/demo_data.py` writing into the shared `transactions` + `daily_balances`. Plant scenario rows exercising each sheet: a fanout cluster (10+ senders → 1 recipient), a 2σ-anomalous window pair, and a 4-hop transfer chain (separate from the existing PR chain so investigation has its own headline scenario). Same-persona (Sasquatch National Bank — Compliance / Investigation team) consistent with PR/AR. Add `TestScenarioCoverage` assertions in `tests/test_investigation_demo_data.py`. Lock the per-app SHA256 seed hash. Verify scenarios drill back into AR Transactions correctly (cross-app drill smoke test).
- [ ] **K.4.7 — Browser e2e for investigation.** `tests/e2e/test_investigation_*.py` mirroring AR's coverage shape: deployed resources exist, dashboard structure correct, sheet visuals render, filters scope correctly, drill-downs land (including cross-app drills into AR/PR). One Sankey-specific test: render-to-completion within the visual timeout.
- [ ] **K.4.8 — Investigation Handbook + walkthroughs.** New `docs/handbook/investigation.md` + `docs/walkthroughs/investigation/*.md`. Three walkthroughs minimum, one per sheet's core question ("Who's getting money from too many senders?", "Which sender→recipient pair just spiked?", "Where did this transfer actually originate?"). Add to `mkdocs.yml` nav after PR. Cross-link Schema_v3 (no schema change but the matviews added in K.4.4 / K.4.5 land in the matview catalogue and need REFRESH coverage).
- [ ] **K.4.9 — Release as v4.0.0 (major).** Earned by: the `apps/` re-org breaks import paths for any external consumer; the docs/training tree cleanup changes file locations; the new investigation app + its matviews + cross-app drills are the headline feature; cumulative scope across K.4.0 – K.4.8. RELEASE_NOTES.md describes the import path changes, the new app, the new matviews + REFRESH contract additions, and the docs reorg. Per the project's "no backward-compat shims" rule, no compatibility shim for the old import paths.

**Sequencing.** Sankey spike (K.4.0) **first** — if it fails, the whole money-trail sheet redesigns and we don't want to have already shipped the reorg + skeleton + cross-app drill wiring against the wrong assumptions. After spike result: reorg (K.4.1) lands as one mechanical commit before any new investigation code so K.4.2+ writes against the final layout. Then build the three sheets fanout → window → provenance (easy → moderate → hardest, each shippable as it lands). Demo data + cross-app drills + e2e + handbook stack at the end where everything they reference exists. v4.0.0 release is the last sub-phase.

# Backlog - Phase L Candidates

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

## Docs/Training Tree Merge (deferred from K.4.1)
- Today `src/quicksight_gen/docs/` (operator handbook, mkdocs source) and `src/quicksight_gen/training/` (audience-organized cross-training, whitelabel-able via `quicksight-gen export training`) are separate trees with separate export paths and different audiences. K.4.1 kept them split because the audiences genuinely differ today. Revisit after K.4.x lands more targeted training examples — once the training/handbook content has expanded with the investigation app's scenarios, the audience boundary may blur enough that a single mkdocs-buildable tree (with audience-tagged sections) becomes feasible. If we merge: training/ becomes a sub-tree under docs/, `export training` either dies or becomes `export docs --audience trainee`, and whitelabel substitution needs to know which docs/ subpaths to walk.

## Template-rendered docs (replaces string-substitution whitelabel)
- K.4.1 inlined `whitelabel.py` into `cli.py` as Option A from a discussion that also surfaced Option C for later: replace the string-substitution model entirely with template-rendered docs. Docs become Jinja templates (or similar) that take a persona object — the canonical Sasquatch strings stop being load-bearing because every shipped doc is generated from `common/persona.py` at export time, with the user-supplied persona swapped in. Wins: no leftover-canonical-string warnings, no mapping.yaml maintenance burden, schema-typed control over substitution scope (the persona is a dataclass — adding a field is a Python change, not a string-mapping change). Costs: every shipped doc has to grow placeholder syntax, and the "human-readable canonical copy" disappears as a directly-viewable artifact (you have to render to see what the SNB version actually reads like). Pairs naturally with the docs/training merge above — both rework how shipped content is structured. Decide in Phase L kickoff whether to do them together or stage.

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
