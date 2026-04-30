# QuickSight Generator — Active Plan

**Where we are.** Phase M shipped v6.0.0 (L2 foundation + 4-app shape). Historical context for phases G–M lives in `PLAN_ARCHIVE.md`.

**Active phases below.** Phase N reshapes the two carry-over apps (Investigation, Executives) onto the L1/L2 primitives that L1 Dashboard + L2 Flow Tracing already use, and lifts theme out of code into the L2 YAML so each instance carries its own brand. Phase O renders docs + training against the L2 instance vocabulary instead of today's hand-written Sasquatch copy. Everything else collects in **Backlog**.

---

## Phase N — Port Investigation + Executives onto L1/L2; theme as L2 attribute

**Goal.** Make L2-fed apps the only model. Today Investigation + Executives still read directly from the shared base tables and carry their own per-app theme presets in `common/theme.py`. Phase N folds them into the L1/L2 stack so a single L2 YAML drives all four apps' shape, schema, and theme.

**Sequencing rationale.** Theme moves first (N.1) because it's a pure L2-side change — no app rewiring — and the reshapes that follow can pick up the new attribute. Audit happens before the reshapes (N.2) to confirm the question shape each app answers and decide keep / reshape / delete per app rather than committing in advance.

- [ ] **N.1 — Theme as an L2 YAML attribute.** Today's `PRESETS` dict in `common/theme.py` collapses to one theme per L2 instance, declared inline in the L2 YAML. Scope decision: only the two L2-fed apps (L1 dashboard + L2FT) migrate in N.1; Investigation + Executives keep their current `cfg.theme_preset` path until each gets an L2 instance at N.3 / N.4. CLI `--theme-preset` flag stays for now; it's dropped at N.5 once all four apps are L2-fed.
  - [x] N.1.a — Promote `ThemePreset` to the L2 model. Move the dataclass from `common/theme.py` → `common/l2/theme.py`; re-export from `common/theme.py` for back-compat with apps still consuming directly.
  - [x] N.1.b — Add `theme: ThemePreset | None = None` to `L2Instance`. Optional so existing fixtures + integrator YAMLs without a theme block still load.
  - [x] N.1.c — Loader: `_load_theme(raw, *, path) -> ThemePreset`. Parses inline `theme:` dict; validates hex regex (`^#[0-9a-fA-F]{6}$`) on every color field; friendly errors cite logical path (`theme.accent`).
  - [x] N.1.d — Test fixtures get inline theme blocks. `tests/l2/spec_example.yaml` carries the default palette; `tests/l2/sasquatch_pr.yaml` carries today's `sasquatch-bank` palette. seed_hash unchanged.
  - [x] N.1.e — L1 dashboard routes from L2 via `resolve_l2_theme(l2_instance)`; `cfg.theme_preset` no longer consulted on the L1 path.
  - [x] N.1.f — L2 Flow Tracing routes from L2. Same wiring as N.1.e.
  - [x] N.1.g — Dropped `sasquatch-bank` + `sasquatch-bank-investigation` from `PRESETS`. Registry holds only `default`. Inv + Exec fall back to `default` until N.3 / N.4 migrates them.
  - [x] N.1.h — Loader unit tests. 41 cases covering happy path + every rejection branch.
  - [x] N.1.i — Kitchen-sink fixture exercises a theme block + coverage assertion in `test_kitchen_sink_covers_every_primitive_kind`.
  - [x] N.1.j — Verify + commit. Pyright clean, 1179 unit tests pass, Aurora deploy verification stays as a follow-up validation against a live L2 render.

- [x] **N.2 — Inv + Exec audit + reshape decision.** Both apps RESHAPE onto L2; both decisions in `docs/audits/n_2_inv_exec_audit.md`. **Architectural reframe**: one L2 YAML per institution drives ALL FOUR apps (L1 / L2FT / Inv / Exec). Not per-app YAMLs. The YAML is the **institution spec** — accounts, rails, theme, eventually seed scenarios. SPEC.md and the `L2Instance` docstring need a rename pass to drop "L2 instance" → "institution YAML" in prose (typed identifier `L2Instance` stays). Investigation's two matviews migrate from `schema.sql` to `common/l2/schema.py` for per-instance prefixing.

- [ ] **N.3 — Investigation reshape.** Port Investigation onto L1/L2 primitives. The 4 content sheets keep their shapes; reshape is plumbing only.
  - **Phase 1 — Schema (additive).**
    - [x] N.3.a — Read + document the 2 inv matview SQL bodies. Both touch only `transactions` (no `daily_balances`); 3-substitution shape per body.
    - [x] N.3.b — `_emit_inv_views(instance)` added to `common/l2/schema.py`. Lifts the K.4.4/K.4.5 matview bodies; prefix-substitutes matview names + every `transactions` ref. Wired into `emit_schema()` and `refresh_matviews_sql()`.
    - [x] N.3.c — 10 unit tests in `test_l2_schema.py` covering parametrized emit/drop-before-create/drop-before-base, prefix substitution totality, no flat-ref leakage, no v5-column leakage, inter-view independence, per-instance isolation. Real-Postgres parse deferred to N.3.j Aurora deploy.
  - **Phase 2 — App rewiring.**
    - [x] N.3.d — Investigation dataset SQL strings now derive `prefix` from `cfg.l2_instance_prefix` and substitute every `inv_*` matview + `transactions` ref. Top-level SQL constants → prefix-taking helpers (`_money_trail_base_sql`, `_anetwork_accounts_sql`). New `_require_prefix(cfg)` raises a friendly error if the prefix isn't set, so misuse fails at construction time. Tests fail until N.3.f wires the prefix.
    - [x] N.3.e — Folded into N.3.d. Dataset IDs were already routed through `cfg.prefixed()`; once `build_investigation_app` (N.3.f) sets `cfg.l2_instance_prefix`, the IDs come out as `qs-gen-<prefix>-inv-*-dataset` automatically.
    - [x] N.3.f — `build_investigation_app(cfg, *, l2_instance=None)` mirrors L1. Imports `default_l2_instance` from `apps.l1_dashboard._l2` (TODO: lift to `common/l2/` once spec/scenario YAML split lands). Auto-derives `cfg.l2_instance_prefix` if unset.
    - [x] N.3.g — Theme via `resolve_l2_theme(l2_instance)`; dropped `get_preset(cfg.theme_preset)` from app.py. Pass `theme=theme` through `_build_getting_started_sheet` + `_build_app_info_sheet` → `populate_app_info_sheet`.
    - [x] N.3.h — CLI's `_generate_investigation` mirrors L1 (loads L2 instance, pre-stamps `cfg.l2_instance_prefix`, passes through). `_apply_demo` also pre-stamps prefix so demo apply's QS-JSON write step works mid-flight (seed SQL is still flat-table — that lands in N.3.i). `_all_dataset_filenames` cross-app helper auto-stamps prefix when caller's cfg lacks one (Executives invokes Investigation enumeration in --all flow).
  - **Phase 3 — Demo seed (rolls in AR-dim-tables backlog cleanup).**
    - [ ] N.3.i — `apps/investigation/demo_data.py` takes a `prefix` kwarg; all `_inserts("transactions", ...)` become `_inserts(f"{prefix}_transactions", ...)`. Drop the `ar_ledger_accounts` / `ar_subledger_accounts` plants AND drop the corresponding CREATE TABLE statements from `schema.sql` (the legacy AR dim carry-overs noted in the Backlog).
    - [ ] N.3.j — `quicksight-gen demo apply investigation` flow: refresh `<prefix>_inv_*` matviews; pass `cfg.l2_instance_prefix` to `generate_demo_sql`.
  - **Phase 4 — Tests.**
    - [ ] N.3.k — Update `test_investigation.py` for prefixed dataset IDs + L2-fed signature. Walk failures one-at-a-time.
    - [x] N.3.l — `tests/e2e/conftest.py` Investigation fixtures (`inv_dashboard_id`, `inv_analysis_id`, `inv_dataset_ids`) now include the L2 instance prefix segment via a new `inv_l2_prefix` fixture, mirroring the L1 pattern. The 6 `test_inv_*.py` files use those fixtures; no per-test patches needed.
    - [x] N.3.l-bis — `tests/e2e/_harness_inv_assertions.py` (new) provides `assert_inv_matviews_queryable(db_conn, prefix)` — schema-health check that catches v5/v6 column-name regressions like the one surfaced in N.3.b. Wired into `test_harness_end_to_end.py` as Layer 1b alongside `assert_l1_matview_rows_present`.
    - [x] N.3.l-ter — **Folded into N.4.h.** Implementation landed there: `InvFanoutPlant` covers BOTH Inv matviews; InvAnomalyPlant + InvChainPlant deferred as N.4.h follow-up.
    - [x] N.3.m — Full unit suite + pyright + commit. Achieved at multiple commits along the way; final state: 1189 passed, pyright clean.
  - **Phase 5 — Drop legacy + docs.**
    - [x] N.3.n — Dropped the global `inv_pair_rolling_anomalies` + `inv_money_trail_edges` from `schema.sql` (truncated lines 1380-1563). Added explicit `DROP MATERIALIZED VIEW IF EXISTS` lines for upgrade safety. Updated `cli.py::_apply_demo` REFRESH calls to use the prefixed names.
    - [x] N.3.o — CLAUDE.md Investigation paragraph + demo apply paragraph + schema.sql comment reflect L2-fed status.
    - [ ] N.3.p — Aurora deploy verification of the L2-fed Investigation flow + planted Sasquatch Investigation persona (defer to combined N.3+N.4 deploy at end of N.4). The seed-data lift to common/l2/seed.py is the prerequisite (currently flat-table v5 plants don't surface in the prefixed Inv matviews).
  - **Cleanup carried into N.4** — `populate_app_info_sheet(theme=None)` fallback stays until Executives also migrates.

- [ ] **N.4 — Executives reshape + theme cleanup + Inv harness parity.** Closes Phase N's substantive work. Executives goes L2-fed, the deferred N.3.l-ter Inv plant primitives land here (so combined N.3+N.4 Aurora verify has actual data), the legacy `cfg.theme_preset` path gets fully removed, and the silent-fallback theme contract lands (no L2 theme block → no custom QS Theme resource emitted; AWS CLASSIC takes over).
  - **Phase 1 — App rewiring.**
    - [x] N.4.a — Executives dataset SQL routed through `<prefix>_transactions` / `<prefix>_daily_balances` via `_require_prefix(cfg)`; v6 column renames applied (`MAX(ABS(t.amount_money))`, `DATE(MIN(t.posting))`, `d.account_role AS account_type`, `SUM(t.amount_money) AS transfer_net`).
    - [x] N.4.b — `build_executives_app(cfg, *, l2_instance=None)` mirrors L1. Imports `default_l2_instance`; auto-derives `cfg.l2_instance_prefix` if unset.
    - [x] N.4.c — Theme via `resolve_l2_theme(l2_instance)`; `_analysis_name(theme: ThemePreset)` + threaded through `_populate_getting_started`.
    - [x] N.4.d — CLI `_generate_executives` accepts `l2_instance_path`, pre-stamps prefix, builds app once. Demo apply Exec block threads `inv_l2`.
  - **Phase 2 — Tests + harness parity.**
    - [x] N.4.e — `test_executives.py` updated: `_TEST_CFG.l2_instance_prefix="spec_example"`; `MAX(t.amount)` → `MAX(ABS(t.amount_money))` v6 assertion.
    - [x] N.4.f — `tests/e2e/conftest.py` carries `exec_l2_prefix` fixture; prefix segments on dashboard / analysis / dataset IDs.
    - [x] N.4.g — `tests/e2e/_harness_exec_assertions.py` provides `assert_exec_base_tables_queryable`; wired into `test_harness_end_to_end.py` as Layer 1c.
    - [x] N.4.h — **Inv plant primitives + harness tightening.** Added `InvFanoutPlant` (one fanout covers BOTH Inv matviews — pair_rolling_anomalies + money_trail_edges; InvAnomalyPlant + InvChainPlant deferred follow-up). Wired into `auto_scenario.default_scenario_for(mode="l1_invariants")`; re-locked `seed_hash` on spec_example + sasquatch_pr + `_BROAD_MODE_HASHES` for l1_plus_broad. Added `assert_inv_planted_rows_visible(db_conn, prefix, manifest)` to `_harness_inv_assertions.py`; wired as Layer 1b'. Per-plant unit tests + manifest-shape tests added. **Schema bug surfaced+fixed**: Inv matview filter said `status='success'` (v5-era leftover) — corrected to `'Posted'`. Validated by N.4.o Aurora deploy.
  - **Phase 3 — Theme path cleanup (the v6.1.0 trigger).**
    - [x] N.4.i — `populate_app_info_sheet(theme: ThemePreset)` now required (not `| None`). Dropped the `(theme or get_preset(cfg.theme_preset)).accent` fallback + the `get_preset` import. Docstring example updated.
    - [x] N.4.j — Dropped `cfg.theme_preset` (Config dataclass + YAML loader + env-var map) AND the CLI `--theme-preset` flag (generate + deploy commands). Apps now coerce `resolve_l2_theme(l2_instance) or get_preset("default")` for in-canvas accent colors; CLI uses the un-coerced Optional for the silent-fallback emit decision. ~70-site sweep across cli.py + 4 apps + 11 test fixtures + 2 doc walkthroughs (re-skin walkthrough rewritten around the L2 ``theme:`` block model).
    - [x] N.4.k — `build_theme(cfg, theme: ThemePreset | None) -> Theme | None` returns `None` when `theme is None`. CLI + harness deploy skip `theme.json` write + theme deploy in that case — AWS CLASSIC takes over. `resolve_l2_theme` now returns `ThemePreset | None`. New unit test `TestDefaultPreset::test_silent_fallback_returns_none_when_no_theme` locks the contract.
    - [x] N.4.l — Dropped `PRESETS` dict + `get_preset()`; the 4 apps + 1 test file now reference `DEFAULT_PRESET` directly. Removed the 5 registry-validation tests in `test_theme_presets.py` (the function under test no longer exists). Updated `common/l2/theme.py` docstring.
  - **Phase 4 — Verify + close.**
    - [x] N.4.m — Full unit suite green (1186 passed, 84 skipped); pyright clean on `common/tree/` strict scope. Single commit `d13b661` covers N.4.h–N.4.l (37 files, +698 / -408).
    - [x] N.4.n — CLAUDE.md sweep: tagline ("four apps, all L2-fed"), demo apply paragraph (mentions Executives + the silent-fallback contract), single-app generate example (uses `--l2-instance` instead of dropped `--theme-preset`), structure tree comments (config.py / theme.py / test_theme_presets.py descriptions), Architecture Decisions theme bullet rewritten around the L2 attribute model, Conventions hex-color rule references `theme.<token>` instead of `get_preset(cfg.theme_preset).<token>`.
    - [x] N.4.o — **Combined N.3 + N.4 Aurora deploy verify.** Final: 75 passed, 1 known-flake (sasquatch L1 dashboard render flake — see backlog). Eight iterations to reach steady state, each surfacing a real fix:
      - `Config.with_l2_instance_prefix(prefix)` helper centralizes prefix-stamp + datasource_arn re-derive across all 8 sites; without it, per-app builders baked the unprefixed datasource_arn into dataset JSON and deploy failed `InvalidParameterValueException`.
      - `_apply_demo` now applies `emit_l2_schema(inv_l2)` so per-instance `<prefix>_*` matviews actually exist on the demo database.
      - `_apply_demo` now plants the L2-shape demo seed via `emit_l2_seed(inv_l2, default_scenario_for(inv_l2).scenario)` instead of the legacy `apps/investigation/demo_data.py` (which wrote v5-shape rows into the now-dead unprefixed tables — invisible to the prefixed L1 + Inv matviews). **Closes the deferred N.3.i.**
      - Inv `pair_legs` CTE outputs aliased back to `recipient_account_type` / `sender_account_type` (downstream consumers expect v5 names).
      - `_create_theme` now skips when `theme.json` is missing (silent-fallback contract; `_delete_theme` already had the guard).
      - Inv `recipient_fanout` dataset SQL migrated to v6 columns (`amount_money` / `posting` / `account_role` / `status='Posted'` / leaf-internal predicate).
      - Inv + Exec `_analysis_name` normalized to L1/L2FT shape (`Name (instance)`).
      - Test-side: L1 `l1_dataset_ids` adds 2 App Info datasets; Inv/Exec sheet count + EXPECTED_NAMES carry trailing `Info`; harness `expected_kinds` adds `inv_fanout_plants`.
      - **Persona walkthrough lift to common/l2/seed.py** (Cascadia/Juniper) deferred to Phase O — current demo seed is the auto-derived `default_scenario_for` shape (drift / overdraft / limit-breach / stuck / supersession / fanout) which renders the L1 + Inv dashboards with real data without persona-flavored content.
      - Silent-fallback theme verification (deploy with NO `theme:` block) — covered by harness fuzz instances (no inline theme), `_create_theme` guard exercised on each.
      - Hash relocks — `seed_hash` values were updated mid-N.4 (commits f.../d13b661); ground-truth Aurora data confirmed in this run.
      - Closed pending issue #433 "L1 dashboard date filter doesn't surface matview rows" — root cause was `_apply_demo` only refreshing 3 of the 13 per-prefix matviews. Fixed by calling `refresh_matviews_sql(inv_l2)` which already had the right dependency-ordered list (commit 41efda8).

- [x] **N.5 — End-of-phase iteration gate.** Cut **v6.1.0** — L2 YAML is the only configuration surface for app shape + theme. All four apps L2-fed, no per-app theme presets, no hand-rolled persona globals. `__version__ = "6.1.0"`; RELEASE_NOTES entry covers what's new + breaking changes + migration notes (commit `5e07bb8`). Awaiting tag + push.

---

## Phase O — Unified docs render pipeline

**Goal.** One unified docs site rendered per L2 instance. Today's two separate surfaces (`docs/handbook/` — reference voice, details + examples; `training/handbook/` — narrative voice, how + why) merge into a single mkdocs site with a coherent information architecture that holds both voices. Templated against the L2 institution YAML's vocabulary instead of today's hand-written Sasquatch-flavored copy. Replaces `mapping.yaml` substitution.

**Two voices, one site.**
- **Reference voice** (handbook today): "what column does `posting` carry, what shape does `daily_balances` take, here's the contract, here's an example row". Lives under a "Reference" section.
- **Narrative voice** (training today): "what is double-entry, why does escrow need a reversal, when does eventual consistency bite". Lives under a "Concepts" section + per-persona quickstarts.
- **Walkthroughs** (mixed): task-oriented "how do I set up the L1 dashboard for my institution" / "how do I read the Drift sheet". Bridges the two voices on a per-task basis.

**Diagrams are a cross-cutting capability.** The L2 YAML already encodes flow + linkages (accounts ↔ rails ↔ chains ↔ transfer templates). Graphviz renders those structurally, and hand-authored diagrams cover the conceptual narrative shapes (double-entry, escrow cycle, sweep-net-settle). Both kinds of diagrams embed across every section of the docs site — Concepts gets the conceptual narratives, Reference gets the L2-driven topology, Walkthroughs gets per-sheet dataflow, For Your Role gets a "your role's view" diagram. Treated as a first-class capability in O.0.g and used throughout O.1's prose migration.

**Sequencing rationale.** Audit + decisions land in O.0 (template engine, vocabulary schema, **information architecture for the merged site**, file-layout convention) so O.1 can execute mechanically against a settled contract. O.1 is the unified docs migration (folds `docs/handbook/` + `docs/walkthroughs/` + `training/handbook/` into the merged IA). O.2 collapses to the bits that don't fit O.1 cleanly: the deferred L.8 Executives prose, the per-instance ScreenshotHarness regen, and the `export` CLI surface. O.3 closes the loop with a fresh-L2-yaml smoke + per-customer publishing workflow.

**Help-sheet idea dropped.** The "render docs into a sheet on the dashboard itself" idea was investigated (`docs/audits/o_help_sheet_design.md`) and shelved — QS sheet rendering is too limiting for the doc shapes we need. Docs stay as mkdocs HTML / markdown.

- [ ] **O.0 — Audit + ground-truth decisions.** Lock the template engine, vocabulary schema, AND merged information architecture before touching prose.
  - [x] O.0.a — **Content audit landed.** `docs/audits/o_0_content_audit.md` covers all 62 prose files across the 3 surfaces + 2 docs-root files. Voice distribution: 27% reference, 34% narrative, 29% walkthrough, 10% mixed. Persona-string totals: SNB (71+), Cascadia (23+) — Cascadia/Juniper Investigation personas + 2 Training_Story merchants need adding to `SNB_PERSONA` (or a new `HandbookVocabulary` superset). Zero real code-side bleeds (4 residual hits are all docstring examples or intentional whitelabel-detection patterns). 5-section IA validated. Diagram catalog inputs captured for O.0.f.
  - [ ] O.0.b — **Decide template engine**. Prefer `mkdocs-macros-plugin` + Jinja2 — already in the mkdocs ecosystem, doesn't fork the build, lets templates live alongside markdown. Document the trade-offs vs. custom render in the audit doc.
  - [ ] O.0.c — **Define `HandbookVocabulary` dataclass** + `vocabulary_for(l2_instance) -> HandbookVocabulary`. Typed contract carries BOTH voices' needs: institution name, account-taxonomy strings (subledger / control / external), persona names + role descriptions (training voice), sample customer/account names, anchor scenario references (Cascadia/Juniper-style), conceptual examples (double-entry walk-through values). Some fields come from `l2_instance.description`; the persona-shaped fields likely need a new optional `personas:` block on the L2 YAML — decide whether to extend `L2Instance` (typed primitive) or sidecar (separate `<instance>_personas.yaml`).
  - [ ] O.0.d — **Decide file-layout convention**: in-place templating (overwrite `docs/`) vs. split `docs_template/` + render to `_rendered/`. Probably split, so source diffs stay clean. Document in the audit.
  - [ ] O.0.e — **Decide merged IA**. Default proposal (refine in audit doc):
    - `Concepts/` — narrative voice (today's `training/handbook/concepts/`): double-entry, escrow-with-reversal, eventual-consistency, sweep-net-settle, vouchering, open-vs-closed-loop. The "why" before the "what".
    - `Reference/` — reference voice (today's `docs/handbook/`): per-app reference (l1, l2_flow_tracing, investigation, executives, etl, customization), schema_v6, L1-invariants. The "what" with examples.
    - `Walkthroughs/` — mixed task-oriented (today's `docs/walkthroughs/`): per-sheet markdown for each app + customization how-tos.
    - `For Your Role/` — narrative voice, audience-specific quickstarts (today's `training/handbook/for-*/`): for-accounting, for-customer-service, for-developers, for-product-owner. Each landing page picks the right Concepts + Reference pages for that role.
    - `Scenarios/` — walkthrough voice (today's `training/handbook/scenarios/`): end-to-end demo narratives. Reference back to Concepts + Reference.
    Document the IA as a top-level mkdocs nav skeleton in the audit.
  - [ ] O.0.f — **Diagram catalog + render decisions.** Diagrams are a first-class capability across the docs (the L2 YAML already encodes accounts ↔ rails ↔ chains ↔ transfer templates — Graphviz can render that structurally). Catalog every diagram we want to embed, classified as:
    - **L2-driven** (auto-generated per institution from the YAML): account-rail-account topology (per L2), chain DAG (per L2), layered combination (per L2), per-app dataflow (which datasets feed which sheets — joins L2 + dataset SQL), per-sheet "where does this data come from" (Reference + Walkthroughs).
    - **Hand-authored** (conceptual narratives, not L2-derived): double-entry flow, escrow-with-reversal cycle, sweep-net-settle, vouchering, eventual-consistency timeline, open-vs-closed-loop. Lift into a `docs/_diagrams/` directory; embed via macro so the source `.dot` lives alongside the output SVG.
    - **Hybrid** (skeleton hand-authored, L2 fills in labels): "your role's view" diagrams under `For Your Role/` — one per persona showing which sheets/datasets they touch.
    Decide: Graphviz `dot` (hierarchical, default) vs `neato`/`sfdp` (force-directed) vs `circo` (circular) per diagram kind. Render pipeline: SVG output cached in `docs/_diagrams/_rendered/` (gitignored), regenerated on `mkdocs build` via the macro engine. Output the catalog as part of the O.0 audit doc.
  - [ ] O.0.g — Commit O.0 audit + decisions doc. Phase 1 unblocked.

- [ ] **O.1 — Unified docs render pipeline.** All prose (today's `docs/handbook/` + `docs/walkthroughs/` + `training/handbook/`) folds into the merged IA from O.0.e and renders against L2 vocabulary. mkdocs render takes `(L2 instance, neutral templates) → rendered docs site`. Friendly + helpful voice in narrative sections, precise + example-rich voice in reference sections.
  - [ ] O.1.a — Add chosen template-engine dep (likely `mkdocs-macros-plugin`). Wire into `mkdocs.yml`. Stand up the new top-level nav skeleton from O.0.e (Concepts / Reference / Walkthroughs / For Your Role / Scenarios) with placeholder index pages so the structure is visible before content moves in.
  - [ ] O.1.b — Implement `HandbookVocabulary` + `vocabulary_for(l2_instance)`. Unit tests: spec_example, sasquatch_pr, plus a synthetic minimal-L2 fixture exercise the full field set including the both-voices fields (persona role descriptions, conceptual examples).
  - [ ] O.1.c — **Diagram render pipeline.** Add Graphviz dep (system + `graphviz` python wrapper). Implement:
    - `render_l2_topology(l2_instance, kind: Literal["accounts", "chains", "layered"]) -> str` — emits an SVG string from the L2 YAML's structural data. The `chains` cut consumes `apps/l2_flow_tracing/datasets.py::CHAINS_CONTRACT`'s shape; `accounts` cut walks `instance.accounts` + `instance.rails`; `layered` is the union.
    - `render_dataflow(app_name) -> str` — emits the per-app dataflow (which datasets feed which sheets); reads the App tree's emitted Analysis structure.
    - mkdocs-macros hook: `{{ diagram("l2_topology", kind="chains") }}` / `{{ diagram("conceptual", name="double-entry") }}` macros so any markdown page can embed without duplicating the render call.
    - Hand-authored `.dot` files live under `docs/_diagrams/conceptual/`; rendered SVGs cached under `docs/_diagrams/_rendered/` (gitignored).
    Land before O.1.d so the migration substeps can embed diagrams as prose moves in.
  - [ ] O.1.d — **Pilot migration**: convert ONE Reference-voice page (`docs/handbook/l1.md`) AND ONE narrative-voice page (`training/handbook/concepts/double-entry.md`) into the new IA's templated form. Both pilots embed the relevant diagrams via the O.1.c macro (Reference page gets the L2 topology; Concepts page gets the hand-authored double-entry flow). Render against spec_example AND sasquatch_pr; eyeball both for voice consistency in their respective sections + zero Sasquatch leakage.
  - [ ] O.1.e — Migrate the rest of `docs/handbook/` into `Reference/` (`l2_flow_tracing.md`, `investigation.md`, `etl.md`, `customization.md`, plus the new `executives.md` from L.8 — see O.2.a). Each per-app reference page embeds its dataflow diagram.
  - [ ] O.1.f — Migrate `docs/walkthroughs/` per-sheet markdown into `Walkthroughs/` (l1/, investigation/, etl/, customization/, plus the new executives/ from L.8 — see O.2.b). Per-sheet pages embed the "where does this data come from" diagram (per-sheet dataflow cut).
  - [ ] O.1.g — Migrate `training/handbook/concepts/` into `Concepts/` (double-entry, escrow-with-reversal, eventual-consistency, sweep-net-settle, vouchering, open-vs-closed-loop). Each concept page embeds its hand-authored conceptual diagram.
  - [ ] O.1.h — Migrate `training/handbook/for-*/` into `For Your Role/` (for-accounting, for-customer-service, for-developers, for-product-owner). Each landing page links into the right Concepts + Reference pages for that role AND embeds the "your role's view" hybrid diagram (skeleton hand-authored, L2 fills labels).
  - [ ] O.1.i — Migrate `training/handbook/scenarios/` into `Scenarios/`. Each scenario embeds an end-to-end flow diagram showing the L2-driven path the scenario walks.
  - [ ] O.1.j — **Schema_v6 examples lift**: detailed `transactions` / `daily_balances` row examples + recommendations, sourced from YAML fixtures (so they stay in sync with the seed primitives). Append to `docs/Schema_v6.md` under Reference.
  - [ ] O.1.k — **L.5 persona-leak cleanup**: grep for residual Sasquatch / Bigfoot / SNB outside `apps/<app>/demo_data.py` + `tests/l2/` fixtures. Each remaining hit is a real bleed; either fix at source or template through O.0.c's vocabulary.
  - [ ] O.1.l — **Drop `training/`** — the entire directory goes away once content has moved. Drop `training/mapping.yaml.example` + the SNB-string substitution machinery (superseded by templating). Drop `training/QUICKSTART.md` (folds into the new `For Your Role/` landing page or the top-level `index.md`). The auto-derive parity test in `test_persona.py` either retargets to the new `vocabulary_for` shape or is deleted.
  - [ ] O.1.m — Tests: render docs against spec_example, sasquatch_pr, and a fresh "acme_treasury" minimal fixture. Assert NO Sasquatch / Bigfoot leakage in spec_example's rendered output. Diagram render produces non-empty SVG for each of the 3 L2 cuts on each fixture. `mkdocs build --strict` green. Nav structure matches the O.0.e IA.
  - [ ] O.1.n — Commit.

- [ ] **O.2 — Executives docs + ScreenshotHarness regen + CLI.** What didn't fit cleanly into O.1's prose-migration loop.
  - [ ] O.2.a — **L.8 deferred Executives handbook** — write `docs/handbook/executives.md` (lands under Reference) covering the 4 sheets + how it overlaps with L1 / L2FT / Inv. Consumes the existing Executives sheet descriptions.
  - [ ] O.2.b — **L.8 deferred Executives walkthroughs** — `docs/walkthroughs/executives/` per-sheet markdown (Getting Started + Account Coverage + Transaction Volume + Money Moved). Mirrors L1's per-sheet walkthrough shape; lands under Walkthroughs.
  - [ ] O.2.c — **CLI**: `quicksight-gen export docs --l2-instance <yaml> -o <dir>`. Renders the unified docs site against the supplied L2; default L2 = spec_example. Replaces both the existing `export docs` AND `export training` commands (the unified site eliminates the split).
  - [ ] O.2.d — **ScreenshotHarness wrapper**: per-instance regen. Deploy → warm Aurora (`SELECT 1`) → screenshot → tear down. Wire into the `export docs` flow as an optional `--with-screenshots` flag (heavy operation; off by default).
  - [ ] O.2.e — **Aurora warm-up**: `SELECT 1` against `cfg.demo_database_url` right before each ScreenshotHarness embed-URL fetch (per F12 / M.0.10 — Aurora Serverless cold-start otherwise surfaces as QS's generic "We can't open that dashboard" error). Wrap in a helper so future ScreenshotHarness callers inherit the warm-up.
  - [ ] O.2.f — Tests: docs+screenshots rendered against multiple L2 instances; ScreenshotHarness output present + non-empty.
  - [ ] O.2.g — Commit.

- [ ] **O.3 — Iteration gate.** Unified docs render against any L2 instance the integrator points at. Per-customer publishing pipeline supports the merged site.
  - [ ] O.3.a — **Per-customer smoke**: write a fresh `tests/l2/acme_treasury.yaml` (no Sasquatch flavor, simplest possible institution shape). Run `export docs --l2-instance acme_treasury.yaml` (with + without `--with-screenshots`) and eyeball outputs for leakage + voice consistency across all 5 IA sections.
  - [ ] O.3.b — **Publishing workflow doc** (lands under the new `Walkthroughs/` section as a customization how-to): walks the integrator through the end-to-end (write your L2 YAML → `export docs` → publish to your wiki / website).
  - [ ] O.3.c — README + CLAUDE.md sweep: docs section reflects the unified-site + templated-render workflow; drop references to the substitution-via-`mapping.yaml` approach AND the `training/` directory; `export training` command no longer exists.
  - [ ] O.3.d — Decide release cut: **v6.2.0** (additive — the unified docs pipeline lands cleanly on top of N's L2-fed apps; the `training/` directory removal is technically a breaking change for anyone consuming it as a Python package surface, but in practice it's a docs reorg + a CLI surface change `export training` → `export docs`) vs **v7.0.0** (if you want to flag the docs reorg as breaking explicitly). Default expectation: v6.2.0 with a clearly-called-out "training/ directory removed" entry in RELEASE_NOTES.
  - [ ] O.3.e — Bump `__version__`; write RELEASE_NOTES; commit + tag + push.

---

## Backlog

Single grab-bag for everything not yet in a phase. Promote to a numbered phase entry when work starts. Full historical detail in `PLAN_ARCHIVE.md`.

### Punted from Phase M ship push

- **CLI workflow polish.** Materialize the SPEC's "Workflow Ideas" — `generate config (demo|template)`, `apply schema`, `apply data`, `apply dashboards`, `generate training`. Acceptance: a fresh integrator can run end-to-end from one YAML.
- **QS-UI kitchen-sink reference tool.** Standalone tool that consumes QS console "view JSON" output for every visual type and dumps it as a reference fixture. Defensive measure; deferred since the concrete editor-crash bugs got fixed.
- **L2FT plants-visible date-filter widening.** `assert_l2ft_plants_visible` hard-fails on sasquatch_pr because some planted firings have `days_ago` exceeding the L2FT dashboard's default date filter window. Same family as the L1 dynamic widening fix (M.4.4.12). Currently wrapped in inline xfail.
- **Drop AR-only schema.sql carry-overs.** `ar_ledger_accounts` / `ar_subledger_accounts` dimension tables stay in `schema.sql` because Investigation's demo seed registers its own sub-ledgers there for FK integrity. Phase N's Investigation reshape decides whether Inv migrates off the AR dim tables — once it does, drop the carry-overs.

### L2 model gaps

- **Validator: every Transfer MUST match a Rail.**
- **Validator: no overlap on (role, transfer_type) entries.**
- **Multiple dashboards from one L2 instance** (shared prefix + naming).
- **PR dashboard → generic L2-validation dashboard** (re-skinning of L2FT for a different validation persona).
- **Lift seed primitives into `common/l2/seed.py`** (was M.2d.5).

### Tooling / test reliability

- **Single-app deploy must not orphan shared datasource.**
- **Apply layered (query+render) pattern to all browser e2e tests** (was M.4.1.k).
- **Sasquatch L1 dashboard render flake.** `test_harness_l1_planted_scenarios_visible[sasquatch_pr]` Layer 2 occasionally misses `cust-0001-snb` on the Limit Breach sheet — Layer 1 (matview row presence) passes, the row IS in the matview, but the deployed Limit Breach table doesn't render the cell within the visual timeout. One retry already baked in via `run_dashboard_check_with_retry`; second attempt also misses. Spec_example + fuzz variants of the same test pass on the same run, so the flake is data-shape-specific (sasquatch_pr's seed has more transactions; the L1 dashboard's per-sheet transfer_type dropdown may default-narrow before the table loads). Investigation work: add a screenshot comparison of the Limit Breach sheet between sasquatch_pr (failing) and spec_example (passing) at the moment of the assertion, OR widen the harness's per-sheet wait to assert "table rendered" before sheet_text capture, OR re-deploy sasquatch_pr seed with a tighter days_ago=1 limit_breach plant to rule out timing. Do NOT xfail (the M.4.4.12 lesson — silent xfails masked real bugs).
- **L1 dashboard date filter doesn't surface matview rows** (root cause TBD — non-blocking workaround in place).
- **PR FilterControl dropdown e2e tests hang on dropdown open** — 5 tests in `tests/e2e/test_filters.py` time out waiting on the MUI listbox popover under `data-automation-context`. (Deleted with PR app in M.4.4 — left as reference if the dropdown helper is reused.)

### Audit / data evaluation / app info

- **Audit-readiness columns** on Daily Statement (per-row leg-match percentage, etc.) for regulator reporting. Don't use QS pixel-perfect (cost); start with PDF-print guidance in training material.
- **Postgres dataset evaluator** — given a connection, evaluate whether all exception cases are present; report stats on the CLI.
- **App Info sheet enhancements** — version of `quicksight-gen` used to generate (so version mismatches are detectable); most-recent `transactions` / `daily_balances` row date (so ETL can be troubleshooted); most-recent matview refresh timestamp.

### Tech debt

- **Encode more invariants in the type system.** K.2 did this for drill-param shape compatibility; Phase L's tree primitives close another big chunk. What remains after L is the candidate list for the next round.

### Known platform limitations — do not re-attempt without new evidence

- **QS URL-parameter control sync** — K.4.7 cross-app drills dropped. URL fragment sets the parameter store but doesn't push values into bound controls. Re-entry conditions: AWS fix, custom embedded app via `setParameters()` SDK, or a new URL form that triggers control sync. See `PLAN_ARCHIVE.md` for full re-entry details.
- **Cross-app dataset prune drops sibling app's non-default-L2 datasets.** When two L2-fed apps deploy against the same non-default L2 instance, generating one prunes the other's already-generated dataset JSONs. Workaround: skip the CLI; write JSON directly via Python. Fix candidates (option 3 recommended — per-app-prefix prune) in `PLAN_ARCHIVE.md`.
