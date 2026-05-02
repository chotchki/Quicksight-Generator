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

## Phase S — Drop the system `dot` binary (research)

**Goal.** Replace the graphviz/`dot` runtime dependency with a pure-Python (or browser-rendered) pipeline that produces the same diagrams. Today every consumer of `quicksight-gen docs apply` (and every CI / Pages / Release runner) needs `apt install graphviz` or `brew install graphviz` first, plus the Python `graphviz>=0.20` wrapper that shells out to `dot`. That's a meaningful install-friction wall for new integrators and a per-job setup cost on every pipeline.

**Why research, not implementation.** Five plausible substitution paths exist (pure-Python layout, browser-rendered Mermaid, in-browser graphviz-WASM, hand-rolled SVG emitters, status-quo defense). Picking blind risks a half-built migration that loses layout quality or trades one external dep for a different one. Phase S converges on the path before we commit to building it.

**Acceptance.** Either a written ADR with a chosen path + rough effort estimate (and a Phase T entry to execute), or a documented decision to keep graphviz with the install-friction tradeoff accepted.

### S.0 — Surface catalog

Catalog the diagrams we render today so candidate evaluation is grounded in real shapes, not abstract "could it work":

- [ ] **S.0.a — Hand-authored `.dot` files** in `src/quicksight_gen/docs/_diagrams/conceptual/` (6 files: double-entry, escrow-with-reversal, eventual-consistency, open-vs-closed-loop, sweep-net-settle, vouchering). Hand-tuned DOT with rank constraints + cluster subgraphs. The hardest to replace because they exploit graphviz's hierarchical layout language.
- [ ] **S.0.b — Programmatic graphs in `common/handbook/diagrams.py`** — `render_conceptual()`, `render_dataflow()`, `render_l2_topology()` plus per-primitive `_build_accounts_graph` / `_build_account_templates_graph` / etc. (~20+ `graphviz.Digraph()` call sites). Pure data-driven: each takes an L2 instance + slice and emits.
- [ ] **S.0.c — `common/l2/topology.py::render_topology()`** — full L2 instance topology renderer (accounts + templates + rails + chains + transfer templates + limit schedules in one DAG). Largest single graph; relies heavily on `dot` ranking for readable layouts.

For each surface: count nodes / edges / clusters; list which graphviz attributes are load-bearing (rank, rankdir, splines, cluster colors, node shapes); which are decorative.

### S.1 — Candidate evaluation (leading: D, fallback: C)

User pick after first-pass review: **D (graphviz WASM)** is the leading path because it preserves DOT semantics + zero migration of existing diagrams. **C (Mermaid)** stays as the documented fallback if D's WASM lib + plugin chain isn't credibly maintained. The other three options are documented for ADR completeness but get no spike effort.

**Maintenance is a hard gate on D.** The graphviz WASM space has a tail of abandoned forks — classic viz.js (mdaines) stagnated for years; multiple "graphviz in the browser" experiments stopped tracking upstream graphviz releases. The acceptance bar for D is a **WASM build that's actively tracking upstream graphviz** and a **mkdocs plugin (or pymdown-extension) that wraps it cleanly**. If both halves of that chain aren't healthy, fall back to C.

- [ ] **S.1.d (LEADING) — Browser-rendered: graphviz WASM.** Keep DOT semantics + identical graphviz layout. The Python side emits DOT strings; the browser renders them via WASM.
  - **Maintenance gate (S.1.d.1) — DONE 2026-05-02. PASS for the WASM lib.** Two healthy candidates:
    - `@hpcc-js/wasm-graphviz` (HPCC Systems) — **1.21.5 released 2026-05-01**, 10 commits in the last week, weekly release-please cadence, embeds upstream graphviz 14.1.3. Single ~800kB ESM bundle with WASM inlined. Used by Observable. **Recommended.**
    - `@viz-js/viz` (mdaines v3 rewrite) — **3.26.0 released 2026-04-14**, monthly cadence, also embeds graphviz 14.1.3. Split ~1.26MB across `.js` + `.wasm`. Healthy fallback.
    - Stale: classic `viz.js` 2.x (deprecated by author); `d3-graphviz` 5.6.0 last release 2024-08-18 (~20 months stale, broken against current `@hpcc-js/wasm` per issue #335). Drop d3-graphviz from consideration.
  - **Plugin gate (S.1.d.2) — DONE 2026-05-02. NO maintained plugin uses WASM.** All four PyPI candidates subprocess `dot`:
    - `mkdocs-graphviz` (rod2ik) — last release 2023-01-26, subprocess.
    - `markdown-inline-graphviz-extension` — 2025-07-25, subprocess.
    - `graphviz-superfence` — 2024-12-15, subprocess via `pymdownx.superfences`.
    - `mkdocs-kroki-plugin` — calls a Kroki HTTP server; out of scope.
    - **Verdict:** the gate is on us. The plugin we'd own is small — a `pymdownx.superfences` custom_fence (~30 lines Python) that wraps DOT in `<pre class="graphviz">` + a 5-line `extra_javascript` shim that loops over `.graphviz` nodes on `DOMContentLoaded` and calls `Graphviz.load().then(g => g.dot(text))`. mkdocs-material's first-party Mermaid integration follows the same pattern.
  - **Net assessment:** D is viable but requires owning ~35 lines of plugin glue. Trade-off vs C: keep graphviz layout (vs Mermaid's dagre), pay for that with a small in-house plugin.
  - **Migration shape under D (revised):**
    1. Rewrite `common/handbook/diagrams.py` so each `_build_X_graph` returns a DOT string (not pre-rendered SVG). The graphviz Python lib + system `dot` binary can leave the runtime entirely.
    2. mkdocs-macros `diagram(...)` macro emits ` ```graphviz fenced blocks (or `<pre class="graphviz">` directly) instead of inline SVG.
    3. Author the custom_fences entry + JS shim. Vendor the WASM lib (don't CDN — we want offline-friendly docs).
  - **Cost vs status quo:** site ships ~800kB more JS (loaded once, cached); first-paint of diagram-heavy pages adds the WASM init time (a few hundred ms). No system-package install in CI. No graphviz Python dep.
- [ ] **S.1.c (FALLBACK) — Browser-rendered: Mermaid via `mkdocs-mermaid2-plugin`.** Two distinct authoring stories:
  - **Hand-authored conceptual diagrams** (S.0.a's 6 `.dot` files) → rewrite as Mermaid fenced blocks dropped directly into the `.md` page. No build-time renderer involved; no Python emitter needed for these.
  - **Data-driven L2 topology + dataflow diagrams** (S.0.b / S.0.c) → keep the Python data-walker, but emit a Mermaid string via `mkdocs-macros` (a `{% raw %}{{ diagram(...) }}{% endraw %}` call returns the Mermaid source instead of a rendered SVG, and the page wraps it in a Mermaid fenced block).
  - Layout-quality risk: Mermaid's `flowchart` engine (dagre) makes different tradeoffs than `dot`. The L2 topology with chains + cluster subgraphs is the stress test. The spike (S.2.c) only fires if D's maintenance gate fails.
  - Loses standalone-SVG export: output is browser-rendered `<div>`.
- [~] S.1.a — NetworkX + matplotlib SVG (pruned). Matplotlib's layout for hierarchical DAGs is too weak vs `dot`; ~15MB dependency footprint isn't free either.
- [~] S.1.b — NetworkX + custom SVG emitter (pruned). Reinventing graph layout is a multi-week sink for a problem already solved by `dot`/Mermaid/viz.js.
- [~] S.1.e — Status quo (pruned as the active path). Kept as the ADR's defensible-fallback option only — if both D and C fail the spike, document the install requirement and stop.

### S.spike — Outcome (2026-05-02)

Spiked both finalists against the `kind="accounts"` diagram on `/scenario/` (sasquatch_pr L2). Eyeball verdict:

- **C (Mermaid + ELK) — FAILED.** Loaded Mermaid 11 + `@mermaid-js/layout-elk` from jsDelivr `+esm`. Diagram rendered, but self-loops drew as floating disconnected lines (ELK self-loop rendering is much weaker than dot), bundled multi-rail labels needed a `<script type="text/x-…">` workaround to survive the HTML parser, and the overall topology fidelity was poor for our shapes. User verdict after first render: "the topology is very wrong and the lines aren't connecting"; after the label fix: "still not much better." Not credible.
- **D (graphviz WASM) — PASSED.** Loaded `@hpcc-js/wasm-graphviz` 1.21.5 from jsDelivr `+esm`, `Graphviz.load().then(g => g.dot(source))`. Identical layout to current graphviz/dot — it IS graphviz running in the browser. Self-loops render as actual loops. Multi-rail labels keep their line breaks. User verdict: "It looks great."

**Decision:** path D wins. The spike proved the WASM path end-to-end; Phase T executes the full migration. ADR can be light — the comparison + verdict above IS the ADR.

### S.2 — Spike D (with self-authored plugin glue)

S.1.d.1 + S.1.d.2 done; the gate verdict is "WASM lib healthy, no maintained plugin so we own ~35 lines of glue." Spike D first; only fall back to C if the spike surfaces a layout-correctness or bundle-size dealbreaker.

- [ ] **S.2.a — Target diagram set.**
  - One **hand-authored conceptual** (pick the densest of S.0.a's 6 `.dot` files — likely `vouchering.dot` or `sweep-net-settle.dot` since they exercise rank constraints + cluster subgraphs).
  - One **data-driven L2 primitive view** (e.g., `_build_accounts_graph` from S.0.b — accounts hierarchy with parent_role edges).
  - The **full L2 topology** from S.0.c (`render_topology(sasquatch_pr_instance)`) — the largest single diagram. Acceptance: byte-identical to today's graphviz layout (it IS graphviz). Any visual diff is a plugin or WASM bug, not a layout regression.
- [ ] **S.2.b — Author the mkdocs glue.**
  - Vendor `@hpcc-js/wasm-graphviz` 1.21.5 ESM bundle into `src/quicksight_gen/docs/_static/` (offline-friendly; don't CDN).
  - Add a `pymdownx.superfences` custom_fence entry to `mkdocs.yml` that maps `name: graphviz` → `<pre class="graphviz">` containing the raw DOT text.
  - Add `extra_javascript` shim (~5 lines) that imports `Graphviz.load()` once on `DOMContentLoaded` and replaces every `.graphviz` `<pre>` with the `<svg>` it returns.
- [ ] **S.2.c — Drop graphviz from the runtime.**
  - Rewrite `common/handbook/diagrams.py` so each `_build_X_graph` builds a `graphviz.Digraph` only as a string-construction convenience (not for rendering), then returns its `.source` as the DOT string. Or skip the lib entirely and string-build DOT directly — it's simple syntax.
  - Update the `diagram(...)` mkdocs-macros entry to emit ` ```graphviz fenced blocks instead of inline SVG.
  - Drop `graphviz>=0.20` from `pyproject.toml` `[docs]` extra (and main deps if not load-bearing elsewhere). Drop `apt-get install graphviz` from `.github/workflows/ci.yml` (3x), `.github/workflows/release.yml`, `.github/workflows/pages.yml`.
- [ ] **S.2.d — Build + eyeball.**
  - `quicksight-gen docs apply` produces a site that renders the three target diagrams via WASM. Side-by-side screenshot vs the v8.0.x graphviz output. Layout match should be exact.
  - Measure: total bytes added to the site (WASM + JS shim), first-paint latency on the L2 topology page.
- [ ] **S.2.e — Fall-through to C (Mermaid) only if D fails.** If D's eyeball test reveals a dealbreaker (layout corruption, unacceptable bundle bloat, plugin glue more involved than the ~35 lines projected), document the failure mode + spike C: convert one hand-authored + one data-driven diagram to Mermaid via mkdocs-material's first-party `pymdownx.superfences` + Mermaid.js integration. Score Mermaid's dagre layout on the L2 topology specifically.

### S.3 — Decision + ADR

- [ ] **S.3.a — Write an ADR** (likely `docs/_adr/0001-diagram-renderer.md`) capturing the comparison matrix, eyeball verdict, install-footprint deltas, and the chosen path. Even if "stay with graphviz", the ADR documents *why* so the question doesn't get re-opened ad-hoc.
- [ ] **S.3.b — Open Phase T with an effort estimate** if the ADR picks a migration path. Phase T builds the chosen renderer + migrates each diagram surface in order of risk (programmatic first, hand-authored DOT last).

### S.4 — Open follow-ups (status quo not picked; see Phase T)

Phase T executes the migration. S.4 only fires if Phase T blows up
in execution + we have to revert.

---

## Phase T — Migrate every diagram surface to graphviz WASM

**Goal.** Drop the system `dot` binary install from every CI / release / pages runner without changing how diagrams look or how they're authored. The Phase S spike proved the WASM lib + plugin glue work; Phase T is mechanical execution.

**Acceptance.** `apt-get install graphviz` deleted from every workflow. `docs apply` produces a site whose diagrams render byte-identical to v8.0.x. The Python `graphviz` lib stays as a runtime dep (it's still doing pure-Python DOT construction), but no system binary is needed.

- [ ] **T.1 — Port the remaining diagram surfaces.** Spike covered only `kind="accounts"`. Replace `_to_svg(g)` with `g.source` everywhere in `common/handbook/diagrams.py`:
  - `render_l2_topology` for `account_templates` / `chains` / `hierarchy` / `layered` / `transfer_template`.
  - `render_l2_account_focus` / `render_l2_account_template_focus` / `render_l2_rail_focus` / `render_l2_transfer_template_focus` / `render_l2_chain_focus` / `render_l2_limit_schedule_focus` (per-primitive concept-page macros).
  - `render_dataflow` (per-app dataset → sheet wiring).
  - `render_conceptual` (the 6 hand-authored `.dot` files in `_diagrams/conceptual/` — return the file text directly; no `graphviz.Source` wrap).

- [ ] **T.2 — Make WASM the default; drop the env-var toggle.** `_wrap_svg(svg, alt)` → `_wrap_dot(dot, alt)` emits `<figure class="qs-diagram"><script type="text/x-graphviz">DOT</script></figure>`. Drop `QS_USE_WASM` env check + `diagrams_wasm.py` (its job is folded into the main pipeline).

- [ ] **T.3 — JS shim renders into the figure (lightbox compat).** Update `qs-graphviz-wasm.js` to insert the rendered SVG into the parent `<figure>` so the existing `qs-lightbox.js` click-to-zoom keeps working without changes.

- [ ] **T.4 — Drop system `dot` from CI / release / pages workflows.** Five `apt-get install graphviz` lines in `.github/workflows/{ci,release,pages}.yml` go away.

- [ ] **T.5 — Update README + install docs.** README "Prerequisites" mentions `dot` for diagrams — drop. The Python `graphviz` lib stays via `[docs]` extra.

- [ ] **T.6 — Verify.** `docs apply` builds clean against both `spec_example` and `sasquatch_pr`. Eyeball every diagram surface (scenario tour, concept pages, handbook overviews) — should look identical to v8.0.x.

- [x] **T.8 — Cut v8.1.0.** Additive: removes a system requirement, doesn't add Python deps. RELEASE_NOTES entry covers the WASM swap + the dropped `apt install` line. Tag pushed 2026-05-02.

T.7 (vendor the WASM lib) deferred to Backlog — bring in if jsDelivr CDN reliability becomes a complaint from real users. Phase T otherwise complete.

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

- **Vendor `@hpcc-js/wasm-graphviz` for offline-friendly docs** (was T.7). `qs-graphviz-wasm.js` currently CDN-loads from jsDelivr. Bring in if jsDelivr reliability becomes a real-user complaint OR an integrator deploys the docs site somewhere airgapped. ~30 min: download the ESM bundle into `docs/_static/`, swap the import path.
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
