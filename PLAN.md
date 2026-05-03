# QuickSight Generator — Active Plan

**Where we are.** v8.0.0 shipped (Q.3.a CLI redesign — four artifact groups, emit/--execute pattern). Historical detail for every phase prior to v8.0.0 lives in `PLAN_ARCHIVE.md` and `RELEASE_NOTES.md`. This file tracks **forward-looking** work only.

---

## Phase history (one-line per shipped phase)

- **Phase N** (v6.1.0) — Investigation + Executives ported onto L1/L2 tree primitives; theme moved to L2 YAML attribute; preset registry dropped. Full detail: `PLAN_ARCHIVE.md`.
- **Phase O** (v6.2.0) — Unified docs render pipeline with mkdocs-macros + `HandbookVocabulary`; per-app handbooks render against any L2 instance.
- **Phase P** (v7.x cumulative) — Dialect-aware schema + dataset emission; Postgres + Oracle CI matrix; Phase R seed pipeline foundations.
- **Phase Q.1** — Dashboard polish: USD currency formatting via `Measure(currency=True)`, universal date-filter sweep, Oracle case-fold wrapper for `ORA-00904`.
- **Phase Q.2** — Doc IA cleanup; Shape C audience-first home; persona-leak sweep across handbook + walkthroughs.
- **Phase Q.4** (v7.3.0) — Persona-neutral docs release; new `persona:` block on L2 YAML; CI gate for persona-token leakage.
- **Phase Q.5** — Persona-neutral docs full L2-driven substitution; Investigation walkthroughs split into mechanics + worked-example admonitions.
- **Phase Q.3.a** (v8.0.0) — CLI redesign: four artifact groups (`schema | data | json | docs`); each `apply`/`clean` defaults to emit, `--execute` opts in to side effects; `cli_legacy.py` deleted; bundled JSON emit (no per-app filter).
- **Phase R** (v7.2.0) — 90-day per-Rail healthy baseline + embedded plant overlays (densify×5, broken×15, inv-fanout×5); Volume Anomalies signal real on the seed; lognormal amount distribution.
- **Phase S** — Research: drop the system `dot` binary. Spiked Mermaid+ELK (failed eyeball — self-loops floated, layout fidelity poor) and graphviz WASM via `@hpcc-js/wasm-graphviz` (passed — byte-identical to graphviz/dot). Verdict written into RELEASE_NOTES + git log; Phase T executed the migration.
- **Phase T** (v8.1.0) — Every diagram now renders client-side via `@hpcc-js/wasm-graphviz`. `render_*` helpers return DOT strings; `<template class="qs-graphviz-source">` blocks inside `<figure>` wrappers; ~50-line JS shim does the WASM render. 5 `apt-get install graphviz` lines deleted across CI / Release / Pages workflows.
- **Phase U** (v8.2.0) — Audit Reconciliation Report. Fifth artifact group (`audit`) ships `apply` / `clean` / `verify` / `test` verbs that emit a regulator-ready PDF (cover + exec summary + per-invariant violation tables + per-account Daily Statement walks + sign-off + provenance appendix) bound by a four-input SHA256 fingerprint (`tx hwm + bal hwm + l2 yaml + code identity`); optional pyHanko auto-sign. Release-gate U.8.b's three-way contract (`expected == PDF == dashboard`) verified live across **6 invariants × 2 dialects = 12/12 PASS**. Closed the L1 dashboard's stuck/supersession `[today-7, today]` date scope that hid current-state matview rows from the dashboard's view.

_Phase S + T + U sub-task detail removed during post-phase cleanup. RELEASE_NOTES v8.{1,2}.0 carry the per-phase narratives._

## Phase V — Config / institution YAML split + uv migration + small follow-ups

A grab-bag of post-v8.2.x cleanup folded into one phase. V.1 and V.2 are
the headline items; the rest are small tune-ups deferred from earlier
phases that have stabilized enough to land here.

- [x] **V.1.a — Auto-emit `out/datasource.json`.** Done. In `cli/json.py::json_apply`, after the four apps emit + before deploy, when `cfg.demo_database_url` is set the verb now calls `build_datasource(cfg)` and writes the JSON to `out/datasource.json`. (`cfg` is already L2-prefixed by `resolve_l2_for_demo`, so the auto-derived `datasource_arn` already includes the prefix — no extra step.) Customer-managed deploys (`demo_database_url` unset, explicit `datasource_arn`) skip the auto-emit and leave the customer's existing datasource alone. Closes the orphan-`build_datasource()` gap U.8.b.3 hit twice this session when deploying `spec_example`. Closes the related backlog item _"Single-app deploy must not orphan shared datasource."_

- [x] **V.1.b — Split `config.yaml` ↔ L2 institution YAML (wider sweep).** Done. Strict allowlist on `load_config()` (`common/config.py`) — config.yaml accepts only env-only keys (`aws_account_id`, `aws_region`, `datasource_arn`, `resource_prefix`, `principal_arns` / `principal_arn`, `extra_tags`, `demo_database_url`, `dialect`, `signing`); rejects L2-only keys (theme / persona / rails / chains / accounts / account_templates / transfer_templates / limit_schedules / instance / description / seed_hash) with a pointer at the L2 YAML; rejects hand-set `l2_instance_prefix` (it's derived from the L2 instance at CLI time). Tests/test_config_loader.py covers each rejection path. Test boilerplate: 17 sites that hand-built `Config(...)` literals collapsed to `make_test_config(**overrides)` in `tests/_test_helpers.py`. Example configs (`config.example.yaml`, `examples/config.yaml`) updated with the env-vs-institution boundary callout and theme-moved-to-L2 note.

- [ ] **V.2 — Convert pip → uv.** Adopt `uv` for env / lock management (faster installs, deterministic resolution, single-tool surface). Migration scope: `pyproject.toml` extras stay; add `uv.lock`; CI / Release / Pages workflows swap `pip install` for `uv sync`; `.venv/bin/` invocation pattern preserved (CLAUDE.md memory). Document the change in `docs/handbook/customization.md` (or whichever walkthrough covers env setup).

- [ ] **V.3 — App Info sheet enhancements.** Version of `quicksight-gen` used to generate (so version mismatches are detectable); most-recent `<prefix>_transactions` / `<prefix>_daily_balances` row date (so ETL can be troubleshooted); most-recent matview refresh timestamp.

- [x] **V.4 — Drop `tests/json/test_l2_flow_tracing_matrix.py`'s implicit dependency on `cli` module imports.** No-op — file already had zero `cli` imports (the M.3.9 design from the start went straight at `apps/l2_flow_tracing/app.py::build_l2_flow_tracing_app` rather than through any CLI wrapper). Q.3.a left this one clean. (Five other `tests/json/*.py` files do still import from `quicksight_gen.cli`; out of V.4's narrow scope.)

- [ ] **V.5 — R.6.e "First impression" baseline tune-up.** Two known tuning targets where baseline data still surfaces "real bookkeeping cascade" signal as L1 invariant violations. Both need invariant-aware leg-loop work:
  - **Overdraft on intermediate clearing accounts** (~220 rows on ach_orig_settlement, merchant_payable_clearing, internal_transfer_suspense, ZBA sub-accounts). Cause: baseline emits transfers in random order, so causal cascades (customer outbound → settlement → ZBA sweep → concentration → FRB) don't preserve cause-before-effect timing. Intermediate accounts swing into negative as a result. Fix options: (a) restructure leg loop to enforce causal ordering, (b) materialize zero-net intermediate-clearing legs per cascade per day, (c) widen account starting-balance cushions further.
  - **Limit_breach on customer outbound** (~56 rows). Cause: amount sampler clamps each transfer to the LimitSchedule cap individually, but daily aggregate across multiple firings can exceed cap. Fix: track per-(account, transfer_type, day) cumulative outbound during emission and clamp incremental amounts.

- [ ] **V.6 — R.7.d Re-screenshot at 1280×900.** Re-run `quicksight-gen docs screenshot --all -o src/quicksight_gen/docs/_screenshots/` against the deployed `spec_example` dashboards (Postgres + Oracle live as of v8.2.1). Current screenshots predate Phase R's realistic baseline + Phase U's audit work.

- [x] **V.7 — R.7.e Lift R.1.f spec into a docs-site reference page.** Lifted to `src/quicksight_gen/docs/handbook/seed-generator.md` and wired into the `Reference:` nav alongside `ETL — Data Integration`. Page reflects current code (R.4 starting-balance tuning, ach_return rate at 0.2, intraday rail kind added) rather than the stale 2025 spec values; spec narrative for the per-Rail kind / amount distribution / time-of-day / RNG / chain completion / overlay multipliers all match `common/l2/seed.py` + `common/l2/auto_scenario.py` as of v8.2.2.

- [ ] **V.8 — Reference nav regroup.** Today's `Reference:` mkdocs nav is 8 flat items mixing three concerns: app handbooks (L1 / L2FT / Investigation / Executives / Audit), data contract (Schema v6 / L1 Invariants), and operations (ETL / Customization). Group them via nested `navigation.sections` (mkdocs-material supports it natively, already enabled in `mkdocs.yml`) to give 3 levels of cross-page nav within the existing theme:
  ```
  - Reference:
    - App handbooks: { L1 / L2FT / Investigation / Executives / Audit }
    - Data contract: { Schema v6 / L1 Invariants }
    - Operations: { ETL / Customization }
  ```
  Trade-off is one extra click to reach a leaf, but the URL structure now matches the mental model. Cross-link audit between operations + executive scorecard since auditor + executive read the same artifact differently. If the regroup still feels wrong after landing, escalate to a theme swap (Sphinx+Furo or custom Material override) — significantly bigger.
    - Comment: I really like trying to get to a more responsive theme, there's enough content on these pages that the current theme is limiting us (sphinx+Furo looks very nice)

- [ ] **V.9 — Re-run 4-cell e2e matrix (P.9f.d) + cut v8.3.0.** Was deferred when the per-cell triage list was still settling. Worth a green pass once V.1–V.8 land. Then bump + tag.

---

## Backlog

Single grab-bag for everything not yet in a phase. Promote to a numbered phase entry when work starts.

### L2 model gaps

- **Validator: every Transfer MUST match a Rail.**
- **Validator: LimitSchedule uniqueness on (parent_role, transfer_type).**
- **Multiple dashboards from one L2 instance** (shared prefix + naming).
- **PR dashboard → generic L2-validation dashboard** (re-skinning of L2FT for a different validation persona).
- **Lift seed primitives into `common/l2/seed.py`** (was M.2d.5).

### Tooling / test reliability

- **Apply layered (query+render) pattern to all browser e2e tests** (was M.4.1.k). U.8.b.4 applied this pattern to the audit-dashboard agreement suite; broader sweep across the harness + per-app browser tests is still open.
- **Sasquatch L1 dashboard render flake.** `test_harness_l1_planted_scenarios_visible[sasquatch_pr]` Layer 2 occasionally misses `cust-0001-snb` on the Limit Breach sheet — Layer 1 (matview row presence) passes, the row IS in the matview, but the deployed Limit Breach table doesn't render the cell within the visual timeout. One retry already baked in via `run_dashboard_check_with_retry`; second attempt also misses. Spec_example + fuzz variants of the same test pass on the same run, so the flake is data-shape-specific (sasquatch_pr's seed has more transactions; the L1 dashboard's per-sheet transfer_type dropdown may default-narrow before the table loads). Investigation work: add a screenshot comparison of the Limit Breach sheet between sasquatch_pr (failing) and spec_example (passing) at the moment of the assertion, OR widen the harness's per-sheet wait to assert "table rendered" before sheet_text capture, OR re-deploy sasquatch_pr seed with a tighter days_ago=1 limit_breach plant to rule out timing. Do NOT xfail (the M.4.4.12 lesson — silent xfails masked real bugs).
- **QS-UI kitchen-sink reference tool** (was M.4.4.9). Standalone tool that consumes QS console "view JSON" output for every visual type and dumps it as a reference fixture. Defensive measure; deferred since the concrete editor-crash bugs got fixed.

### Dashboard polish — Q.1.c follow-ups

- **Q.1.a.3 — Auto-derive plain-English axis labels for BarChart** (replace raw column names like `transfer_type` with `Transfer Type`). Manual labels landed on the most visible chart (L1 Today's Exceptions) via Q.1.c; auto-derivation is the broader sweep.
- **Executives Transaction Volume + Money Moved — metadata grouping** (was Q.1.c.6). Needs L2-instance-aware metadata key dropdowns (cascading Key + Value like L2FT Rails sheet) plus a dataset pivot to expose metadata as a dim. Bigger than a punch-list item; queue as its own sub-phase.

### Audit / data evaluation / app info

- **Postgres dataset evaluator** — given a connection, evaluate whether all exception cases are present; report stats on the CLI.


### Tech debt

- **Encode more invariants in the type system.** K.2 did this for drill-param shape compatibility; Phase L's tree primitives close another big chunk. What remains after L is the candidate list for the next round.


### Known platform limitations — do not re-attempt without new evidence

- **QS URL-parameter control sync** — K.4.7 cross-app drills dropped. URL fragment sets the parameter store but doesn't push values into bound controls. Re-entry conditions: AWS fix, custom embedded app via `setParameters()` SDK, or a new URL form that triggers control sync. See `PLAN_ARCHIVE.md` for full re-entry details.
- **QS dropdown click target is the middle grey bar** — `ParameterDropDownControl` only opens on the inner grey bar; clicking the visible edge does nothing. Suggest before investigating "unresponsive dropdown" reports.
- **QS silent-fail mode** — datasets healthy + describe-cleanly, every visual on every sheet shows the spinner forever. See CLAUDE.md → Operational Footguns for the diagnostic ladder.
