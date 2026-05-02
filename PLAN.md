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

---

## Q.3.b — yaml field naming / config-vs-L2 boundary review (deferred)

Today's split between `run/config.yaml` (account, region, datasource, dialect, theme defaults) and the L2 institution YAML (rails, chains, accounts, persona, theme override) has accumulated friction points. Audit + tighten the boundary based on what actually got threaded in M-/N-/O-/P-/Q-. Defers to a dedicated phase with its own scoping pass after Q.3.a settles.

---

## Phase R — Realistic demo seed (open follow-ups)

Phase R landed v7.2.0 (3-month healthy baseline + embedded plants). Three open follow-ups remain:

- [ ] **R.6.e — "First impression" tune-up.** Two known tuning targets where baseline data still surfaces "real bookkeeping cascade" signal as L1 invariant violations. Both need invariant-aware leg-loop work that's out of scope for first land:
  - **Overdraft on intermediate clearing accounts** (~220 rows on ach_orig_settlement, merchant_payable_clearing, internal_transfer_suspense, ZBA sub-accounts). Cause: baseline emits transfers in random order, so causal cascades (customer outbound → settlement → ZBA sweep → concentration → FRB) don't preserve cause-before-effect timing. Intermediate accounts swing into negative as a result. Fix options: (a) restructure leg loop to enforce causal ordering, (b) materialize zero-net intermediate-clearing legs per cascade per day, (c) widen account starting-balance cushions further.
  - **Limit_breach on customer outbound** (~56 rows). Cause: amount sampler clamps each transfer to the LimitSchedule cap individually, but daily aggregate across multiple firings can exceed cap. Fix: track per-(account, transfer_type, day) cumulative outbound during emission and clamp incremental amounts.
- [ ] **R.7.d — Re-screenshot at 1280×900 against the v7.2.0+ demo.** Re-run `quicksight-gen docs screenshot --all -o src/quicksight_gen/docs/_screenshots/` against the deployed sasquatch_pr dashboards once the dashboards are stable post-v8.0.0. Current screenshots predate Phase R's realistic baseline.
- [ ] **R.7.e — Lift R.1.f spec out of PLAN_ARCHIVE.md into a docs-site reference page.** Once the implementation has stabilized + the headline numbers in the spec match what the generator actually produces, lift the design doc into the docs site as durable reference. Likely target: `docs/handbook/seed-generator.md`.

---

## Backlog

Single grab-bag for everything not yet in a phase. Promote to a numbered phase entry when work starts.

### L2 model gaps

- **Validator: every Transfer MUST match a Rail.**
- **Validator: no overlap on (role, transfer_type) entries.**
- **Validator: LimitSchedule uniqueness on (parent_role, transfer_type).**
- **Multiple dashboards from one L2 instance** (shared prefix + naming).
- **PR dashboard → generic L2-validation dashboard** (re-skinning of L2FT for a different validation persona).
- **Lift seed primitives into `common/l2/seed.py`** (was M.2d.5).

### Tooling / test reliability

- **Single-app deploy must not orphan shared datasource.** (Mostly moot under v8.0.0 since `json apply` emits all four; keep as defensive note.)
- **Apply layered (query+render) pattern to all browser e2e tests** (was M.4.1.k).
- **Sasquatch L1 dashboard render flake.** `test_harness_l1_planted_scenarios_visible[sasquatch_pr]` Layer 2 occasionally misses `cust-0001-snb` on the Limit Breach sheet — Layer 1 (matview row presence) passes, the row IS in the matview, but the deployed Limit Breach table doesn't render the cell within the visual timeout. One retry already baked in via `run_dashboard_check_with_retry`; second attempt also misses. Spec_example + fuzz variants of the same test pass on the same run, so the flake is data-shape-specific (sasquatch_pr's seed has more transactions; the L1 dashboard's per-sheet transfer_type dropdown may default-narrow before the table loads). Investigation work: add a screenshot comparison of the Limit Breach sheet between sasquatch_pr (failing) and spec_example (passing) at the moment of the assertion, OR widen the harness's per-sheet wait to assert "table rendered" before sheet_text capture, OR re-deploy sasquatch_pr seed with a tighter days_ago=1 limit_breach plant to rule out timing. Do NOT xfail (the M.4.4.12 lesson — silent xfails masked real bugs).
- **L1 dashboard date filter doesn't surface matview rows** (root cause TBD — non-blocking workaround in place).
- **Re-run 4-cell e2e matrix (P.9f.d)** — was deferred when the per-cell triage list was still settling. Worth a green pass against v8.0.0 once any first-impression tune-ups in R.6.e land.
- **QS-UI kitchen-sink reference tool** (was M.4.4.9). Standalone tool that consumes QS console "view JSON" output for every visual type and dumps it as a reference fixture. Defensive measure; deferred since the concrete editor-crash bugs got fixed.
- **Per-command --help smoke tests** for the new artifact groups. `schema apply` / `data apply` / `data refresh` / `data clean` / `json clean` / `docs apply` / `docs serve` aren't directly exercised by unit tests today — the integration job covers the `--execute` paths against real DB, and emit-only paths flow through pre-existing dataset-shape tests. Add a `tests/{schema,data,json,docs}/test_cli_smoke.py` that asserts `--help` exits 0 + the emit path against `spec_example` produces a non-empty SQL stream.

### Dashboard polish — Q.1.c follow-ups

- **Q.1.a.3 — Auto-derive plain-English axis labels for BarChart** (replace raw column names like `transfer_type` with `Transfer Type`). Manual labels landed on the most visible chart (L1 Today's Exceptions) via Q.1.c; auto-derivation is the broader sweep.
- **Executives Transaction Volume + Money Moved — metadata grouping** (was Q.1.c.6). Needs L2-instance-aware metadata key dropdowns (cascading Key + Value like L2FT Rails sheet) plus a dataset pivot to expose metadata as a dim. Bigger than a punch-list item; queue as its own sub-phase.

### Audit / data evaluation / app info

- **Audit-readiness columns** on Daily Statement (per-row leg-match percentage, etc.) for regulator reporting. Don't use QS pixel-perfect (cost); start with PDF-print guidance in training material.
- **Postgres dataset evaluator** — given a connection, evaluate whether all exception cases are present; report stats on the CLI.
- **App Info sheet enhancements** — version of `quicksight-gen` used to generate (so version mismatches are detectable); most-recent `<prefix>_transactions` / `<prefix>_daily_balances` row date (so ETL can be troubleshooted); most-recent matview refresh timestamp.

### Tech debt

- **Encode more invariants in the type system.** K.2 did this for drill-param shape compatibility; Phase L's tree primitives close another big chunk. What remains after L is the candidate list for the next round.
- **Drop `tests/json/test_l2_flow_tracing_matrix.py`'s implicit dependency on `cli` module imports** if any survived the Q.3.a reorg.

### Known platform limitations — do not re-attempt without new evidence

- **QS URL-parameter control sync** — K.4.7 cross-app drills dropped. URL fragment sets the parameter store but doesn't push values into bound controls. Re-entry conditions: AWS fix, custom embedded app via `setParameters()` SDK, or a new URL form that triggers control sync. See `PLAN_ARCHIVE.md` for full re-entry details.
- **QS dropdown click target is the middle grey bar** — `ParameterDropDownControl` only opens on the inner grey bar; clicking the visible edge does nothing. Suggest before investigating "unresponsive dropdown" reports.
- **QS silent-fail mode** — datasets healthy + describe-cleanly, every visual on every sheet shows the spinner forever. See CLAUDE.md → Operational Footguns for the diagnostic ladder.
