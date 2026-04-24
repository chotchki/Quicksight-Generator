# PLAN — Phases K + L: shipped (see archive)

K.1 + K.2 (+ v3.6.1 doc patch) + K.2a + K.3 + K.4 shipped — see `PLAN_ARCHIVE.md` for the rolled-up summaries and `RELEASE_NOTES.md` for the per-version detail.

L.0 – L.4, L.6, L.7, L.9, L.10, L.11 shipped as **v5.0.2** — see `PLAN_ARCHIVE.md` for the rolled-up Phase L summary and `RELEASE_NOTES.md` for the per-version detail. L.5 + L.8 deferred to Phase M (below) — both touch persona/copy surfaces M is rewriting, so the intermediate work would just get redone.

# Phase L deferrals — context preserved for Phase M kickoff

- [~] **L.5 — Layer separation: default vs demo overlay.** **Deferred to Phase M (Whitelabel-V2).** Phase M's headline is replacing today's persona model with a typed dataclass that drives seed SQL + handbook + dashboard render in lockstep — L.5's overlay extraction would be the throwaway intermediate step. Today's single-persona / no-customer-asking-for-non-demo state has nothing forcing the separation. The two costs of deferral are (a) two always-emitted persona leaks ship in non-demo dashboards (`apps/investigation/app.py:210` + `apps/account_recon/app.py:1062` — cosmetic, easy hotfix if it matters), and (b) the L.5 audit findings would re-surface at M kickoff — preserved here so they don't.

  **L.5.1 + L.5.2 audit findings (preserved for Phase M kickoff):**

  *Category A — always-emitted persona leaks (break "zero Sasquatch in non-demo"):*
  - `apps/investigation/app.py:210` — Getting Started intro: "Compliance / AML triage surface for the Sasquatch National Bank shared base ledger."
  - `apps/account_recon/app.py:1062` — Two-Sided Post Mismatch KPI subtitle: "...one side of an expected SNB/Fed post pair landed but the other side never did."

  *Category B — demo-conditional flavor blocks (already gated by `if cfg.demo_database_url:`):*
  - `apps/payment_recon/app.py` — Sasquatch coffee-shop demo block (~13 lines).
  - `apps/account_recon/app.py` — Sasquatch CMS demo block (~50 lines).
  - Investigation has no demo-conditional path — its persona text is unconditional (Category A above).

  *Category C — already-isolated, intentional:*
  - `common/persona.py` — `SNB_PERSONA` substitution dict (K.2a.5 — feeds `mapping.yaml.example` derivation).
  - `common/theme.py` — Sasquatch theme presets (themes ARE personas).
  - `common/dataset_contract.py:63` — single docstring example mentioning "Sasquatch Sips (gl-1850)"; rephraseable as a one-line cleanup.
  - `apps/<app>/demo_data.py` — demo SQL generators (persona is the point).
  - `apps/<app>/etl_examples.py` — ETL example files (these ARE examples, persona-by-design).

  *Recommended overlay shape (notes for M):* extract demo flavor copy into `apps/<app>/_demo_copy.py` sibling modules; the `if is_demo:` branches in `app.py` import from `_demo_copy`. Smaller than the (a) wrapper / (b) composition shapes and keeps persona text near its consumer. **Note:** if Phase M moves to a fully persona-dataclass-driven render pipeline, this whole approach gets replaced — that's why deferring is correct.

- [ ] **L.8 — Executives handbook + walkthroughs.** **Deferred to Phase M.** All this prose touches the persona surface M is rewriting; cleaner to write the Executives handbook against the new persona-dataclass-driven render pipeline than to write Sasquatch-flavored copy that immediately gets redone.
  - [ ] L.8.1 — Read the L.6 sheet shape; draft the question per sheet that becomes a walkthrough title.
  - [ ] L.8.2 — Draft `docs/handbook/executives.md` overview. Frame the executives team as a fourth persona — exec / board reporting cadence, scan-for-trends posture, drill into the operational sheets when something looks off.
  - [ ] L.8.3 — Draft 3–4 walkthroughs in `docs/walkthroughs/executives/*.md` (one per sheet's question). Mirror the established Story → Question → Where to look → What you'll see in the demo → What it means → Drilling in → Next step → Related shape.
  - [ ] L.8.4 — Update `mkdocs.yml` nav: add Executives Handbook block after Investigation.
  - [ ] L.8.5 — Update `docs/index.md` to count four apps; surface the Executives handbook in the Operator handbooks section.
  - [ ] L.8.6 — Verify `mkdocs build --strict` clean.

# Phase M — Whitelabel-V2 + docs/training (preview)

Will be planned in detail when L lands. Headline: replace today's string-substitution whitelabel (one canonical Sasquatch copy + a `mapping.yaml` substitution at export time) with a relationship/flow-aware persona model — define what an institution looks like operationally (account topology, settlement cadences, customer mix, rail composition, scenario shapes) as a typed dataclass, then have a deterministic generator consume that model and emit both the seed SQL **and** the rendered handbook/training content in lockstep. The persona is the source of truth; every shipped artifact is rendered from it.

Bundles in three currently-queued items:
- Whitelabel-V2 (the relationship/flow modeling layer + generator)
- Docs/Training Tree Merge (deferred from K.4.1)
- Template-rendered docs (replaces string-substitution whitelabel)

CLI scope revisit likely lands here too — `quicksight-gen` grows from a generator/deployer into a customization platform, and `export training` / `export docs` / `whitelabel apply` may collapse or restructure. Decide at M kickoff.

**Unified theme across all 4 dashboards** — today the apps default to three different Sasquatch presets (`sasquatch-bank` / `sasquatch-bank-ar` / `sasquatch-bank-investigation`), each designed during its app's phase to be "visually separable so analysts can tell at a glance which one they're in" (per `common/theme.py` comments). With L.6 shipping a 4th app and the product hardening into a four-dashboard surface, the right call is to reverse that decision: one persona = one bank = one theme. Phase M is the natural home because (a) the persona-dataclass redesign naturally drives theming as a persona attribute, and (b) picking a unified palette is a deliberate design exercise (a colour scheme that works for executive board reports AND fraud investigation alerts AND merchant ops AND treasury reconciliation), not a 5-line CLI swap. Deferred per the same logic that deferred L.5 — a small intermediate fix today would just get redone in M. **Audit findings preserved for M kickoff:** today's per-app preset mapping lives in `cli.py::_apply_demo`'s `theme_preset` dict and in the `_generate_<app>(theme_preset=…)` defaults; the 3 SNB presets live in `common/theme.py::PRESETS`. None of the L.4–L.6 ports created new presets — Executives reuses `sasquatch-bank` as a fallback (L.6.8 decision).

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
