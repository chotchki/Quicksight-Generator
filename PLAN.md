# PLAN — Phase K: persona-driven layout work

K.1 + K.2 (+ v3.6.1 doc patch) + K.2a + K.3 + K.4 shipped — see `PLAN_ARCHIVE.md` for the rolled-up summaries and `RELEASE_NOTES.md` for the per-version detail.

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

### QuickSight URL-parameter control sync — known platform limitation (do not re-attempt without new evidence)

**The defect.** When a QuickSight dashboard URL sets a parameter via the fragment (`#p.<param>=<value>`), QS applies the value to the parameter store (visuals filter, "Reset" eventually shows blue after a hard refresh) but **does not push the value into the on-screen parameter / filter controls** bound to that parameter. The control widgets keep showing "All" even though data is filtered. Same defect affects QS's own intra-product Navigation Action with parameters — confirmed in [re:Post Q&A](https://repost.aws/questions/QUPWsGyb8wRNS8lojxfhkJmA/quicksight-navigation-action-with-parameters-doesn-t-update-the-controls-in-the-new-tab) and the [QuickSight community thread](https://community.amazonquicksight.com/t/values-of-filter-list-added-to-sheet-are-not-getting-updates-dynamically-based-on-parameter-passed-in-url/15355). AWS's own [parameters-in-a-URL doc](https://docs.aws.amazon.com/quick/latest/userguide/parameters-in-a-url.html) doesn't address it.

**Why we care.** A drill where filtered data and visible controls disagree is a non-user-obvious error that reduces analyst trust — worse than no drill. K.4.7 dropped its three Investigation → AR cross-app drills for this reason.

**Re-entry conditions** — re-attempt cross-app URL drills only if one of these flips:
1. AWS ships a fix (check the re:Post / community threads above; QS release notes for "URL parameter" or "navigation action" entries).
2. We re-architect to a custom embedded app and use the embedding SDK's `setParameters()` API, which DOES sync controls. Big scope; only justified if cross-app drilling becomes a load-bearing UX pattern across multiple personas.
3. Someone discovers a URL form / fragment syntax that triggers control sync. Low probability — the docs are silent and the existing form is well-trodden.

**Reuse for new URL features.** The dropped K.4.7 code (`CustomActionURLOperation` model, `cross_app_drill()` helper, `URLSourceColumn` + `url_column()`, `_build_url_template()`) is in git history at the commit prior to the K.4.7 revert — recoverable for any future static-link or non-parameterized URL action. **Don't** rebuild for a parameterized cross-app drill without one of the re-entry conditions above.

# Evolving the app
- The code base's approach still feels very constant heavy. I feel like we could move towards a builder pattern and greatly reduce the effort required.
  - Basically it feels like due to the hierchical nature of the Dasboards, we should be able to "build" up a tree structure that auto derives its IDs based off the title with separators, maybe first character of each title word separated by hyphens.
  - Example Structure (not complete):
    - App
      - Dashboard
        - Analysis
          - Sheet
            - Parameters
            - Filters
            - Visuals
          - Cross Sheet Filters
  - we can then pass the built objects to builds for actions/cross-sheet filters/etc instead of maintaining a huge list of constants
  - when we're ready to produce the json the tree and can recursively walk itself, calling the existing lower level classes and then producing final json
  - Would also allow for even stronger typing
  - This would be in common and the apps continue to be an opinionated implementation of this
