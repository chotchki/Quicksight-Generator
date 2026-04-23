# PLAN — Phase K: persona-driven layout work (shipped)

K.1 + K.2 (+ v3.6.1 doc patch) + K.2a + K.3 + K.4 shipped — see `PLAN_ARCHIVE.md` for the rolled-up summaries and `RELEASE_NOTES.md` for the per-version detail.

# PLAN — Phase L: tree walker + builder pattern → v5.0.0

Goal: replace the constant-heavy, manually-cross-referenced dashboard construction in `apps/{payment_recon,account_recon,investigation}/{analysis,filters,visuals}.py` with a tree of typed builder objects in `common/`. Each app becomes one of three things composed top-down:

1. **L1 — Tree primitives** (`common/`). Persona-blind. The QuickSight API surface plus type-safe composition: `App → Dashboard / Analysis → Sheet → (Parameters | FilterGroups | Visuals | Controls)` plus cross-sheet filter wiring. The tree resolves IDs and cross-references for you (FilterGroup scope refers to a Visual node, not a string ID); the existing `models.py` dataclasses stay as the JSON-emission layer.
2. **L2 — Default app assemblies** (`apps/`). Generic bank-domain implementations of PR / AR / Investigation / Executives — persona-agnostic in code, build dashboards every implementer's bank can deploy unchanged. These are *examples* of how to drive the tree, the way Sasquatch is the example data.
3. **L3 — Demo overlay**. The Sasquatch persona — theme preset, demo seed generator, persona-specific Getting Started copy — composed *on top of* the L2 default tree. Implementers replace this layer to ship their own brand without forking L2.

The tree's existence is the test case for the layer separation: anything Sasquatch-specific that leaks into L1 or L2 means the API isn't right yet.

**Locked decisions** (from review):
- **No auto-derived IDs.** Resource IDs stay explicit. Auto-deriving from titles risks breaking deployed dashboard URLs and drill targets when titles change; it also collides easily (first-letter schemes break on synonym titles). The tree wires references for you, but the IDs themselves are author-supplied.
- **Tree primitives are persona-blind.** No `Sheet.if_persona(...)` hooks; no persona threading through the constructors. Persona awareness lives in the L3 overlay layer that wraps or replaces L2 nodes. Easier to add a hook later than to rip one out.
- **Emit through the existing `models.py` dataclasses.** No parallel JSON emission path. The tree's job is to assemble + cross-reference + validate; `to_aws_json()` stays the serialization contract. Reduces L's blast radius and keeps the e2e structure tests valid against L's output.
- **Aim for byte-identical or documented-diff JSON during porting.** Anything else is a regression that needs explanation. The structural e2e tests are the contract.
- **Drop the aggregate constants** (`ALL_FG_AR_IDS`, `ALL_FG_PR_IDS`, `ALL_FG_INV_IDS`, `ALL_P_AR`, `ALL_P_INV`, etc.) as each app ports — the tree IS the source of truth, walking it produces the same set.
- **Executives is the greenfield proof.** Build it on the tree from scratch as L.6 — proves the API works for first-time authors, not just for porting existing apps. Ships as a fourth Sasquatch app in L; re-shapes into the Phase M whitelabel model later.

- [ ] **L.0 — Tree spike (`spike/l-tree-account-network` branch).** Smallest possible port to validate the tree primitives produce JSON that the existing `models.py` accepts and that the deployed dashboard renders unchanged. Sketch the L1 types (`App`, `Dashboard`, `Sheet`, `Visual`, `FilterGroup`, `ParameterDecl`, `FilterControl`, `ParameterControl`) just enough to cover one sheet; port `_build_account_network_sheet()` from `apps/investigation/analysis.py` to the tree; diff the emitted JSON against `out/investigation-dashboard.json`'s Account Network sheet. **Acceptance:** byte-identical (or documented-semantic-equivalent) JSON for the Account Network sheet; deployed dashboard renders without regression. **If fail:** capture the failure mode (cross-reference resolution? ID collision? emission gap with the existing models?) and redesign the tree's API or emit interface before any L.1 work. Findings captured in this plan; spike branch either cherry-picks the validated primitives into L.1 or dies on the spike branch.
- [ ] **L.1 — Tree primitives in `common/`.** New module(s) under `common/` (working name `common/tree.py`; split if it grows past ~600 lines). Types: `App` (root, holds dashboards + analyses + datasets + theme reference), `Dashboard`, `Analysis`, `Sheet`, `ParameterDecl`, `FilterGroup`, `Visual` (one subtype per visual kind we use today — KPI, table, bar, Sankey, etc., or a single `Visual` with a typed `kind`), `FilterControl`, `ParameterControl`, `CrossSheetFilter`. Cross-reference helpers: a FilterGroup's scope takes `[Visual]` references, not bare IDs; a drill action's destination takes a `Sheet` reference. The tree walks itself to emit the existing `Analysis` + `Dashboard` instances from `models.py` — no parallel JSON model. Validation hooks at construction time (e.g. `FilterGroup.validate_scope()` ensures every scoped visual is on the same sheet) per the encode-invariants-in-types rule. Tests: tree assembly, ID resolution, cross-reference resolution, JSON emission shape, builder ergonomics. **Acceptance:** primitives module shipped with full unit coverage; `to_aws_json()` over a tree-built `App` produces output that round-trips through deploy paths (no missing fields).
- [ ] **L.2 — Port Investigation to the tree.** Smallest existing app + freshest code = lowest port risk and the natural follow-on to the L.0 spike. Rewrite `apps/investigation/analysis.py` + `filters.py` + `visuals.py` against the tree; `datasets.py` + `demo_data.py` + `etl_examples.py` unchanged. Drop `ALL_FG_INV_IDS` + `ALL_P_INV` from `constants.py` (the tree is the source of truth — update the e2e structure tests to walk the tree's emitted set, not the constants module). **Acceptance:** byte-identical (or documented-diff) `investigation-analysis.json` + `investigation-dashboard.json`; full unit suite green; e2e green at deploy time (28 Investigation tests + 3 deferred K.4.9 skips unchanged).
- [ ] **L.3 — Port Account Reconciliation to the tree.** Largest existing app (5 sheets, 14 exception checks, ~20 filter groups, ~80 visuals) — tests the tree primitives against the worst-case complexity. Drop `ALL_FG_AR_IDS` + `ALL_P_AR` aggregates. **Acceptance:** byte-identical AR JSON; full unit suite green; e2e green.
- [ ] **L.4 — Port Payment Reconciliation to the tree.** Medium complexity; the Payment Reconciliation tab's side-by-side mutual-filter pattern is the only PR-special-case the tree needs to express cleanly. If the existing 5 PR FilterControl dropdown e2e tests (Test Reliability backlog item below) trace to a structural pattern the tree can refactor away, fix them as part of the port; otherwise leave them in the backlog. Drop PR's filter group + visual ID aggregates. **Acceptance:** byte-identical PR JSON; full unit suite green; e2e green.
- [ ] **L.5 — Layer separation: default vs demo overlay.** With all three apps ported, audit the L1 + L2 surface for persona leaks. Grep `common/` and `apps/` for "Sasquatch", "SNB", merchant names, demo account IDs — each leak is either pushed into the L3 overlay (if persona-specific) or generalized (if structural). Make the demo theme preset selection explicit: default tree builds against `default` theme; demo overlay opts into `sasquatch-bank*`. Move persona-specific copy from sheet rich text + sheet descriptions into the L3 overlay layer (today the Investigation Getting Started mentions "Sasquatch National Bank shared base ledger" — that copy belongs to demo, not default). Document the three-layer model in `CLAUDE.md` under Architecture Decisions. **Acceptance:** `quicksight-gen generate --all` against a non-demo config produces a fully-rendering generic dashboard with zero Sasquatch references; `demo apply --all` continues to produce the Sasquatch-flavored output it does today.
- [ ] **L.6 — Executives app on the new tree from scratch.** Greenfield use of the tree pattern as the proving ground that the API works for first-time authors, not just for porting existing apps. Per Training_Story.md: counts across the data, transactions over time, money moved per type. Likely 3–4 sheets — Getting Started + Account Coverage (counts per ledger / sub-ledger / customer / merchant / etc.) + Transaction Volume Over Time (line charts per `transfer_type`) + Money Moved (totals per rail / per type, period-over-period). New `apps/executives/` package; new theme preset `sasquatch-bank-executives` (or reuse default + Sasquatch overlay). Reads the same shared `transactions` + `daily_balances` base tables — no new schema; matview only if a query chokes Direct Query. Cross-app drill into AR Transactions for any "show me the rows" on a metric. Demo seed: probably none — executives reads the shape the other apps already plant. Hash-lock the dataset SQL projection contracts. **Acceptance:** 4th app deploys alongside the other 3; full unit + e2e suites green; the L.6 author writes ~no `constants.py` (the tree carries the IDs).
- [ ] **L.7 — Browser e2e for Executives.** Mirror the K.4.9 / AR e2e shape. New conftest fixtures (`exec_dashboard_id`, `exec_analysis_id`, `exec_dataset_ids`); new `test_exec_*.py` files for deployed-resources / dashboard structure / dashboard renders / sheet visuals; filter + drill tests as appropriate to the visuals built in L.6. **Acceptance:** ~20–25 new tests collected; full e2e suite green.
- [ ] **L.8 — Executives handbook + walkthroughs.** New `docs/handbook/executives.md` + walkthroughs per sheet's core question ("How many accounts do we have, and how is that growing?"; "How many transactions are we processing per month?"; "How much money have we moved in the last quarter?"; "Which transfer types are growing or shrinking?" — final list depends on L.6 sheet shape). Frame the executives team as a fourth persona — exec / board reporting cadence, scan-for-trends posture, drill into the operational sheets when something looks off. `mkdocs.yml` nav extended after Investigation; `docs/index.md` updated to count four apps + surface the executives handbook. **Acceptance:** `mkdocs build --strict` clean.
- [ ] **L.9 — Test refresh + handbook + CLAUDE / README / PLAN updates.** New "Tree pattern" section in `CLAUDE.md` under Architecture Decisions covering L1 → L2 → L3 layering and the "Sasquatch lives only in L3" rule. README updates to count four apps and replace the constants-driven framing with the tree-driven one. New customization handbook walkthrough: "How do I author a new app on the tree?" — the L.6 work is the worked example. Drop the "Constant-heavy" bullets from PLAN.md's "Evolving the app" section (the work the section called for is now done). **Acceptance:** `mkdocs build --strict` clean; `pytest` green; all docs accurate against the post-L codebase.
- [ ] **L.10 — Release as v5.0.0 (major).** Earned by: internal API change (external callers importing `quicksight_gen.apps.*.analysis` / `.filters` / `.visuals` for programmatic dashboard construction need to update — the new public surface is the `common/` tree); the new Executives app; the layer-separation cleanup. RELEASE_NOTES.md describes the tree pattern, the layer model, the apps porting, the new Executives app, and the migration path for external callers. Per the project's no-backwards-compat-shims rule, no compatibility re-exports of the old per-app builder modules.

**Sequencing.** L.0 first — the tree spike's only job is to validate that the L1 API can produce JSON the existing models accept; if it can't, redesign before any porting. L.1 lands the full primitives once the spike validates. Port apps L.2 → L.3 → L.4 in increasing complexity (Investigation smallest, AR largest) so each port stress-tests the API a little more than the previous one. L.5 (layer separation) lands after porting because we can't see the persona-specific surface clearly until all three apps are on the tree. L.6 (Executives greenfield) follows L.5 so it's built against the cleaned-up two-layer API. L.7–L.8 (e2e + handbook for Executives) mirror the K.4.9 → K.4.10 shape and stack at the end where everything they reference exists. L.9 sweeps the docs. L.10 publishes.

**Out of scope** (queued for Phase M or later):
- Whitelabel-V2 (relationship/flow modeling for demo data) — Phase M headline.
- Docs/training tree merge + template-rendered docs — bundled into Phase M with whitelabel-V2 as one initiative (the persona dataclass should drive both the seed generator AND the doc renderer in lockstep).
- CLI scope revisit — its role is changing as customization extends; revisit in M or later once the new tree + whitelabel layers settle.
- App Info tab, Audit Enhancements, Data Evaluation tooling, the 5 PR FilterControl dropdown e2e tests (unless L.4 incidentally fixes them) — stay in backlog.

# Phase M — Whitelabel-V2 + docs/training (preview)

Will be planned in detail when L lands. Headline: replace today's string-substitution whitelabel (one canonical Sasquatch copy + a `mapping.yaml` substitution at export time) with a relationship/flow-aware persona model — define what an institution looks like operationally (account topology, settlement cadences, customer mix, rail composition, scenario shapes) as a typed dataclass, then have a deterministic generator consume that model and emit both the seed SQL **and** the rendered handbook/training content in lockstep. The persona is the source of truth; every shipped artifact is rendered from it.

Bundles in three currently-queued items:
- Whitelabel-V2 (the relationship/flow modeling layer + generator)
- Docs/Training Tree Merge (deferred from K.4.1)
- Template-rendered docs (replaces string-substitution whitelabel)

CLI scope revisit likely lands here too — `quicksight-gen` grows from a generator/deployer into a customization platform, and `export training` / `export docs` / `whitelabel apply` may collapse or restructure. Decide at M kickoff.

# Backlog - Phase N+ Candidates

## Audit Enhancements
- How can someone show the state of the system durably?
  - This could be columns on the daily statement, show the percentage of each transaction row that matches perfectly to its other legs
  - This is to support reporting to auditors/regulators
  - should not use the pixel perfect report feature (costs too much money)
  - may just be we add to the training material to pdf print certain tabs to start

## Data Evaluation / Test Enhancements
- Could given a postgresql database connection evaluate a dataset to see if it already has all the exception cases in it? report out on the command line some stats?

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
  - Acceptance: all 5 pass three runs in a row at `--parallel 4`. Try fixing as part of L.4 (PR port); if the structural pattern doesn't naturally refactor away, leave here.

## Tech Debt
- Are there more invariants that are better encoded into the type system? K.2 did this for drill-param shape compatibility (`common/drill.py`: `ColumnShape` + `DrillParam` + `DrillSourceField` + `cross_sheet_drill()` refuse mismatched wirings at construction time) and codified the rule in `CLAUDE.md`. Phase L's tree primitives close another big chunk by encoding parent-child structure and cross-reference shape; what remains after L is the candidate list for the next round.

### QuickSight URL-parameter control sync — known platform limitation (do not re-attempt without new evidence)

**The defect.** When a QuickSight dashboard URL sets a parameter via the fragment (`#p.<param>=<value>`), QS applies the value to the parameter store (visuals filter, "Reset" eventually shows blue after a hard refresh) but **does not push the value into the on-screen parameter / filter controls** bound to that parameter. The control widgets keep showing "All" even though data is filtered. Same defect affects QS's own intra-product Navigation Action with parameters — confirmed in [re:Post Q&A](https://repost.aws/questions/QUPWsGyb8wRNS8lojxfhkJmA/quicksight-navigation-action-with-parameters-doesn-t-update-the-controls-in-the-new-tab) and the [QuickSight community thread](https://community.amazonquicksight.com/t/values-of-filter-list-added-to-sheet-are-not-getting-updates-dynamically-based-on-parameter-passed-in-url/15355). AWS's own [parameters-in-a-URL doc](https://docs.aws.amazon.com/quick/latest/userguide/parameters-in-a-url.html) doesn't address it.

**Why we care.** A drill where filtered data and visible controls disagree is a non-user-obvious error that reduces analyst trust — worse than no drill. K.4.7 dropped its three Investigation → AR cross-app drills for this reason.

**Re-entry conditions** — re-attempt cross-app URL drills only if one of these flips:
1. AWS ships a fix (check the re:Post / community threads above; QS release notes for "URL parameter" or "navigation action" entries).
2. We re-architect to a custom embedded app and use the embedding SDK's `setParameters()` API, which DOES sync controls. Big scope; only justified if cross-app drilling becomes a load-bearing UX pattern across multiple personas.
3. Someone discovers a URL form / fragment syntax that triggers control sync. Low probability — the docs are silent and the existing form is well-trodden.

**Reuse for new URL features.** The dropped K.4.7 code (`CustomActionURLOperation` model, `cross_app_drill()` helper, `URLSourceColumn` + `url_column()`, `_build_url_template()`) is in git history at the commit prior to the K.4.7 revert — recoverable for any future static-link or non-parameterized URL action. **Don't** rebuild for a parameterized cross-app drill without one of the re-entry conditions above.
