# Phase M — Whitelabel-V2 + L2 institutional model → v6.0.0

**Goal.** Land LAYER 2 (institutional model + library) per `SPEC.md`, port AR CMS + PR to L2-as-data as the validation case, then carry the rest of the product (CLI + dashboards + docs + training) along with it. v6.0.0 is the destination.

**Iteration model.** We do NOT know all the steps up front. The plan below sketches key milestones in expected order; each major milestone (M.X) ends with an explicit **iteration gate** where we replan the downstream sub-steps based on what surfaced. SPEC.md gets amended as we discover gaps; PLAN.md sub-steps regenerated. M.4 onward are deliberately sparse — they get fleshed out only after M.3's iteration gate.

**Product surface reminder.** `quicksight-gen` ships four things in lockstep — **CLI + dashboards + docs + training material**. Each milestone should make at least small progress in each area; M.0 is a deliberate full-vertical slice (touches all four minimally) to prove the pipeline shape works before scaling. Subsequent milestones broaden each area.

**L deferrals folded in.** L.5 (layer separation: default vs demo overlay) and L.8 (Executives handbook + walkthroughs) deferred from L land here naturally — both touch the persona/copy surface M is rewriting. Sub-folded into M.7 / M.8 below.

**Testing per-milestone, not deferred.** Each milestone (M.0 spike excepted) explicitly lands its testing surface as the layer is built — Phase L's kitchen-sink + L.1.18 validator-audit pattern carries forward. The rule: every new primitive gets a unit test, every new SPEC validation rule gets a rejection test, every layer gets at least one integration test exercising the layer above's contract, and every L2 instance gets a hash-lock for deterministic seed output. Tests prove the layer is built before we move on; we don't accumulate test debt to clear at M.9. M.0 carries a smoke test only — its job is shape-learning, not coverage; M.4–M.9 placeholders inherit the principle and get specific test sub-steps fleshed out at the iteration gate before each.

- [ ] **M.0 — Vertical-slice spike.** Smallest meaningful end-to-end through CLI → schema → data → dashboard → minimal docs. Validates the pipeline shape end-to-end before committing to library structure. Same approach as L.0 — surface what works on a tiny case, lift the working primitives into M.1+. Acceptance: a single `quicksight-gen apply --config slice.yaml` invocation produces a deployed dashboard showing one drift scenario, plus one rendered handbook page templated against the L2 instance's vocabulary.
  - [ ] M.0.1 — Pick scenario. Recommend: 2-account institution + 1 sub-ledger drift scenario. Smaller is better; spike's job is shape validation, not coverage.
  - [ ] M.0.2 — Hand-write `slice.yaml` per the L2 SPEC (1 InstancePrefix, 2 Accounts, 1 Rail, no Templates / Chains / Limits).
  - [ ] M.0.3 — Hand-code minimal library glue under `common/l2/_spike/`: YAML loader, prefixed schema SQL, drift-planting seed generator, one dashboard sheet (drift table + KPI), one handbook page.
  - [ ] M.0.4 — End-to-end: `apply schema` → `apply data` → `apply dashboards` → `generate training`. All four CLI commands stubbed minimally.
  - [ ] M.0.5 — One smoke test: load `slice.yaml`, run the pipeline, assert the planted drift row appears in the dashboard's drift exception table. One test only — spike's job is shape-learning, not coverage.
  - [ ] M.0.6 — Capture findings: what surprised us, what the SPEC missed, what code shape worked, what didn't.
  - [ ] M.0.7 — **Iteration gate** — amend `SPEC.md` if needed; replan M.1+.

- [ ] **M.1 — L2 library foundation.** Lift the spike's working glue into proper library modules. Typed YAML loader matching SPEC; all SPEC validation rules with rejection tests; prefix-aware SQL emission; Current* projection. Acceptance: `from quicksight_gen.l2 import load_instance, validate, ...` works; spike's `slice.yaml` loads through it cleanly; pyright strict on `common/l2/`.
  - [ ] M.1.1 — Typed dataclasses for L2 primitives (Account, AccountTemplate, Rail, TransferTemplate, ChainEntry, LimitSchedule, …) matching the SPEC tuples 1:1.
  - [ ] M.1.2 — YAML loader with friendly error messages (cite file/line for validation failures).
  - [ ] M.1.3 — All SPEC load-time validation rules (singleton ParentRole, ≤1 Variable leg per template, vocabulary literals for Completion/Cadence, single-leg reconciliation, XOR-group consistency, Aggregating-not-as-child) with one rejection test each.
  - [ ] M.1.4 — Prefix-aware SQL emission for L1 base tables (`<prefix>transactions`, `<prefix>daily_balances`) + L2 derived tables (`<prefix>accounts`, `<prefix>limits`, …).
  - [ ] M.1.5 — Current* SQL views for `Transaction` + `StoredBalance` per the SPEC's set-comprehension definitions.
  - [ ] M.1.6 — **Per-primitive unit tests** — one test per L2 primitive type (Account / AccountTemplate / Rail (each shape variant) / TransferTemplate / ChainEntry / LimitSchedule) covering load + emit + Current* projection.
  - [ ] M.1.7 — **Validation rejection tests** — one rejection test per SPEC load-time validation rule (singleton ParentRole, ≤1 Variable leg per template, vocabulary literals for Completion/Cadence, single-leg reconciliation, XOR-group consistency, Aggregating-not-as-child, etc.). Mirrors L.1.18 audit pattern — extends the audit table when new validators land.
  - [ ] M.1.8 — **Kitchen-sink L2 instance** under `tests/l2/_kitchen.yaml` exercising every primitive and every variant flag at least once. Loaded by a coverage test that asserts every primitive type appears; serves as both regression harness and worked-example documentation. The SPEC's end-to-end merchant-acquirer example is the natural starting point — extend it to cover anything it misses.
  - [ ] M.1.9 — pyright strict on `common/l2/`; pytest sessionstart hook checks gate (matches L.1.20.3).

- [ ] **M.2 — Port AR CMS as L2 instance.** AR first because its checks are mostly L1 invariants with light L2 scoping — exercises Roles + AccountTemplates + LimitSchedules + drift theorems against real complexity but no TransferTemplates / XOR / Aggregating. Acceptance: `apps/account_recon/app.py` consumes L2 instead of hardcoded constants; all AR exception checks render with the right scenario data; deployed dashboard matches today's AR functionally; one AR handbook page rendered against L2 vocabulary (proves templating works for a real app).
  - [ ] M.2.1 — Hand-write `sasquatch_ar.yaml` (8 GL singletons + customer/merchant DDA AccountTemplates + AR rails + LimitSchedules from today's `ar_ledger_transfer_limits`).
  - [ ] M.2.2 — Generate prefixed schema + data; verify drift / overdraft / limit-breach scenarios all surface (compare against today's seed where deterministic).
  - [ ] M.2.3 — Wire `apps/account_recon/app.py` to load the L2 instance and consume account dim / scope predicates from it; today's hardcoded `account_id` constants drop.
  - [ ] M.2.4 — All AR exception checks render correctly against the L2-driven app.
  - [ ] M.2.5 — One handbook page (e.g. `walkthroughs/account-recon/why-is-this-overdraft-firing.md`) rendered against L2 vocabulary; persona-substituted output matches what the existing handbook page says.
  - [ ] M.2.6 — **Integration test** — full pipeline (load `sasquatch_ar.yaml` → emit prefixed schema → plant seed → query CurrentStoredBalance / Drift / etc. → assert each AR exception type surfaces a known row). One end-to-end test per AR exception category.
  - [ ] M.2.7 — **Hash-lock the AR L2 seed output** — deterministic SHA256 across the generated SQL + planted rows, matches today's `tests/test_demo_data.py::TestDeterminism` pattern. Re-lock when intentional generator changes land.
  - [ ] M.2.8 — **No-regression run** — today's existing AR unit tests + AR API e2e tests pass post-port. Browser e2e gated on deploy access; mark as "verified at iteration gate" not blocking M.2.
  - [ ] M.2.9 — Capture SPEC gaps surfaced (especially around AccountTemplate-instance materialization and the per-customer subledger pattern).
  - [ ] M.2.10 — **Iteration gate** — amend `SPEC.md`, replan M.3+.

- [ ] **M.3 — Port PR as L2 instance.** PR is the harder app — exercises TransferTemplates with Variable closure (the merchant settlement cycle), single-leg rails, XOR Chains (settlement → {ACH | voucher | internal} payouts), AggregatingRails. The biggest stress test of the L2 SPEC. Acceptance: `apps/payment_recon/app.py` consumes L2; the sale → settlement → payment → external_txn pipeline checks all surface; PR mutual-filter pattern still works; one PR handbook page rendered from L2 vocabulary.
  - [ ] M.3.1 — Hand-write `sasquatch_pr.yaml` covering merchant settlement cycles + payout vehicle XOR group + external aggregation rail. (The end-to-end example in SPEC.md is deliberately abstracted to be near-this-shape — port should exercise whether it generalizes.)
  - [ ] M.3.2 — Generate prefixed schema + data; verify all PR exception scenarios (sale/settlement mismatch, settlement/payment mismatch, unmatched external, late, returns).
  - [ ] M.3.3 — Wire `apps/payment_recon/app.py` to consume L2.
  - [ ] M.3.4 — All PR exception checks + match aggregation render.
  - [ ] M.3.5 — One PR handbook page rendered against L2 vocabulary.
  - [ ] M.3.6 — **Integration test** — full pipeline against `sasquatch_pr.yaml`, asserts each PR exception type (sale/settlement mismatch, settlement/payment mismatch, unmatched external, late, returns) surfaces a known row.
  - [ ] M.3.7 — **Targeted primitive tests** — the hard L2 primitives that AR didn't exercise need their own tests: TransferKey grouping correctness (legs with matching keys join one Transfer; legs with mismatched keys don't); Variable closure correctness (the closing leg's amount + direction equal what's needed for ExpectedNet); XOR group enforcement (exactly one child Rail fires per parent Transfer instance); AggregatingRail bundling (the rail rolls up activity matching `BundlesActivity` on the declared Cadence).
  - [ ] M.3.8 — **Hash-lock the PR L2 seed output** — same shape as M.2.7.
  - [ ] M.3.9 — **No-regression run** — today's PR unit + API e2e tests pass.
  - [ ] M.3.10 — Capture SPEC gaps surfaced (especially around TransferKey runtime resolution + Variable closure semantics + XOR group scenario planting).
  - [ ] M.3.11 — **Iteration gate** — amend `SPEC.md`, replan M.4+.

- [ ] **M.4 — Port Investigation + Executives.** Lighter-weight — Inv is question-shaped (mostly read-side over the shared base ledger) and Exec aggregates over both. Both should consume the same L2 instances PR + AR produced rather than declare their own. Acceptance: all 4 apps build against L2 instances; full e2e suite green against the new pattern.
  - Sub-steps deferred until after M.3 iteration gate.

- [ ] **M.5 — Demo persona infrastructure + unified theme.** Sasquatch becomes N L2 instances (one per app, or per business context — decided after M.2 + M.3 land). Persona substitution wired so a fresh `quicksight-gen generate config demo > sasquatch.yaml` produces a runnable bundle. Includes the per-instance prefix story (each instance gets its own isolated table set per SPEC). Also lands the **unified theme** decision: today's per-app `sasquatch-bank` / `sasquatch-bank-ar` / `sasquatch-bank-investigation` split (per-app `cli.py::_apply_demo` `theme_preset` dict + `_generate_<app>(theme_preset=…)` defaults; Executives falls back to `sasquatch-bank` per L.6.8) collapses to one theme per persona — driven as an attribute of the L2 persona model, not as per-app preset selection.
  - Sub-steps deferred until after M.4 iteration gate.

- [ ] **M.6 — CLI workflow polish.** Materialize the full workflow from SPEC.md's "Workflow Ideas" section: `generate config (demo|template)`, `apply schema`, `apply data`, `apply dashboards`, `generate training`. Acceptance: a fresh integrator who's never seen the codebase can run the workflow end-to-end and get a deployed Sasquatch demo from one YAML file.
  - Sub-steps deferred until after M.5 iteration gate.

- [ ] **M.7 — Docs render pipeline (folds in L.5).** Handbook prose templated against L2 persona vocabulary. mkdocs render step that takes `(L2 instance, neutral templates) → rendered handbook`. Replaces today's `mapping.yaml` substitution. The deferred L.5 "always-emitted persona leaks" cleanup happens here naturally — under the new model, persona leaks are structurally impossible because all persona-vocabulary strings come from L2.
  - Sub-steps deferred until after M.6 iteration gate.

- [ ] **M.8 — Training render pipeline (folds in L.8).** Training site rendered from L2 + ScreenshotHarness regenerated per L2 instance. Includes the deferred L.8 Executives handbook + walkthroughs (no longer Sasquatch-Sasquatch-flavored prose; templated like the rest).
  - Sub-steps deferred until after M.7 iteration gate.

- [ ] **M.9 — Release v6.0.0.** Breaking-change cut. Bump version, write RELEASE_NOTES, tag, push, verify pipeline. The L1 entity field additions (Entry, ExpectedEODBalance, ExpectedNet, Origin, Limits, Transfer.Parent) are a breaking schema change for any integrator on v5; document the migration.
  - Sub-steps deferred until M.7 + M.8 land.

**Sequencing rationale.** M.0 is a vertical-slice spike — same approach as Phase L's L.0 (smallest possible scope, validate the shape, cherry-pick what works into the proper library). M.1 lifts the spike's working glue into typed library code. M.2 (AR CMS) ports first because its checks are mostly L1-invariant-with-light-scoping — easier landing pad for the L2 plumbing. M.3 (PR) is the real SPEC stress test (TransferTemplates, Variable closure, XOR Chains, AggregatingRails — almost every L2 primitive in flight). M.4 + M.5 round out the apps + persona story once the SPEC has settled. M.6–M.8 broaden the dashboard-only progress to CLI + docs + training. M.9 ships.

**Out of scope** (deferred per SPEC.md "Deliberately not in v1"):
- Cross-instance JOINs / federated analytics across L2 instances.
- Time-varying limit schedules.
- Per-leg `Origin` overrides.
- Failure-category catalogue formalization (adjacent concern; lives in a sibling doc once M lands).
- Scope predicates as a separate primitive (Roles + typed L1 fields cover v1).

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
