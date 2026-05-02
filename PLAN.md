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
- **Phase T** (v8.1.0) — Every diagram now renders client-side via `@hpcc-js/wasm-graphviz`. `render_*` helpers return DOT strings; `<script type="text/x-graphviz">` blocks inside `<figure>` wrappers; ~50-line JS shim does the WASM render. 5 `apt-get install graphviz` lines deleted across CI / Release / Pages workflows.

_Phase S + T sub-task detail removed during the post-T cleanup. RELEASE_NOTES v8.1.0 carries the migration narrative; the spike outcome is documented in the v8.1.0 release notes (Mermaid+ELK failed eyeball, graphviz WASM passed)._

## Phase U — `quicksight-gen audit` PDF reconciliation report

**Goal.** Add a fifth artifact group `audit` to the CLI. `quicksight-gen audit apply -c config.yaml --execute -o report.pdf` queries the per-prefix matviews + base tables directly, formats the result via `reportlab`, emits a regulator-ready PDF. Bypasses QuickSight pixel-perfect entirely (cost + wrong shape for the auditor).

**Why now.** Phase R landed the realistic baseline; Phase Q polished the dashboard surface; Phase T just proved we can stay system-binary-free. The L1 invariant matviews + typed dataset contracts + persona-neutral templating give us all the inputs needed; the same SQL the dashboards run, executed once at report-generation time, formatted into a printable artifact.

**Why this matters more than a QS pixel-perfect export.** Auditors need: cover summary, per-invariant violation tables with row counts + dollar magnitudes, per-account-day reconciliation walk for every drifted account, supersession audit trail, sign-off block. Different shape than the dashboards; building it as its own artifact (sourced from the same matviews) means the regulator's view + the operator's view stay in sync without QS in the loop.

### Decisions (2026-05-02 planning gate)

| Question | Decision |
|---|---|
| Report shape | Cover + executive summary + per-invariant tables + per-account-day Daily Statement walk + sign-off block. **Build page by page** with a review gate between each. |
| Period | Default `yesterday + last 7 days`. `--from / --to` CLI flags override. |
| PDF tech | **`reportlab`** — pure Python wheels, no system deps (preserves the Phase T win). Programmatic API; layout iterates. |
| CLI shape | `audit apply \| clean \| test`. `apply` defaults to emit Markdown source for inspection; `--execute` writes the PDF. Same `--l2 PATH` flag as the other groups. |
| Provenance | Hash of matview-snapshot SHA256s + generation timestamp + L2 fingerprint embedded in cover page footer. Documented on the site. Optional `audit verify report.pdf -c config.yaml` sub-command for recomputation. |
| Persona | Today's L2 surface (institution name + accent + logo via persona block) is enough — functional > marketing. |
| Test layer | Test the **SQL strings + template-input dicts** (dataset-contract pattern). End-to-end smoke: render PDF, extract text via `pypdf`, assert expected section headings + sentinel values from a known seed. |
| Sign-off | Visual signature line in the PDF. Cryptographic signature applied **after** human review (Adobe Sign / DocuSign / `pyHanko`) — out of scope for the generator. |

**Acceptance.** A v1 PDF an auditor would actually accept: covers the L1 invariants, generated reproducibly, carries a verifiable provenance stamp. Iterate page-by-page within Phase U; add sub-tasks as feedback comes in.

### Execution plan (review gate between each)

- [x] **U.0 — Skeleton + harness.** Add `cli/audit.py` with the `audit apply | clean | test` shell. `audit apply` (no `--execute`) emits a one-line "v1 stub" Markdown source to stdout. `audit apply --execute -o report.pdf` writes a one-page reportlab PDF that says "Phase U skeleton — institution: {name}, period: {from}–{to}". Wire into `cli/__init__.py` alongside the other four groups. Add `reportlab` to `[audit]` extra in `pyproject.toml`. **Review gate:** confirm CLI shape feels right before adding pages.
- [x] **U.1 — Cover page.** Institution name (from L2 YAML persona block), period (default yesterday + last 7 days; `--from / --to` overrides), generation timestamp, L2 instance fingerprint hash placeholder (real hash lands in U.7). Layout: title, subtitle, period band, footer with provenance placeholder. **Review gate.**
- [x] **U.2 — Executive summary page.** Totals across the period: transaction count, dollar volume (gross / net), exception counts by check (drift / overdraft / limit_breach / stuck_pending / stuck_unbundled / supersession). Single page, table layout. SQL queries reuse the same matview shapes the dashboards do. **Review gate.**
- [ ] **U.3 — Per-invariant violation tables.** One page (or grouped) per L1 invariant, sourced from `<prefix>_*` matviews. Columns: account, account role, day, magnitude (dollar amount or count), reason. **Review gate after each invariant lands** so layout iterates per-table.
  - [x] U.3.a — Drift
  - [x] U.3.b — Overdraft
  - [x] U.3.c — Limit breach
  - [x] U.3.d — Stuck pending
  - [x] U.3.e — Stuck unbundled
  - [x] U.3.f — Supersession audit
  - [x] U.3.g — **Vocab + theme templating sweep across all audit PDF sections.** Theme: all hardcoded hexes (`#1a1a1a`, `#eef3f7`, `#c7d6e3`, `#f5f8fb`, `colors.whitesmoke`, `setFillGray(0.4)`) replaced with `theme.<token>` references — `theme = resolve_l2_theme(instance) or DEFAULT_PRESET` resolved once in `audit_apply` and threaded through every `_*_story` function via a new `theme` param. Footer color now respects theme via `_make_footer_drawer(theme)` closure factory (reportlab's `onFirstPage`/`onLaterPages` callbacks couldn't take extra args). Vocab: institution name already came from persona block (no further substitution needed — audit prose is L1-domain generic, not persona-specific). Persona-leak CI: `tests/audit/test_persona_clean.py` runs PDF + markdown emit against `spec_example.yaml`, extracts via pypdf, asserts zero matches in the same blocklist `tests/data/test_seed_persona_clean.py` uses (sasquatch / bigfoot / yeti / snb / frb / etc.). Both PDF and markdown paths covered.
  - [x] U.3.h — **PDF bookmarks + TableOfContents flowable.** `_AuditDocTemplate` proxy creates a `BaseDocTemplate` with an `afterFlowable` hook; tagged headings (via `_bookmarked_h1` / `_bookmarked_h3` helpers, which set `_bookmark_level` on the Paragraph) emit both `canvas.addOutlineEntry()` and `notify('TOCEntry', ...)`. `PageTemplate` carries the existing themed footer. `TableOfContents` flowable inserted on its own page after the cover; `multiBuild()` does the two-pass render (pass 1 collects page numbers, pass 2 fills the TOC). Hierarchy: 7 section H1s at level 0, 13 sub-section H3s at level 1. Cover page Title + the "Table of contents" heading itself stay un-bookmarked. Verified: 10 outline entries + 13 sub-entries + dot-leader TOC page on the sasquatch_pr live PDF.
- [x] **U.4 — Per-account-day Daily Statement walk.** For each (account, business_day) row in `<prefix>_drift` for the period, audit emits a walk page: 5 KPIs (Opening / Debits / Credits / Closing stored / Drift) sourced from `<prefix>_daily_statement_summary` matview + day's transactions from `<prefix>_current_transactions`. Same matview reads as the L1 dashboard's Daily Statement sheet → row-for-row agreement. Walks bookmarked at outline level 1 under "Per-account Daily Statement walk" level 0 (each `account_id — YYYY-MM-DD` is its own bookmark + TOC entry). **Footnote explains the per-day drift here is `closing_stored − closing_recomputed-from-day's-flow` which can differ from U.3.a's cumulative `stored − sum(all transactions)` when daily_balances are sparse.** Sasquatch_pr live: 2 walks (cust-0001 / 04-27, cust-0002 / 04-26) — page count went 10 → 14.
  - for parent accounts, they should always render, even if drift is zero
- [ ] **U.5 — Sign-off block.** Last-page footer / dedicated sign-off page: auditor name field, date field, signature line. Visual only — actual cryptographic signature applied externally after review. **Review gate.**
 - Note: it would be very valuable to have the option of a system generated signing and another signature box for the auditor. that way if someone generates the pdfs automatically, someone can still sign off without invalidating the rest. Note the in phase V we are going to tighten the config.yaml and l2.yaml split which will help with this.
- [ ] **U.6 — Provenance footer.** Every page footer: report-version sentinel, page X of Y, generation timestamp, source-data fingerprint (short hash). Cover page additionally carries the long-form fingerprint with the per-matview SHA256 list. **Review gate.**
- [ ] **U.7 — Provenance hash + verify subcommand.**
  - Question: should this be hashed over the materialized views or a hash of the base rows through a given pair of entry ids? The views will change, the underlying data should be immutable.
    - Hash external inputs - all of these should be included on a single pdf page on how to validate this output
      - transaction entry #
      - balance entry #
      - l2 yaml
      - git commit hash of the quicksight-gen version
    - Hash over
      - transaction entry #
      - balance entry #
      - transaction rows from 0 to the entry # (inclusive)
      - balance entry rows from 0 to the entry # (inclusive)
      - l2 yaml 
      - git commit hash of the quicksight-gen version
  - Compute fingerprint as `sha256(L2_instance_fingerprint || sorted_matview_row_hashes || period_anchor)`. Reproducible for a given DB snapshot + L2.
  - Add `audit verify report.pdf -c config.yaml` — extracts embedded fingerprint from the PDF, queries the same matviews, recomputes, compares. Exit 0 on match, 1 on drift.
  - Document on the site (`docs/handbook/audit.md`): what the fingerprint covers, how to recompute manually, exact SQL the verify command runs.
- [ ] **U.8 — Test layer.**
  - `tests/audit/test_sql.py` — locked SQL strings for each invariant query (dataset-contract pattern).
  - `tests/audit/test_template_input.py` — assert the dict passed to reportlab carries expected sections + sentinel values from a known fixture seed.
  - `tests/audit/test_smoke.py` — end-to-end against `spec_example`: render PDF, extract text via `pypdf`, assert expected section headings + planted-scenario values appear. (User asked for an end-to-end sanity check; this is the cheapest credible one.)
  - `audit test` CLI subcommand wires pytest + pyright per the four-artifact convention.
  - Note: this should be testable in CI.
- [ ] **U.8.b — Audit/dashboard agreement e2e (release gate).** The credibility contract: every number in the audit PDF MUST agree with what the deployed L1 dashboard shows for the same period + L2 + DB snapshot. Auditor seeing one number while the operator sees another destroys trust in the entire generator. Test plan: seed demo DB to a known state (existing harness fixture); generate audit PDF via `audit apply --execute -o`; extract numbers from PDF cells via `pypdf` (exec-summary table values + per-invariant table row counts + Daily Statement aggregates); for each one, walk the corresponding L1 dashboard sheet via Playwright (existing `tests/e2e/_harness_*` pattern), apply the same period date filter, count rows / read KPI value; assert audit number == dashboard number. Both Postgres + Oracle. **Gates the v8.2.0 release** — failure means rebuild before tag.
- [ ] **U.9 — CLI surface tests.** `--help` smoke + emit-only path against `spec_example`. Mirror the pattern queued for the other groups in the Backlog.
- [ ] **U.10 — Documentation.**
  - `docs/handbook/audit.md` — reference page covering: what the report contains, how to generate it, how to verify the fingerprint, how to apply a cryptographic signature externally.
  - Update `docs/for-your-role/compliance-analyst.md` with the audit-report onramp.
  - README + CLAUDE.md mention the new artifact group.
- [ ] **U.11 — Cut release.** v8.2.0 — additive (new artifact group + new optional `reportlab` dep). RELEASE_NOTES entry. Tag, push, verify pipeline.

---
# Proposed Phase V
- Convert to using uv from pip
- Today's split between `run/config.yaml` (account, region, datasource, dialect, theme defaults) and the L2 institution YAML (rails, chains, accounts, persona, theme override) has accumulated friction points. Audit + tighten the boundary based on what actually got threaded in M-/N-/O-/P-/Q-. Defers to a dedicated phase with its own scoping pass after Q.3.a settles.
  - Comments: I think there is a natural split between insitution and environment.
    - config.yaml has 
      - aws account
      - aws region
      - tag prefix
      - quicksight datasource (optional but if left out, json generates it)
      - database dialect, 
      - database connection (optional but required for demo data automatic population and audit pdf)
      - signing key (optional but enables strong pdf signatures for audit trail)
    - institution has
      - rails
      - chains
      - accounts
      - persona
      - theme override (defaults live in the code)
- **Vendor `@hpcc-js/wasm-graphviz` for offline-friendly docs** (was T.7). `qs-graphviz-wasm.js` currently CDN-loads from jsDelivr. Bring in if jsDelivr reliability becomes a real-user complaint OR an integrator deploys the docs site somewhere airgapped. ~30 min: download the ESM bundle into `docs/_static/`, swap the import path.
  - The goal being that someone could output the documentation to a flat file directory and run without a web server. web server would still be a command line option
- **Per-command --help smoke tests** for the new artifact groups. `schema apply` / `data apply` / `data refresh` / `data clean` / `json clean` / `docs apply` / `docs serve` aren't directly exercised by unit tests today — the integration job covers the `--execute` paths against real DB, and emit-only paths flow through pre-existing dataset-shape tests. Add a `tests/{schema,data,json,docs}/test_cli_smoke.py` that asserts `--help` exits 0 + the emit path against `spec_example` produces a non-empty SQL stream.
- **Re-run 4-cell e2e matrix (P.9f.d)** — was deferred when the per-cell triage list was still settling. Worth a green pass against v8.0.0 once any first-impression tune-ups in R.6.e land.
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

- **QS-UI kitchen-sink reference tool** (was M.4.4.9). Standalone tool that consumes QS console "view JSON" output for every visual type and dumps it as a reference fixture. Defensive measure; deferred since the concrete editor-crash bugs got fixed.


### Dashboard polish — Q.1.c follow-ups

- **Q.1.a.3 — Auto-derive plain-English axis labels for BarChart** (replace raw column names like `transfer_type` with `Transfer Type`). Manual labels landed on the most visible chart (L1 Today's Exceptions) via Q.1.c; auto-derivation is the broader sweep.
- **Executives Transaction Volume + Money Moved — metadata grouping** (was Q.1.c.6). Needs L2-instance-aware metadata key dropdowns (cascading Key + Value like L2FT Rails sheet) plus a dataset pivot to expose metadata as a dim. Bigger than a punch-list item; queue as its own sub-phase.

### Audit / data evaluation / app info

- **Postgres dataset evaluator** — given a connection, evaluate whether all exception cases are present; report stats on the CLI.
- **App Info sheet enhancements** — version of `quicksight-gen` used to generate (so version mismatches are detectable); most-recent `<prefix>_transactions` / `<prefix>_daily_balances` row date (so ETL can be troubleshooted); most-recent matview refresh timestamp.

### Tech debt

- **Encode more invariants in the type system.** K.2 did this for drill-param shape compatibility; Phase L's tree primitives close another big chunk. What remains after L is the candidate list for the next round.
- **Drop `tests/json/test_l2_flow_tracing_matrix.py`'s implicit dependency on `cli` module imports** if any survived the Q.3.a reorg.

### Known platform limitations — do not re-attempt without new evidence

- **QS URL-parameter control sync** — K.4.7 cross-app drills dropped. URL fragment sets the parameter store but doesn't push values into bound controls. Re-entry conditions: AWS fix, custom embedded app via `setParameters()` SDK, or a new URL form that triggers control sync. See `PLAN_ARCHIVE.md` for full re-entry details.
- **QS dropdown click target is the middle grey bar** — `ParameterDropDownControl` only opens on the inner grey bar; clicking the visible edge does nothing. Suggest before investigating "unresponsive dropdown" reports.
- **QS silent-fail mode** — datasets healthy + describe-cleanly, every visual on every sheet shows the spinner forever. See CLAUDE.md → Operational Footguns for the diagnostic ladder.
