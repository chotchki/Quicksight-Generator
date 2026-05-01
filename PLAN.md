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
  - [x] O.0.b — **Template engine: `mkdocs-macros-plugin` + Jinja2**. Audit §8. In-tree, no separate render step, templates live alongside markdown.
  - [x] O.0.c — **`HandbookVocabulary` schema sketched** in audit §5. Built on top of existing `SNB_PERSONA`; adds `InvestigationPersonaVocabulary` for Cascadia + Juniper Ridge + the 2 missing Training_Story merchants. Drop the redundant `account_labels` tuple (derivable from `gl_accounts`). Implementation lands in O.1.b.
  - [x] O.0.d — **File-layout: in-place** (overwrite `docs/`). Audit §8. mkdocs-macros runs at build time; source markdown stays template-shaped without a separate `_rendered/` directory. Override if a problem surfaces during O.1.d pilot.
  - [x] O.0.e — **5-section IA**: Concepts / Reference / Walkthroughs / For Your Role / Scenarios. Validated against the 62-file inventory in audit §6. The mixed-voice handbook index pages split into per-section landing pages + cross-section see-also blocks.
  - [x] O.0.f — **Diagram catalog**: audit §7. L2-driven (Graphviz auto from YAML — topology / chains / layered / per-app dataflow), hand-authored conceptual (`docs/_diagrams/conceptual/*.dot` for double-entry, escrow-with-reversal, sweep-net-settle, vouchering, eventual-consistency, open-vs-closed-loop), hybrid (per-role view skeletons). Engine: Graphviz `dot` + `neato`. Embedded via `{{ diagram(...) }}` mkdocs-macros hook.
  - [x] O.0.g — Audit + decisions doc landed at `docs/audits/o_0_content_audit.md` (commit `2c4fad5`). Phase 1 unblocked.

- [ ] **O.1 — Unified docs render pipeline.** All prose (today's `docs/handbook/` + `docs/walkthroughs/` + `training/handbook/`) folds into the merged IA from O.0.e and renders against L2 vocabulary. mkdocs render takes `(L2 instance, neutral templates) → rendered docs site`. Friendly + helpful voice in narrative sections, precise + example-rich voice in reference sections.
  - [x] O.1.a — `mkdocs-macros-plugin>=1.3` + `graphviz>=0.20` added to `[docs]` extras. `mkdocs.yml` restructured to the 5-section IA (Concepts / Reference / Walkthroughs / For Your Role / Scenarios + API Reference); existing pages re-homed under Reference / Walkthroughs / Scenarios with no path moves yet (those land per-section in O.1.d-i). 5 placeholder section index pages created. `_macros/` + `_diagrams/conceptual/` placeholder directories created (macro module + conceptual `.dot` files land in O.1.b / O.1.c). `mkdocs build --strict` green.
  - [x] O.1.b — `common/handbook/vocabulary.py` ships `HandbookVocabulary` + 4 sub-shapes (`InstitutionVocabulary`, `StakeholderVocabulary`, `MerchantVocabulary`, `InvestigationPersonaVocabulary`) and `vocabulary_for(l2_instance)`. Built-in `sasquatch_pr` vocabulary reuses `SNB_PERSONA` for the strings already there + layers Investigation personas (Juniper Ridge, Cascadia Trust Bank + Operations, three Shell Companies). Anything else routes to a neutral fallback that derives institution name from the L2 description's first proper-noun run (strict title case so spec_example's "Generic SPEC-shaped" doesn't false-match) and leaves persona-flavored fields empty — zero leakage by construction. 25 unit tests across `tests/test_handbook_vocabulary.py` cover sasquatch_pr, spec_example (incl. the no-leakage hard contract), the synthetic-minimal fixture, and the `_extract_institution_name` / `_institution_acronym` helpers.
  - [x] O.1.c — **Diagram render pipeline landed.** `common/handbook/diagrams.py` ships:
    - `render_l2_topology(l2_instance, kind)` — kinds `accounts` / `chains` / `layered` emit inline SVG. Accounts cut walks `instance.accounts` + `instance.rails` (TwoLegRail draws source→destination edges, SingleLegRail draws self-loops on the leg-role account, union role expressions expand to multiple edges). Chains cut walks `instance.chains` (required edges solid, optional dashed, XOR groups labeled). Layered subgraphs both into one figure.
    - `render_dataflow(app_name)` — walks the typed `App` tree for `l1_dashboard` / `l2_flow_tracing` / `investigation` / `executives`, fanning datasets→sheets via every visual's dataset reference.
    - `render_conceptual(name)` — reads `docs/_diagrams/conceptual/<name>.dot` and pipes through Graphviz; raises `KeyError` with the catalog list when the named file is missing.
    - All three strip `<?xml ... ?>` + `<!DOCTYPE>` so the SVG embeds cleanly via `md_in_html`.
    `main.py` at the repo root registers the `diagram(family, **kwargs)` macro that dispatches by family. mkdocs.yml wires `module_name: main` (mkdocs-macros default location). The first hand-authored `.dot` (`double-entry.dot`) ships under `src/quicksight_gen/docs/_diagrams/conceptual/`; package_data adds `docs/**/*.dot` so they ship with the wheel. `concepts/index.md` carries the macro call as a smoke test — `mkdocs build --strict` renders the SVG inline. 19 unit tests in `tests/test_handbook_diagrams.py` cover all three render families against spec_example + sasquatch_pr.
  - [x] O.1.d — **Pilot migration landed.** `main.py` exposes `vocab` + `l2_instance_name` Jinja variables sourced from `vocabulary_for(load_instance(QS_DOCS_L2_INSTANCE or spec_example.yaml))` so any markdown page can substitute `{{ vocab.institution.name }}`. `handbook/l1.md` drops the snb-hero (was a hardcoded SNB wordmark) for a vocab-substituted intro and embeds two diagrams: `l2_topology kind=accounts` near the top + `dataflow app=l1_dashboard` near the bottom. `concepts/double-entry.md` is a fresh in-IA copy of the training page (training/ original stays until O.1.l) with the conceptual diagram embedded and persona-flavored bits replaced by neutral L1-vocabulary phrasing. Both render cleanly under both L2 instances: spec_example shows "Your Institution" with zero SNB / Sasquatch / Bigfoot / Federal Reserve strings in the pilot pages; sasquatch_pr shows "Sasquatch National Bank" via vocab substitution + the L2 accounts topology fills out with SNB's actual GL chart.
  - [x] O.1.e — Reference handbook intros (l2_flow_tracing, investigation, etl, customization) drop the snb-hero hardcoded SNB wordmark for vocab-substituted intros + dataflow / chains diagrams embedded on the per-app pages. Body examples (gl-XXXX codes, merchant names) still SNB-flavored — those clean up in O.1.k.
  - [ ] O.1.f — `docs/walkthroughs/` per-sheet markdown stays at its current path (the IA already maps it under `Walkthroughs/`). Per-sheet dataflow embeds + path moves under `walkthroughs/<app>/<sheet>/index.md` are deferred — current paths render fine and the substantive content already lives there.
  - [x] O.1.g — All 6 conceptual pages migrated into `docs/concepts/` with hand-authored Graphviz diagrams embedded. `_diagrams/conceptual/` ships the full set (double-entry, escrow-with-reversal, sweep-net-settle, vouchering, eventual-consistency, open-vs-closed-loop). Each page replaces the original "In the SNB demo" section with a "How L1 surfaces this" pointer at the L1 invariants. Stale AR/PR walkthrough links replaced with L1 handbook links.
  - [ ] O.1.h — `for-your-role/index.md` ships as a slim landing page; the original `training/handbook/for-*/` content (4 role guides, 813 lines) was heavily SNB-coupled and was dropped with `training/` in O.1.l rather than rewritten in vocab-templated form. Future per-role pages can be authored here when needed.
  - [x] O.1.i — `scenarios/index.md` updated to vocab-substituted intro; `Training_Story.md` stays as the demo cast of characters (intentionally Sasquatch-flavored). Per-scenario training pages dropped with `training/` in O.1.l (their content was already covered by `walkthroughs/`).
  - [ ] O.1.j — **Schema_v6 examples lift** deferred to backlog. The current `Schema_v6.md` is sufficient for the spec contract; examples-from-YAML-fixtures lift can land later when integrators ask for it.
  - [x] O.1.k — Top-level + section-landing pages (index.md, L1_Invariants.md, scenarios/index.md, concepts/*) persona-cleaned. Walkthroughs + api/* still carry residual SNB body examples; those clean up incrementally as integrator feedback comes in.
  - [x] O.1.l — `training/` directory deleted (18 files). `_apply_whitelabel`, `_parse_mapping`, `_WhitelabelResult`, `_WHITELABEL_*`, `export_training_cmd` removed from `cli.py`. `derive_mapping_yaml_text` + `_HEADER` + `_yaml_kv` removed from `common/persona.py` (parity test in `test_persona.py` reduced to non-empty guards on `SNB_PERSONA`). `training/**/*` removed from `pyproject.toml` package_data. `tests/test_export.py` reduced to `export docs` coverage. README + CLAUDE.md updated to drop training/ + substitution-machinery references.
  - [ ] O.1.m — Tests: 1227 unit tests pass + `mkdocs build --strict` green. Per-fixture render test ("acme_treasury minimal" + Sasquatch-leakage assertion) deferred to O.2 with the export-docs CLI work.
  - [ ] O.1.n — Commit.

- [ ] **O.2 — Executives docs + ScreenshotHarness regen + CLI.** What didn't fit cleanly into O.1's prose-migration loop.
  - [x] O.2.a — `docs/handbook/executives.md` ships under Reference. Covers the 4 sheets (Getting Started, Account Coverage, Transaction Volume Over Time, Money Moved) + how they overlap with L1 / L2FT / Inv. Embeds the per-app dataflow diagram + uses vocab substitution for the institution name. Wired into mkdocs.yml nav.
  - [ ] O.2.b — Per-sheet Executives walkthroughs (`docs/walkthroughs/executives/`) deferred. The reference page covers each sheet's purpose; deeper walkthroughs land when integrator demand surfaces.
  - [x] O.2.c — `quicksight-gen export docs --l2-instance <yaml>` validates the L2 path and echoes the `QS_DOCS_L2_INSTANCE=<path> mkdocs build` command the integrator runs to render against that institution.
  - [ ] O.2.d — ScreenshotHarness wrapper deferred. AWS-dependent + heavy; lands when the export-docs publishing pipeline gets real customer feedback.
  - [ ] O.2.e — Aurora warm-up helper deferred (depends on O.2.d).
  - [ ] O.2.f — Per-fixture render tests deferred (depends on O.2.d).
  - [ ] O.2.g — Commit.

- [x] **O.3 — Iteration gate.** Unified docs render pipeline lands as v6.2.0.
  - [ ] O.3.a — Per-customer smoke (`acme_treasury.yaml` fixture) deferred. The neutral fallback in `vocabulary_for` already exercises the "any non-sasquatch L2 produces zero-leakage docs" path; a synthetic minimal fixture ships under `tests/test_handbook_vocabulary.py::TestSyntheticMinimalInstance` instead.
  - [x] O.3.b — Publishing-workflow walkthrough at `walkthroughs/customization/how-do-i-publish-docs-against-my-l2.md`. Walks the integrator through `export docs --l2-instance` → `QS_DOCS_L2_INSTANCE=… mkdocs build`.
  - [x] O.3.c — README + CLAUDE.md sweep landed in O.1.l (training/ + substitution machinery references all removed).
  - [x] O.3.d — Cut as **v6.2.0** — additive on top of N's L2-fed apps; the `training/` directory removal is called out as a breaking change in RELEASE_NOTES.
  - [x] O.3.e — `__version__ = "6.2.0"` bumped; v6.2.0 RELEASE_NOTES entry written.

---

# Phase P — Multi-database support (Postgres + Oracle 19c)

**Headline feature**: every emitted SQL surface (DDL + dataset SQL) renders against either Postgres or Oracle 19c Standard Edition. The dialect is carried by `config.yaml` (`dialect: postgres|oracle`), propagates through demo apply + datasource emission + matview refresh, and round-trips through CI containers for both. Cuts as **v7.0.0** — additive (Postgres users see no behavior change) but touches every SQL surface, so the major bump flags the breadth.

The existing SQL is already constrained to a portable subset (no JSONB, SQL/JSON path syntax) precisely because Oracle was anticipated; Phase P operationalizes that intent end-to-end.

- [x] **P.0 — Audit + decisions captured.** This conversation is the audit; the design calls landed:
  - **Abstraction**: hand-written `common/sql/dialect.py` helpers (option (i)). Switch to per-dialect parallel SQL files only if helpers get unwieldy on a specific surface.
  - **Materialized views everywhere**: keep MVs on Oracle (`REFRESH ON DEMAND`); plain views skipped — performance would suffer on the L1 invariant scans.
  - **Oracle target**: 19c Standard Edition. BOOLEAN doesn't exist (NUMBER(1)); TEXT → CLOB / VARCHAR2; identity columns + sequences differ; `WITH RECURSIVE` → unmarked recursive `WITH`.
  - **Dialect carrier**: `config.yaml` carries `dialect: postgres|oracle`; no CLI flag (the `datasource_arn` is dialect-coupled anyway).
  - **CI**: Docker Postgres + Docker Oracle Free containers run **alongside** the existing fast unit pass — added as gated `integration-postgres` / `integration-oracle` jobs, not replacing the current no-DB unit run.
  - **Naming**: Oracle is named freely in repo artifacts going forward. The "do not name the target RDBMS" memory becomes historical context (pre-Phase-P era).

- [ ] **P.1 — V5 carry-over cleanup.** `schema.sql` ships dead DDL (`DROP TABLE IF EXISTS` for the v5 12-table family + the AR `ar_*` dim tables + dead `ar_*` view surface) carried for upgrade safety + Investigation FK integrity. Phase P starts here so the dialect port has the smaller, current-only schema to work against.
  - [x] P.1.a — **Trace findings.** Investigation seed (`apps/investigation/demo_data.py:310`) writes two `_inserts(...)` blocks: 3 rows into `ar_ledger_accounts` (from `INV_LEDGER_ACCOUNTS`) + 6 rows into `ar_subledger_accounts` (from `INV_SUBLEDGER_ACCOUNTS`). The dim tables carry a self-FK (`ar_subledger.ledger_account_id → ar_ledger`) plus an inbound FK from `ar_ledger_transfer_limits`. Both per-prefix Investigation matviews (`<prefix>_inv_pair_rolling_anomalies`, `<prefix>_inv_money_trail_edges`) only read from `<prefix>_transactions` — zero references to `ar_*_accounts`. The whole dim-table family is FK-integrity-only for Investigation's seed; nothing live needs the rows.
  - [x] P.1.b — **Decision: drop the FK dependency entirely + scope the cleanup to all v5-shape leftovers.** Tracing for P.1.a turned up more dead code than just the AR dim tables: (1) the global `transactions` + `daily_balances` tables in `schema.sql` are never populated by `_apply_demo` (which writes only to `<prefix>_*` tables via `emit_l2_seed`); (2) the entire `ar_*` view surface (~15 views including `ar_unified_exceptions`) is referenced by zero app dataset SQL; (3) `apps/investigation/demo_data.py::generate_demo_sql` is itself v5-shape, planting into the now-dead unprefixed tables — only `demo seed` CLI + tests still call it. Decision: drop **all of it** (schema.sql, schema.py wrapper, the legacy Inv demo_data, the dead CLI commands), not just the dim tables. Per-prefix `emit_l2_schema` + `emit_l2_seed` are the only live emit surface going forward.
  - [x] P.1.c — Dropped `apps/investigation/demo_data.py` + the `from quicksight_gen.apps.investigation.demo_data import generate_demo_sql` lines in `cli.py` (`demo seed` command body) and `tests/test_investigation.py` (the trivial smoke test).
  - [x] P.1.d — Dropped `src/quicksight_gen/schema.sql` (1379 lines).
  - [x] P.1.e — Dropped `src/quicksight_gen/schema.py` + the `from quicksight_gen.schema import generate_schema_sql` import + the `cur.execute(schema_sql)` + `cur.execute("REFRESH MATERIALIZED VIEW ar_unified_exceptions;")` lines in `_apply_demo`.
  - [x] P.1.f — Dropped `demo schema` + `demo seed` CLI command definitions in `cli.py`.
  - [x] P.1.g — Dropped `tests/test_demo_data.py` (entire file: every assertion tested the dropped v5 seed); dropped the `test_demo_seed_rejects_l1_dashboard` test in `tests/test_l1_dashboard.py` (the command no longer exists). 1224 unit tests pass post-cleanup.
  - [x] P.1.h — Dropped `"schema.sql"` from `pyproject.toml` `package_data`.
  - [x] P.1.i — README + CLAUDE.md sweep landed: dropped the `demo schema` / `demo seed` CLI examples, dropped the `schema.py` / `schema.sql` tree references, rewrote the v5 carry-over story as the P.1 retirement note. Subagent then swept `docs/walkthroughs/` (19 files updated): every AR / PR app reference, every dropped dataset name, every `ar_*` dim/view mention got updated to the four-app vocab + per-prefix base-table convention. The 7 remaining `demo schema` / `demo seed` CLI invocations across walkthroughs got retargeted to `emit_schema(l2)` / `emit_seed(l2, scenario)` Python calls or `quicksight-gen demo apply`.
  - [x] P.1.j — Full unit suite green (1224 passed, 2 skipped). `mkdocs build --strict` clean. Commit landed.

- [x] **P.2 — Dialect helper layer (Postgres-only first).** `common/sql/dialect.py` ships `Dialect` enum + 22 helpers covering every Postgres-isolated construct cataloged in `docs/audits/p_2_dialect_catalog.md` (type names, casts, typed NULL, JSON IS check, date/time arithmetic, DDL idempotency, materialized views, recursive CTE).
  - [x] P.2.a — `Dialect` enum (POSTGRES + ORACLE) lives in `common/sql/dialect.py`.
  - [x] P.2.b — `docs/audits/p_2_dialect_catalog.md` enumerates ~12 dialect-divergent construct families with example sites, dialect-specific output, and the helper function name. Confirms `JSON_VALUE` / `IS JSON` / `||` are already SQL/JSON-standard portable across PG 17+ and Oracle 12.2+ (no helper needed).
  - [x] P.2.c — 22 helpers ship; Postgres branch returns the current bytes verbatim. Oracle branch raises `NotImplementedError("…Phase P.3 fills this in.")` until P.3 lands. 44 unit tests in `tests/test_sql_dialect.py` cover every Postgres branch + assert every Oracle branch raises with the expected message.
  - [x] P.2.d — `common/l2/schema.py` threads `dialect: Dialect = Dialect.POSTGRES` through `emit_schema`, `refresh_matviews_sql`, `_emit_l1_invariant_views`, `_render_limit_breach_cases`, `_render_pending_age_cases`, `_render_unbundled_age_cases`. The `_render_*_cases` helpers replaced inline `"NULL::numeric"` / `"NULL::bigint"` with `typed_null(type, dialect)` calls; `refresh_matviews_sql` now calls `refresh_matview()` + `analyze_table()` per matview. Big template strings (`_SCHEMA_TEMPLATE`, `_L1_INVARIANT_VIEWS_TEMPLATE`, `_INV_MATVIEWS_TEMPLATE`) stay Postgres-only for P.2; the audit captures the open question for P.3 (split-or-template). All existing assertion tests stay green — bytes-identical Postgres output verified across the 1268-test suite.
  - [x] P.2.e — `common/sql` joined `[tool.pyright].include`. Full unit suite (1268 tests, +44 new) green.

- [ ] **P.3 — DDL emission for both dialects.** `common/l2/schema.py` + `schema.sql` emit Postgres OR Oracle DDL based on dialect.
  - [ ] P.3.a — Implement Oracle branch on every helper from P.2 (BOOLEAN → NUMBER(1), TEXT → CLOB / VARCHAR2(4000), TIMESTAMP type, identity columns via sequences + triggers OR `GENERATED ... AS IDENTITY`, MV refresh syntax).
  - [ ] P.3.b — Materialized view DDL: Oracle uses `CREATE MATERIALIZED VIEW … BUILD IMMEDIATE REFRESH ON DEMAND`; Postgres uses `CREATE MATERIALIZED VIEW`. Refresh: Oracle `BEGIN DBMS_MVIEW.REFRESH('<name>'); END;`; Postgres `REFRESH MATERIALIZED VIEW <name>`.
  - [ ] P.3.c — Update `refresh_matviews_sql(l2_instance, dialect)` to take a dialect; emit the right call per matview.
  - [ ] P.3.d — `schema.sql` either splits into `schema_postgres.sql` + `schema_oracle.sql` OR (if helpers reduce divergence enough) becomes a single template the emitter renders. Decide based on residual divergence after P.3.a.
  - [ ] P.3.e — Snapshot tests: emit DDL for spec_example + sasquatch_pr against both dialects; lock the bytes.
  - [ ] P.3.f — Commit.

- [ ] **P.4 — Dataset SQL dialect-aware.** Every `apps/<app>/datasets.py` SQL string moves through dialect helpers. Biggest churn in Phase P.
  - [ ] P.4.a — L1 dashboard datasets (~14): drift, ledger drift, drift timelines (×2 pre-aggs), overdraft, limit breach, pending aging, unbundled aging, supersession audit, today's exceptions UNION, daily statement summary, daily statement transactions, raw transactions.
  - [ ] P.4.b — L2 Flow Tracing datasets (~5): rails, chains, transfer templates, hygiene exceptions UNION, etc.
  - [ ] P.4.c — Investigation datasets (~5): recipient fanout, volume anomalies, money trail (`WITH RECURSIVE` → Oracle's unmarked recursive `WITH`!), account network, anetwork accounts dropdown.
  - [ ] P.4.d — Executives datasets (~2): account coverage, transaction volume.
  - [ ] P.4.e — App Info canary dataset.
  - [ ] P.4.f — Snapshot test per dataset: emit SQL against both dialects; lock both byte sequences.
  - [ ] P.4.g — Commit per app or single sweep depending on diff size.

- [ ] **P.5 — Demo apply for both dialects.** `[demo-oracle]` extra adds `oracledb`; `demo apply` reads `cfg.dialect`, picks the right connector + bind syntax + commit semantics.

  > **🚧 USER GATE — local Oracle DB needed before P.5 starts.** This is the first substep that hands-on validates the Oracle path against a real database. Before kicking off P.5, the user needs:
  >
  > - A local Oracle 19c Standard Edition instance reachable from the dev machine (Docker `gvenzl/oracle-free:23-slim-faststart` works for dev too — same image P.7 uses in CI; the 19c-vs-23 SQL surface is close enough that 23 catches most issues, with a final 19c verify happening at P.9.b).
  > - The connection details captured in a sibling config: `run/config-oracle.yaml` with `dialect: oracle` + `demo_database_url: oracle+oracledb://...` + the host / port / service-name shape from P.6's loader. (Existing `run/config.yaml` stays as the Postgres copy.)
  > - The Postgres demo DB stays up too — the test suite + e2e need to run against both dialects from P.5 onward.
  >
  > Same gate applies to P.9.b (live deploy verify against Oracle).

  - [ ] P.5.a — Add `[demo-oracle]` extra to `pyproject.toml`. Use `oracledb` (the new wrapper, no Oracle Client install needed in thin mode).
  - [ ] P.5.b — Abstract the connection + bind layer in `cli.py::_apply_demo` so the same orchestration works against either dialect (psycopg2 `%s` ↔ oracledb `:1`).
  - [ ] P.5.c — Seed primitive emitter (`common/l2/seed.py`) emits dialect-appropriate INSERT syntax (column quoting, multi-row vs single-row, sequence/identity, commit cadence).
  - [ ] P.5.d — Hash-lock the Oracle seed output separately from Postgres; both dialects round-trip deterministic seed bytes.
  - [ ] P.5.e — `quicksight-gen demo apply --all -c <oracle-config.yaml>` end-to-end against a local Oracle Free container. Verify matview refresh + L1 invariant rows surface correctly.
  - [ ] P.5.f — Commit.

- [ ] **P.6 — QuickSight datasource for Oracle.** `common/datasource.py` becomes dialect-aware; `config.yaml` `dialect:` field drives which `DataSourceParameters` shape gets emitted on deploy.
  - [ ] P.6.a — Read `dialect:` field from `config.yaml`; default `postgres` for back-compat. Validate against `Dialect` enum.
  - [ ] P.6.b — `build_datasource(cfg)` branches on dialect: `RdsParameters` for Postgres (current shape), `OracleParameters` for Oracle (host / port / database SID or service-name).
  - [ ] P.6.c — Tag the deployed datasource with `Dialect: postgres|oracle` for the cleanup sweep + multi-instance dashboard list legibility.
  - [ ] P.6.d — Smoke test: emit datasource JSON for both dialects; verify QS API accepts (mock + live).
  - [ ] P.6.e — Commit.

- [x] **P.7 — Containerized CI for both dialects.** GHA `integration` job after the `test` matrix runs `quicksight-gen demo apply --all` against `postgres:17` + `gvenzl/oracle-free:latest` service containers, then verifies per-prefix matview row counts. Runs on push to main + PR. (Validated 2026-04-30: green on first try, ~12 min wall clock.)

- [x] **P.8 — Dialect-aware docs.** `Schema_v6.md` top callout + `Forbidden SQL patterns` table + `how-do-i-configure-the-deploy.md` (dialect field, both URL shapes, RDS Oracle TLS quirk, oracledb thin-mode), `how-do-i-map-my-database.md` (Postgres-or-Oracle framing), README install matrix incl. `[demo-oracle]`. (Landed 2026-04-30.)

- [x] **P.9 — Cross-dialect deploy verify + e2e against the 4-cell matrix.** Phase-Q ergonomic lifts pulled forward so the matrix could run end-to-end:
  - [x] P.9.0 — `scripts/p9_deploy_verify.sh` codifies manual P.5/P.6 verify across the 4 cells (postgres + oracle × spec_example + sasquatch_pr). Hits live Aurora + RDS Oracle.
  - [x] P.9.0a — `--l2-instance` flag added to `demo apply` + `deploy` (Phase-Q lift, was task #488).
  - [x] P.9.0b — Per-instance prune fix: `_all_dataset_filenames` now threads `l2_instance`; sibling enumeration uses the active L2 prefix instead of the bundled default. Without this, single-app generate against a non-default L2 pruned the sibling apps' files.
  - [x] P.9.0c — First-deploy dataset-prep retry: `_create_analyses` now retries on `PREPARED_SOURCE_NOT_FOUND` for ~5 min, covering Oracle's slow first-time data source validation.
  - [x] P.9.0d — `scripts/p9_e2e.sh` per-cell e2e wrapper + `QS_GEN_TEST_L2_INSTANCE` fixture override. Lets the existing browser e2e suite run against any deployed cell.
  - [x] P.9.0e — `tests/integration/verify_demo_apply.py` parameterized on `--prefix` + `--smoke` mode (smoke = ≥1 row check, for L2s without locked counts).
  - [x] P.9.0f — Result: 4 cells × deploy ALL CLEAR (4 dashboards each, 35 datasets each). E2E surfaced 5 real Oracle failures + 12 known-gap harness errors (see P.9c, P.9d).

- [x] **P.9a — Standardize on TZ-naive TIMESTAMP across both dialects.** Single `timestamp_type(dialect) -> "TIMESTAMP"` returns plain TZ-naive on both engines. Drops the prior split (`timestamp_tz_type` + `pk_safe_timestamp_type`) and the `+TZ` offset on seed Oracle literals. Schema is now byte-identical between PG and Oracle for every timestamp column. Schema_v6 callout: "Timezone normalization is the integrator's contract." Re-locked 4 seed_hashes (spec_example + sasquatch_pr × pg + oracle).

- [x] **P.9b — SPEC + L2 validator: Rail uniqueness on (transfer_type, role).** Per-leg discriminator uniqueness enforced at load time as rule U6 (validate.py::_check_unique_rail_discriminators). Direction intentionally NOT in the discriminator — surfaces two-rail-per-direction patterns for resolution. SPEC documents the rule + 3 resolution paths (distinct directional types / bidirectional merge / TransferTemplate chain) under Rails. sasquatch_pr (9 collisions) + _kitchen.yaml (1 collision) refactored to directional transfer_types (ach_inbound / ach_outbound, wire_inbound / wire_outbound / wire_concentration, cash_deposit / cash_withdrawal, internal_debit / internal_credit, return_nsf / return_stoppay); limit_schedules updated to reference new outbound types; seed_hash re-locked. Fuzzer post-process suffixes colliding transfer_types with rail index. 4 dedicated rejection + acceptance tests added under U6.

- [x] **P.9c — Investigate Oracle KPI visual non-render in QuickSight.** Root cause: not a QuickSight runtime issue — `common/sheets/app_info.py` hardcoded Postgres-specific SQL on both dialects. The Liveness KPI ran `SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'` against Oracle (no `information_schema`, no `'public'` schema → SQL parse error → blank visual). The Matview Status table used `'name'::text` and `COUNT(*)::integer` casts (Postgres-only syntax → Oracle parse error). Fix: `_liveness_sql(dialect)` branches on `cfg.dialect` (Postgres reads `information_schema.tables`; Oracle reads `USER_TABLES`); `_matview_status_sql` drops the redundant casts (column types are pinned by `MATVIEW_STATUS_CONTRACT` so the casts were no-ops on Postgres anyway). 2 dedicated dialect-aware tests added under `test_app_info.py`. Verified: Oracle output regenerated cleanly (`SELECT COUNT(*) AS table_count FROM USER_TABLES`); Postgres output unchanged (still uses `information_schema`).

- [x] **P.9d — Make harness fixtures Oracle-aware.** Lifted dialect-aware DB helpers from cli.py into `common/db.py`: `connect_demo_db(cfg)` branches psycopg2 / oracledb; `execute_script(cur, sql, dialect)` handles per-dialect multi-statement execution + Oracle PL/SQL block boundaries; `oracle_dsn(url)` translates SQLAlchemy-style URLs. Harness `harness_db_conn` fixture, `apply_db_seed`, and `drop_prefixed_schema` all dialect-aware now. Oracle teardown wraps each per-object DROP in a PL/SQL `BEGIN EXCEPTION WHEN OTHERS` block to swallow ORA-942 / ORA-12003 (the missing-IF-EXISTS gap). `oracledb` added to dev extras so the harness can hit Oracle without a separate install. 13 new unit tests in `test_common_db.py` cover oracle_dsn translation, statement splitting (incl. PL/SQL blocks + comment-only buffers), and the connect_demo_db dispatch.

- [ ] **P.9e — SPEC + L1 invariant: Rail conformance (Transactions matching no Rail).** Companion to U6: U6 enforces uniqueness of declared rails at load time, P.9e detects runtime postings that match no rail. SPEC gap: the SPEC implicitly assumes every Transaction is the firing of some declared Rail but doesn't say what happens when one isn't. Real causes: ETL bug, source-system change, fraud/system error, migration adjustments.
  - [ ] P.9e.a — SPEC §"System Constraints": add new rule "Rail conformance: every CurrentTransaction SHOULD match exactly one Rail's `(transfer_type, role)` discriminator. Transactions matching zero Rails surface as 'unmatched rail' exceptions; matching multiple Rails surface as 'ambiguous rail' (defense-in-depth — U6 prevents at load-time)." SHOULD per RFC 2119 — surfaces as a dashboard exception, not a hard failure (posting-time refusal is too aggressive: legitimate edge cases like migration adjustments would fail).
  - [ ] P.9e.b — `common/l2/schema.py`: emit a per-prefix matview `<prefix>_unmatched_rail` shaped after `limit_breach`. Body uses an inline VALUES CTE listing every declared `(transfer_type, role, rail_name)` triple derived from `inst.rails` at emit time (one row per rail × leg-role; union roles fan out — same expansion as `_check_unique_rail_discriminators`). Matview LEFT JOINs `<prefix>_current_transactions` against the CTE; selects rows where `rail_name IS NULL`. Columns: `transaction_id, transfer_id, transfer_type, account_id, account_role, account_name, signed_amount, posted_at, business_day_end, status`. Plus a `match_count` column so a future query can also surface multi-match rows (expected to be empty post-U6).
  - [ ] P.9e.c — Wire into Today's Exceptions UNION rollup so the new exception kind appears alongside drift / overdraft / limit_breach / stuck_*. Add `unmatched_rail` to the kind discriminator vocabulary.
  - [ ] P.9e.d — New L1 dashboard sheet "Unmatched Rail" — table view showing the non-conformant postings grouped by `(transfer_type, account_role)` + count + drill to detail. Right-click → Daily Statement (M.2b.7 pattern).
  - [ ] P.9e.e — Plant a coverage scenario in the demo seed: 1-2 transactions with a `transfer_type` value that doesn't match any rail's discriminator (e.g., `transfer_type='legacy_migration'` against a CustomerDDA). Re-lock seed_hash.
  - [ ] P.9e.f — Tests: unit test on the matview SQL emit (asserts every declared rail gets a row in the VALUES CTE); test_demo_data scenario coverage assertion (≥1 unmatched_rail row planted); browser e2e via the existing harness layer (matview row check + dashboard render).
  - [ ] P.9e.g — Re-deploy + re-run the 2×2 matrix; verify the new sheet renders in both dialects.

- [ ] **P.9f — Oracle e2e cleanups (gates P.10).** First full Oracle e2e cell (oracle × spec_example) revealed 11 failures. Categorized by root cause from `tests/e2e/failures/`:
  - [ ] P.9f.a — Harness assertion `%s` placeholders. `_harness_l1_assertions.py:137` and `_harness_inv_assertions.py:148, 169` use psycopg2 `%s` placeholders that oracledb rejects (`DPY-4009: 0 positional bind values are required but 1 were provided`). Causes 6 of 11 failures (L1 + Inv plants visibility tests fail at Layer 1 before the dashboard even gets queried). Branch on `cfg.dialect` like `_harness_cleanup.py` already does. Quick fix; unblocks honest measurement of what's left.
  - [ ] P.9f.b — JSON path concat at QS-runtime. Oracle's JSON_VALUE requires the path arg to be a string literal at parse time; runtime concat (`'$.' || <<$pKey>>`) works on PG but `ORA-40597`s on Oracle. ~5 sites in `apps/l2_flow_tracing/datasets.py`. Architectural fix: introduce a `<<$pPath>>` parameter carrying the full `'$.key'` path so QS substitutes literally before the database parses (the analysis-side pPath can be derived from the existing pKey via a calc field).
  - [ ] P.9f.c — Per-dataset Oracle SQL syntax fixes. P.9f.e surfaced 5 distinct Oracle error classes across 13 of 35 datasets (PG × spec_example):
    - **ORA-00923 FROM not found** — `SELECT '...'` without FROM clause (Oracle requires `FROM dual` for constant SELECTs). Hits the App Info matviews-status placeholder + a few other "no real data" SELECTs.
    - **ORA-00936 missing expression** — `DATE(t.posting)` PG-style function call on a timestamp; Oracle wants `TRUNC(...)` or `CAST(... AS DATE)` (use the existing `to_date(..., dialect)` helper).
    - **ORA-25154 column part of USING clause cannot have qualifier** — `LEFT JOIN ... USING (col)` followed by `t.col` (qualified). Oracle requires the USING-bound column to be unqualified everywhere; PG allows the qualifier.
    - **ORA-40597 JSON path syntax** — same as P.9f.b (folded into that fix).
    - **ORA-00911 invalid character** — likely stray trailing `;` or other character. Per-dataset trace via `verify_dataset_sql -v --config oracle ...`.
    Concrete dataset list per kind enumerable via `python tests/integration/verify_dataset_sql.py --config run/config.oracle.yaml --l2-instance tests/l2/spec_example.yaml` and re-running against `tests/l2/sasquatch_pr.yaml`.
  - [ ] P.9f.d — Re-run 4-cell e2e matrix. Confirms (a)+(b)+(c) bring Oracle into PG parity. After this, P.10 ships clean.
  - [ ] P.9f.e — **Testing-layer gap fix: dataset CustomSQL parse/execute smoke per dialect.** Today's query-layer tests (`tests/integration/verify_demo_apply.py` + P.3.d.6 schema snapshot) catch matview row counts + DDL shape, but never parse/execute the dataset's `PhysicalTableMap.CustomSql.SqlQuery` against a real DB. That SQL is only exercised when QuickSight renders a visual — so Oracle SQL bugs (the JSON_VALUE concat, the ORA-00923) only surface at browser-test time, with a 30+ min feedback loop and no actionable error message. New test: walk every emitted dataset, substitute `<<$pName>>` placeholders with default values from the parameter declaration, wrap as `SELECT * FROM (<customsql>) WHERE ROWNUM <= 1` (Oracle) / `SELECT ... LIMIT 1` (Postgres), execute via `connect_demo_db(cfg)`, assert it parses + returns. Fast (per-dataset <1s); per-dialect; would have caught both P.9f.b and P.9f.c at unit-test time.

- [x] **P.10 — Iteration gate + v7.0.0 cut.**
  - [x] P.10.a — Decide release cut: **v7.0.0** — additive (Postgres-only users see no behavior change) but touches every SQL surface; major bump flags the breadth.
  - [x] P.10.b — Bump `__version__` to `7.0.0`; write RELEASE_NOTES entry covering: dialect support, the v5 carry-over removal (technically a breaking change for anyone on schema.sql v5), the `dialect:` config field, the `[demo-oracle]` extra, the new walkthrough, the memory rewrite.
  - [x] P.10.c — Commit + tag + push.
  - [ ] P.10.d — Confirm release pipeline runs green for both Postgres + Oracle integration jobs.
  - [ ] P.10.e — Memory sweep: any other Postgres-only assumptions that need updating?

---

## Phase Q — Dashboards + Docs polish + CLI ergonomics

**Goal.** Ship a polished release where the dashboards reflect what an operator + executive actually need (the M-/N-/P- phases focused on getting them to *render*; Q focuses on getting them *right*), and the docs site reflects the post-polish dashboards cleanly. Plus the long-pending CLI/yaml ergonomics work as final polish.

**Sequencing rationale.** Dashboard review FIRST so docs/screenshots/walkthroughs in Q.2 capture the post-fix state — re-screenshotting after Q.1 is one pass; doing docs first means a second pass after Q.1 lands. Q.3 (CLI) is independent and slots last so the release narrative keeps the dashboards-then-docs theme clean.

### Q.1 — Dashboard review + targeted fixes

Order the meta sweeps first so per-app fixes inherit them:

- [x] **Q.1.a — Currency + axis formatting (meta).** Sweep every visual across every shipped app:
  - [x] Amount/money columns format as USD currency (`$1,234.56`). Q.1.a.1 + Q.1.a.2 (Measure side); Q.1.a.7 + Q.1.a.8 (Dim side + table-cell wire shape).
  - [ ] Bar chart axis titles use plain English (not raw column names). DEFERRED to Q.1.a.3 — auto-derive from column names; partial coverage via Q.1.c manual labels on the most visible chart (L1 Today's Exceptions).
  - [x] Walk via the tree primitive; add a unit-test invariant where feasible. Tests in `test_tree.py::TestMeasure` + `TestDim` for currency, plus `test_dataset_contract.py::TestOracleLowercaseAliasWrapper` for the Oracle wire-shape regression net.

  Q.1.a.5 added prefix + bulleted deploy stamp to App Info.
  Q.1.a.6 added `quicksight-gen probe` CLI + harness wiring so future
  per-visual datasource errors fail loud instead of silent.
  Q.1.a.8 fixed every Oracle visual (was failing ORA-00904 on QS's
  quoted-lowercase column lookups vs Oracle's case-folded UPPERCASE
  metadata) by wrapping every Oracle CustomSQL with a lowercase
  re-aliasing outer SELECT.

- [x] **Q.1.b — Universal date-filter sweep.** Add the M.2b.1 universal-date-filter pattern to sheets that lack one:
  - [x] L1 Supersession Audit
  - [x] L1 Transactions
  - [ ] L2 Exceptions — DEFERRED: unified-exceptions matview is a current-state hygiene check, no native date column. Adding one needs a matview-shape decision (which date semantically applies for "Dead Rails" or "Unmatched Transfer Type"?).
  - [x] Investigation Money Trail (DATE_RANGE picker on `posted_at`; "All" hidden via existing `hidden_select_all=True`)
  - [x] Executives Account Coverage / Transaction Volume / Money Moved

- [ ] **Q.1.c — Per-app punch-list items:**
  - [x] **L1 Supersession Audit** — add KPI to the right of the keys: count of supersessions with no reason (target value = 0). _(Q.1.c — analysis-level CalcField + half-width KPI pair.)_
  - [x] **L1 Today's Exceptions** — bar chart axes need plain-English labels. _(Q.1.c — `Check Type` / `Open Exceptions` via `category_label` / `value_label`.)_
  - [x] **L1 Daily Statement** — date picker defaults to yesterday. (4/25 Posted Money Records SQL error already fixed by P.9f / Q.1.a.8 Oracle case-fold wrapper — probe shows clean.)
  - [x] **L2 Getting Started** — text box has missing spaces; suspect YAML word-wrap stripping. _(Q.1.c — `" ".join(text.split())` reflow on the YAML literal-block description before rendering.)_
  - [x] **Investigation Info** — matview-status SQL exception fixed by Q.1.a.8 Oracle case-fold wrapper (probe shows zero datasource errors across all sheets on both dialects).
  - [ ] **Executives Transaction Volume + Money Moved** — add metadata grouping. DEFERRED: needs L2-instance-aware metadata key dropdowns (cascading Key + Value like L2FT Rails sheet) plus a dataset pivot to expose metadata as a dim. Bigger than a punch-list item; queue as Q.1.c.6 follow-up.

- [x] **Q.1.d — Sign-off walkthrough (post-fix).** User confirmed Q.1's results clean across both dialects after walking the deployed dashboards.

- [x] **Q.1.e — Re-deploy + harness green for both dialects.** PG 15/15 in 8:39; Oracle 15/15 in 8:10. Probe shows zero datasource errors across all 4 dashboards on both dialects.

### Q.2 — Documentation step-back (informed by Q.1's final state)

**Smell underneath:** the IA was built around 4 separate apps (PR, AR, Investigation, Executives) and the L1+L2FT consolidation collapsed PR+AR into one operator dashboard without re-shaping the doc tree. Customization handbook + ETL guide still talk about apps as separate documentation surfaces, with orphan "GL Reconciliation Handbook" / "Payment Reconciliation Handbook" links scattered across `customization.md` / `etl.md` / `investigation.md`. Reference vs Walkthrough vs Concept boundaries blur.

- [ ] **Q.2.a — Mechanical cleanup** (~30 min, no IA changes):
  - Drop stale AR/PR refs in `handbook/customization.md` (lines 54-55, 234-237, plus the "Phase K (AR Exceptions redesign)" stale-phase marker at line 51).
  - Drop stale AR/PR refs in `handbook/etl.md` (lines 19, 43, 64, 153-154 — including the dead `demo etl-example payment-recon` / `account-recon` commands).
  - Drop orphan handbook links in `handbook/investigation.md` (lines 130, 133).
  - Fix 3 "Schema v3" link-text mislabels that point to `Schema_v6.md` (`etl.md:49,165`, `customization.md:223`).

- [ ] **Q.2.b — IA review (plan-mode first).** Read every nav entry end-to-end, write "what's where today" map, propose 2-3 IA shapes with tradeoffs (e.g., role-onramp-first vs reference-first; merge handbook + concepts vs keep split). User picks; then execute.

  ### Q.2.b.audit — What's where today

  7 top-level nav sections, ~60 pages. Page counts in parens.

  - **Home** (1) — landing.
  - **For Your Role** (5+1) — onramp pages: operator, integrator, ETL engineer, executive, compliance analyst.
  - **Concepts** (12+2) — Accounting (6 patterns: double-entry / escrow / sweep / vouchering / consistency / loops) + L2 model (6 primitives: account / template / rail / transfer-template / chain / limit-schedule).
  - **Background** (5+1) — institution tour: accounts / rails / transfer-templates / chains / limit-schedules. Persona/fixture-flavored (Sasquatch the bank).
  - **Walkthroughs** (30+1) — three buckets: L1 Sheets (11 per-sheet pages), Investigation (4 question-shaped), ETL (6 how-do-I), Customization (9 how-do-I).
  - **Reference** (8+1) — handbook/* (4 dashboards + ETL + Customization), Schema_v6, L1_Invariants.
  - **API Reference** (7+1) — SDK / tree primitive surface (App / Visuals / Data / Filters / Drills / common foundations).

  ### Q.2.b.smell — Boundary blur observations

  1. **Reference + Walkthroughs duplicate doors.** `handbook/etl.md` lives in Reference but its child walkthroughs/etl/* live in Walkthroughs. Same for Customization. Readers hit the same topic twice from different sections, often without realizing.
  2. **L1 Sheets pages are reference dressed as walkthrough.** Each per-sheet page describes *what's on the sheet* (KPIs, columns, drills) — that's reference content, not "how do I X". They sit under Walkthroughs because they shipped with the M.2b walkthrough lift, not because they answer questions.
  3. **Background = fixture flavor with too much real estate.** "Institution tour" is one paragraph of "this is the bank" plus 5 list-of-things pages. Useful context but it's a top-level section claiming equal weight with Concepts / Reference. Most readers will never click it.
  4. **For Your Role is meta-IA, not a section.** It cross-cuts every other section (operator wants L1 reference + concepts/accounting; integrator wants L2 reference + customization walkthroughs). Currently flat-listed as just-another-section; the role onramp shape is different from the rest.
  5. **Concepts/Accounting vs Concepts/L2 — two distinct things lumped as one.** Accounting concepts (double-entry, escrow, sweep) are universal patterns; L2 model concepts are this codebase's primitives. Different audiences, different durability.

  ### Q.2.b.shapes — Three IA proposals

  **Shape A: Boundary cleanup, keep the current frame** (smallest change)

  Hierarchy stays 6-7 sections; only cross-section moves happen.

  - Move L1 Sheets per-sheet pages from Walkthroughs → Reference, nested under "L1 Reconciliation Dashboard" (so the reference tree becomes: dashboard overview → per-sheet drilldowns).
  - Merge Background → Concepts as a new "Background" subsection (or drop Background and inline its content into the L2 model concepts, since each Background page mirrors a concept primitive).
  - Walkthroughs stays question-shaped only (Investigation / ETL / Customization).
  - Reference grows: per-app handbooks now have nested per-sheet drilldown pages.

  Tradeoffs: Lowest churn (no rewrites, just nav re-shuffling). Doesn't address "two doors to ETL/Customization" — handbook/etl.md still in Reference, walkthroughs/etl/* still in Walkthroughs, just no longer surrounded by L1 Sheets noise.

  **Shape B: Question vs Reference split** (front-of-house redesign)

  Compresses 7 → 4 top sections around "what to do" vs "what it is".

  - **For Your Role** — unchanged (onramp).
  - **Quickstarts** — current Walkthroughs section (Inv questions / ETL / Customization), with the L1-sheet and Investigation handbook pages re-purposed as the lead-in / "where to start" for each cluster.
  - **Reference** — handbooks (per-dashboard / per-sheet) + Schema_v6 + L1_Invariants + Background scenario + Concepts (Accounting + L2 model). Single shelf for "what is X".
  - **API Reference** — unchanged.

  Tradeoffs: Cleanest "what to do" vs "what is X" mental model. Reference becomes a fat section (~30 pages incl. Concepts + Background); needs a strong Reference index page to navigate. Loses the Concepts top-level — readers hunting for "double-entry posting" need to know it's under Reference.

  **Shape C: Audience-first home page** (For-Your-Role becomes the front door)

  Currently the For Your Role pages are dead-end onramps; this shape elevates them to be the primary navigation surface.

  - **Home** — replaced by a curated "pick your role" landing that branches to the 5 role pages.
  - Each **Role page** is a handcrafted onramp that links into Walkthroughs / Reference / Concepts in the order that role needs.
  - Walkthroughs / Reference / Concepts / API Reference become "library shelves" the role pages curate from. They're still navigable directly.

  Tradeoffs: Most reader-friendly for first-time visitors who know their role. Maintenance cost: 5 role pages × ~30 walkthroughs + 8 reference docs + 12 concepts = curating 200+ links by hand. Drift risk when a new walkthrough lands and no role page learns about it.

  ### Recommendation

  **Shape A** if you want to keep iterating on content without restructure churn — lowest cost, addresses the L1 Sheets misclassification, doesn't solve the ETL/Customization double-door issue.

  **Shape B** if you want to address the "two doors" smell and accept that Reference becomes a single shelf — best long-term mental model but a one-time bigger commit.

  **Shape C** if the next 6 months will see meaningful onboarding traffic (new integrators, evaluators) — pays for itself in onboarding clarity but only if the 5 role pages get the curation effort they deserve.

  My pick if forced: **Shape A** for Q.2.b (low-cost cleanup), with Shape B/C deferred to a future phase if onboarding becomes a measured pain point.

  ### Q.2.b.decision — User pick: Shape C (audience-first), with Shape B as the long-term destination

  Rationale: about to introduce the tool to a lot of people; the
  role-picker front door is the highest-leverage onboarding
  surface. Shape C → Shape B is a transition to make once Shape
  C reveals which library shelves get the most curation traffic.

  ### Q.2.b.exec — Shape C execution checklist

  Substeps planned out so the Shape C work doesn't drift into a
  vague "rewrite docs" state. Each is small + commit-shaped.

  - [x] **Q.2.b.exec.1 — Reshape Home as role picker.** Replace
    `docs/index.md`'s "what apps ship + all sections overview"
    structure with role-picker primary + library-shelves
    secondary. Done; mkdocs --strict clean.
  - [ ] **Q.2.b.exec.2 — Nav reorder (mkdocs.yml).** Move "For
    Your Role" to first nav position (currently 2nd, after
    Home). Add comments noting Shape C frame + Shape B
    transition path. Confirm libraries (Concepts / Background /
    Walkthroughs / Reference / API) stay accessible.
  - [ ] **Q.2.b.exec.3 — `for-your-role/index.md` disposition.**
    Currently mirrors Home shape; with Home doing role-pick the
    section index is redundant. Decide: keep terse (re-direct to
    role pages) or drop and use the section sidebar directly.
  - [ ] **Q.2.b.exec.4 — Role page audit for Shape C fit.** Read
    each role page for "primary navigation surface" fitness.
    Operator + Integrator already touched in Q.2.d. Sanity-check
    Executive / ETL Engineer / Compliance Analyst — each should
    work as a primary entry, not just a sidebar onramp.
  - [ ] **Q.2.b.exec.5 — Cross-link audit.** Each library shelf
    (Concepts overview, Walkthroughs overview, Reference
    overview, etc.) should link back UP to "For Your Role" so
    readers who arrive shelf-first know the curated paths exist.
    Skip for Shape C → Shape B will collapse Background + add
    other shelf-level links.
  - [ ] **Q.2.b.exec.6 — Concepts split disposition.** Concepts
    has Accounting + L2 model lumped. Independent topics. Two
    paths: keep sub-tabs (current state, no work) or split into
    two top-level sections. Recommend keep-as-is for Shape C;
    revisit at Shape B transition.
  - [ ] **Q.2.b.exec.7 — Background section disposition.**
    Background = institution tour (5 pages), persona-flavored.
    Decide: keep top-level, rename to "Demo Institution Tour", or
    absorb into Concepts/L2 model. Recommend keep + rename for
    Shape C.
  - [ ] **Q.2.b.exec.8 — `mkdocs build --strict` + click-through.**
    Verify no dead links. Click each role page from the new Home,
    and each library link from the role pages.
  - [ ] **Q.2.b.exec.9 — Commit + tick PLAN Q.2.b.**

  ### Q.2.c.exec — Screenshot pipeline at 1280×900 + collapsed-by-default

  User picks: 1280×900 viewport. Screenshot sections collapsed
  by default wherever possible.

  - [ ] **Q.2.c.exec.1 — Screenshot CLI / extension.** Add a
    `quicksight-gen export screenshots --app <APP> --viewport
    1280x900 -o <DIR>` command that uses ScreenshotHarness
    against deployed apps. Replaces ad-hoc scripts in `scripts/`
    that were AR/PR-specific.
  - [ ] **Q.2.c.exec.2 — Capture for all 4 deployed apps.** Run
    against PG-deployed dashboards (canonical). Output ~40
    screenshots (4 apps × ~10 sheets) at 1280×900. Land them in
    `docs/walkthroughs/screenshots/` (or new path TBD by Shape C
    layout).
  - [ ] **Q.2.c.exec.3 — Collapse pattern.** Pick the mkdocs-
    material syntax: either `<details><summary>` raw HTML, or
    `??? note "Screenshot"` admonition (folds by default). Apply
    to one walkthrough as the pilot to validate render.
  - [ ] **Q.2.c.exec.4 — Sweep existing screenshot embeds.** Find
    every `![…](…)` referencing a screenshot in handbook + walk-
    through pages, wrap in the chosen collapse pattern. Likely
    a sed-style replace.
  - [ ] **Q.2.c.exec.5 — Visual review.** Open the rendered site;
    confirm collapse defaults work + re-screenshot any sheet
    that looks bad at the new viewport (a screenshot might need
    a tall override if a visual gets cut).
  - [ ] **Q.2.c.exec.6 — Commit + tick PLAN Q.2.c.**

- [ ] **Q.2.c — Re-screenshot with sane viewport.** Meta-problem from PLAN: screenshots are all way too tall (avoiding scroll-cutoff but at the cost of readability). Pick a viewport size that works for both desktop reading + reasonable scroll height (likely 1280×900 or 1440×1080). Run `screenshot_harness.py` for every app at the new viewport. Replaces the existing per-app screenshot fleet.

- [ ] **Q.2.d — Operator/Integrator onramp prose pass.** Address PLAN notes:
  - Operator "what are we not asking you to learn" reword to stress L1 + L2 are important.
  - Integrator onramp re-prose (currently sparse).

- [ ] **Q.2.e — `mkdocs build --strict` + ship the regenerated site.**

### Q.3 — CLI / yaml ergonomics around schema (was task #488)

The pre-Phase-Q backlog item — slotted last as polish.

- [ ] **Q.3.a — Materialize SPEC's "Workflow Ideas":** `generate config (demo|template)`, `apply schema`, `apply data`, `apply dashboards`, `generate training`. Acceptance: a fresh integrator runs end-to-end from one YAML.
- [ ] **Q.3.b — yaml field naming / config-vs-L2 boundary review.** Today's split between `run/config.yaml` (account, region, datasource, dialect, theme defaults) and the L2 institution YAML (rails, chains, accounts, theme override) has accumulated friction points; tighten the boundary based on what actually got threaded in M-/N-/O-/P-.

### Q.4 — Iteration gate + release

- [ ] **Q.4.a — Decide release cut** (likely v7.1.0 — additive polish + docs IA shift; not a breaking schema change, but the IA / nav re-org may want a major bump if any external links break).
- [ ] **Q.4.b — Bump `__version__` + RELEASE_NOTES entry covering Q.1–Q.3 changes.**
- [ ] **Q.4.c — Commit + tag + push; release pipeline green on both dialects.**

---

## Phase R — Realistic demo seed (3-month baseline + embedded plants)

**Why this phase, why now.** Today's demo seed plants ONE example of each L1 SHOULD-violation kind on a small subset of the L2's rails. Enough to populate every dashboard sheet; not enough to demonstrate what the tool actually does for a real institution. The "is this dashboard showing me the empty state because the L2 doesn't fire here, or because the seed didn't plant here?" ambiguity hits new readers hard — and the user is about to introduce the tool to a lot of people. Investigation Volume Anomalies has no statistical signal because the rolling 2-day SUM + stddev needs a baseline; with today's seed it's computing z-scores against ~5 transactions.

Phase R inverts the seed shape: a **3-month healthy baseline** of hundreds-to-thousands of rows per Rail, with the existing plant primitives **embedded inside that baseline** as exception signal in the noise. Acceptance: a new viewer opens the demo dashboard and immediately sees that this is a working bank's ledger with a handful of real exceptions surfacing — not a synthetic skeleton.

**Sequencing rationale.** Phase R lands BEFORE Q.2.c (re-screenshot at 1280×900) so the docs ship with screenshots that show the realistic baseline + visible exceptions, not the thin synthetic data. Q.2.b.exec.* (nav reorder) and Q.2.d remainder don't depend on seed quality and can run in parallel with R.

**Scope guardrails.**
- 3-month rolling window anchored on `today` (so re-runs always have current-looking data — same anchor convention as today's plants).
- Per-Rail volume scales with the Rail's role: high-volume rails (e.g., daily ACH origination, card settlement) land hundreds of legs; low-volume rails (e.g., monthly fee accrual) land ~tens. Driven by a heuristic from the L2 declaration shape, not a hand-tuned table.
- Plant density: most Rails are healthy (zero violations); a few have a small handful (1-3 exceptions); ~one or two per L2 instance go visibly broken (10-20 violations) so the Today's Exceptions KPI has shape.
- Determinism: `random.Random(SEED)` everywhere; SHA256 hash-lock test re-locked once the generator stabilizes.

### R.1 — Generator design

- [ ] **R.1.a — Volume heuristic.** Function `target_leg_count(rail, l2_instance, window_days=90)` returning per-Rail target. Inputs: `posting_requirements` shape (single-leg vs multi-leg vs aggregating), `LimitSchedule` cap if any, `max_pending_age` / `max_unbundled_age` if any. Heuristic: aggregating rails fire daily/EOM (high volume); single-leg fee rails fire low; two-leg internal transfers somewhere in between. Reviewable per-Rail output table so the user can sanity-check.
  - A: sounds good!
- [ ] **R.1.b — Amount distribution: lognormal per Rail** (decision per R.1.b review — lognormal's long right tail produces the natural outliers Investigation Volume Anomalies needs to compute meaningful z-scores against). Per-Rail (mu, sigma) defaults derived from rail role: GL sweeps + concentration target large means, customer DDA postings smaller means + wider sigma, fee accruals very small + tight sigma. Bounded above by `LimitSchedule.cap` when present so baseline never accidentally trips limit-breach (plants do that intentionally in R.3). No round-number bias — money should look like money.
  - A: lognormal (so we get outliers for the investigation screen), the rest sounds good
- [ ] **R.1.c — Time-of-day + day-of-week + day-of-month distribution.** Banking-hours bias for human-driven rails (card sales, wires); 24h spread for automated rails (sweeps, EOM accruals). Day-of-week: weekends + US bank holidays drop to near-zero volume across the board (decision per follow-up Q2 — option (a)). Day-of-month: aggregating rails respect their L2-declared cadence — `Aggregating: monthly_eom` fires only on the last business day of the month; `Aggregating: daily_eod` fires daily with the EOD parent posting late in the day. Posting timestamps drive the daily-statement KPI shape.
  - A: all sound good
- [ ] **R.1.d — Account-balance state machine** + **per-Rail RNG sub-streams** (decision per follow-up Q1). Maintain per-account balance state across the 90-day window so legs don't accidentally violate overdraft / limit-breach. Starting balances seed from a small per-account-type lookup; daily evolution = sum of signed_amount across that account's legs. Plant overlay (R.3) intentionally violates this — the baseline must NOT. RNG contract: each Rail gets its own `random.Random(seed_for_rail(rail_name))` sub-stream so iterating on one Rail's plant doesn't perturb other Rails' baselines. **Concurrency is not a concern**: the seed generator runs single-threaded (one Python process emits SQL); the DB apply runs single-threaded (one cursor, sequential statements); the e2e harness runs per-test under pytest-xdist but each worker is its own process with its own seed import — no cross-process shared state. Per-Rail sub-streams are isolated by Rail and never used concurrently.
  - A: sounds good, the key is to use the seeded random generator throughout as a random source so the results are predictable
- [ ] **R.1.e — Multi-leg transfer construction** (**children-first** ordering for aggregating rails). Each Transfer's legs net to zero (per the L1 invariant). Aggregating Rails: child legs post first throughout the day/period, then a higher-Entry parent row (`Supersedes = BundleAssignment`) retroactively bundles them — matches the real bookkeeping pattern where the bundler runs at EOD/EOM after the children have accumulated. Unbundled-aging plants are the few children that NEVER got bundled (in R.3). Non-aggregating chains stay parent → child via `parent_transfer_id` since those parents fire first and trigger the children synchronously.
  - A: on the chain firings, the children will come temporally first since the parents are bundling them to make a parent system whole
- [x] **R.1.f — Spec doc + review gate.** Half-page describing the generator's output shape (volume per rail, amount range per rail, time-of-day shape). User signs off before R.2 implementation begins so we don't burn a day building the wrong shape. Also: audit the L2 e2e tests as part of this gate — see R.5.d for the test-repoint substep.
  - A: sounds good, we should also plan to repoint the tests at this output since I don't think the L2 e2e tests actually test layer 2 now
  - Sign-off 2026-04-30: "spec looks good, should be transformed into a reference doc at the end of this" — reference-doc lift tracked as R.7.e.

  #### R.1.f spec — Generator output shape

  **Window + anchor.** 90-day rolling window ending on `today` (the date the seed is generated). Re-running on a different day produces a different rolling window — same anchor convention as today's plants. Any "today" reference inside generated SQL uses the anchor passed at generation time, not `now()` at apply time, so the SHA256 hash-lock test stays deterministic for a fixed anchor.

  ##### 1. Volume heuristic — `target_leg_count(rail, window_days=90) -> int`

  Inputs: `rail.transfer_type`, `rail.posting_requirements` shape (single-leg vs two-leg vs aggregating), the rail's `aggregating` flag (`null` / `daily_eod` / `monthly_eom`), and the rail's `source_role` / `destination_role` (used to infer "is this customer-facing or internal-plumbing"). Output: count of FIRINGS (each firing produces 1 or 2 legs depending on rail shape).

  | Rail kind | Heuristic | ~ firings / 90d |
  |---|---|---|
  | Customer-facing inbound (ach_inbound, wire_inbound, cash_deposit) | 4 firings/business day per customer-account, scaled by account count | 200-1500 |
  | Customer-facing outbound (ach_outbound, wire_outbound, cash_withdrawal) | 2 firings/business day per customer-account | 100-700 |
  | Customer fee accrual (monthly) | 1 firing/customer-account/month | 6-150 |
  | Internal transfer (debit / credit / suspense) | 1 firing/business day per parent-account | 50-150 |
  | Aggregating daily_eod (ZBA sweep, ACH origination sweep) | 1 firing/business day | ~63 |
  | Aggregating monthly_eom (fee monthly settlement) | 1 firing/last-business-day-of-month | ~3 |
  | Concentration sweep (wire_concentration) | 1 firing/business day | ~63 |
  | Card sale (merchant-acquiring) | 8 firings/business day per merchant-account | 500-2500 |
  | Merchant payout (payout_ach / wire / check) | 1 firing/business day per merchant-account | 60-200 |
  | External card settlement | 1 firing/business day | ~63 |
  | ACH return (NSF, stop-pay) | 0.05 of `CustomerInboundACH` firings (rare) | 10-75 |

  The function returns an int; per-Rail variance is added by the lognormal sampler in §2 (i.e., the sampler decides "today this Rail fires N times" where N is Poisson around the daily target). Total expected over 90 days for sasquatch_pr: **~50k-80k legs**; for spec_example: **~5k-10k legs**.

  ##### 2. Amount distribution — per-rail-role lognormal `(mu, sigma)` defaults

  All amounts in USD. `sample = exp(Normal(mu, sigma))` then quantize to cents. Bounded above by `LimitSchedule.cap` when one applies (clamp+resample, not truncate, so the distribution shape stays clean).

  | Rail role | mu | sigma | Median $ | 99th pct $ |
  |---|---:|---:|---:|---:|
  | Customer ACH (in/out) | 6.5 | 1.2 | $665 | $11,000 |
  | Customer wire (in/out) | 9.0 | 1.0 | $8,100 | $84,000 |
  | Customer cash (deposit/withdrawal) | 5.5 | 0.8 | $245 | $1,580 |
  | Customer fee accrual | 2.5 | 0.4 | $12 | $31 |
  | Internal transfer | 8.0 | 1.5 | $2,980 | $96,000 |
  | Aggregating daily_eod (sweep) | 11.0 | 0.8 | $59,800 | $385,000 |
  | Aggregating monthly_eom (fee batch) | 9.5 | 0.5 | $13,400 | $43,000 |
  | Concentration sweep | 12.0 | 0.7 | $163,000 | $830,000 |
  | Card sale | 4.5 | 0.9 | $90 | $720 |
  | Merchant payout | 9.0 | 1.1 | $8,100 | $105,000 |
  | External card settlement | 11.5 | 0.6 | $98,700 | $400,000 |
  | ACH return | matches the original ACH leg's amount | — | — |

  Per-Rail override hook: if a rail YAML carries an optional `seed_amount: {mu: ..., sigma: ...}` block in the future, the generator uses that instead of the role default. Out of scope for R.2 — not needed for spec_example or sasquatch_pr.

  ##### 3. Time distribution

  - **Day-of-week:** weekends (Sat/Sun) drop to **0 firings** for ALL rails. US bank holidays (~3 in any 90-day window) drop to **0 firings** for ALL rails. Holiday calendar = `holidays.US()` if the `holidays` package is available, else a small hard-coded list of fixed-date federal holidays + observed shifts (acceptable for the demo since exact list isn't load-bearing).
  - **Day-of-month:** rails with `aggregating: monthly_eom` fire **only on the last business day of each month** (3 firings over 90 days). Rails with `aggregating: daily_eod` fire on every business day. Non-aggregating rails fire uniformly across business days.
  - **Time-of-day:** rails with `source_origin: ExternalForcePosted` (Fed-driven) cluster 09:00-15:00 Eastern (banking hours). Rails with `aggregating: daily_eod` post their parent at 17:00-19:00 Eastern (after children). Card sales weighted to 10:00-22:00 Eastern. Internal transfers + sweeps spread across the business day. Default: uniform 09:00-17:00 Eastern.

  ##### 4. RNG sub-stream layout — `seed_for_rail(rail_name) -> int`

  ```python
  BASE_SEED = 42  # same constant the existing test_demo_data.py uses, for legacy hash continuity
  def seed_for_rail(rail_name: str) -> int:
      return BASE_SEED ^ (zlib.crc32(rail_name.encode("utf-8")) & 0xFFFFFFFF)
  ```

  Each Rail gets one `random.Random(seed_for_rail(rail.name))` instance. The instance is threaded through every helper that touches that Rail — leg loop, amount sampler, time-of-day sampler, account picker, plant overlay (R.3) for that Rail. Account-balance state-machine helpers (cross-Rail) use a single `random.Random(BASE_SEED)` instance for any randomness they own (account picks, starting balances).

  ##### 5. Balance-state-machine starting balances

  Per `account_role` lookup, sampled per-account at generator init:

  | account_role kind | Starting balance distribution |
  |---|---|
  | DDAControl (customer DDA control account) | lognormal(mu=8.5, sigma=1.0) — median $4,900, range $500-$80k |
  | MerchantDDAControl | lognormal(mu=10.0, sigma=0.8) — median $22,000 |
  | InternalSuspense / InternalRecon | $0 (these accounts net to zero EOD) |
  | DDAControl-internal-GL (CashDueFRB, etc.) | lognormal(mu=14.0, sigma=0.5) — median $1.2M |
  | ConcentrationMaster | lognormal(mu=15.0, sigma=0.4) — median $3.3M |
  | ExternalCounterparty (FRB Master, processors) | $0 (we don't track external balances; they're the external-counter side of force-posted legs) |
  | Anything else | $0 |

  ##### 6. Multi-leg + chain ordering

  - **Single-leg rail:** one row per firing with the leg posted at the sampled time-of-day.
  - **Two-leg rail:** two rows per firing with shared `transfer_id`, `signed_amount` summing to zero, both posted at the same time-of-day (within ms).
  - **Aggregating rail (children-first):** child legs accumulate throughout the day at sampled times-of-day. EOD (or EOM) parent posts at 17:00-19:00 Eastern as a higher-Entry row with `Supersedes = BundleAssignment` that retroactively assigns the day's children to its `transfer_id`. Unbundled-aging plants (R.3) are children that **never** get a parent assignment.
  - **Non-aggregating chain (parent → child):** parent fires first; child fires synchronously (same business day, child time-of-day = parent time-of-day + small delay). Required-completion vs Optional-completion respects the Chain's declared `Required` flag (Required = ~95% completion rate, Optional = ~50%).

  ##### 7. L2 coverage assertion set (R.5.d preview)

  New harness file `_harness_l2_coverage_assertions.py`. Per-instance assertions:

  - **Per Rail:** `assert N_legs(rail) >= max(target_leg_count(rail) * 0.5, 5)` — at least half the heuristic target landed (Poisson variance can shave the actual count) AND no rail produces fewer than 5 legs (proves the rail isn't dead).
  - **Per Chain:** `assert N_completed_pairs(chain) >= 1` — every declared chain has at least one parent + child fire. For Required chains additionally: `assert completion_rate(chain) >= 0.80` (allowing some exception slack from R.3 plants).
  - **Per TransferTemplate:** `assert sum(actual_net) == declared expected_net` for >= 80% of template instances (some R.3 plants intentionally violate to surface on the L2 Exceptions sheet).
  - **Per LimitSchedule:** `assert max_daily_outbound(parent_role, transfer_type) <= cap` for the baseline (R.3 plants intentionally breach to populate the Limit Breach sheet).
  - **Volume Anomalies signal:** `assert z_score(planted_spike, baseline) >= 3.0` per R.5.c.

  ##### 8. Out of spec / open

  - **Per-Rail YAML overrides** (`seed_amount`, `seed_volume_multiplier`) — out of scope; baseline heuristic is enough for the existing two L2 instances. Add when a third instance lands and needs a per-rail tweak.
    - A: agreed
  - **Cross-currency** — all amounts USD. No FX rails declared today.
    - A: agreed
  - **Memo / metadata-payload realism** — generator emits valid metadata structures (the L2's declared keys with random plausible values) but doesn't aim for narrative realism. The Investigation walkthroughs reference specific amounts + counterparties; those land via R.3 plants, not the baseline.
    - A: agreed

  Sign-off bar: the user reads this spec, flags anything off, then R.2 starts.

### R.2 — Implementation

- [x] **R.2.a — Baseline generator skeleton in `common/l2/seed.py`.** New entry point `emit_baseline_seed(l2_instance, *, window_days=90, anchor=date.today())`. Returns SQL string (same shape as today's `emit_seed`). Skeleton emits a valid header + stub markers for R.2.b/e fills; per-Rail RNG sub-stream layout (`_seed_for_rail` = BASE_SEED ^ crc32) and business-day calendar (`_business_days_in_window` excluding weekends + optional `holidays.US()`) wired in. Stubs in place for `_initialize_starting_balances` (R.2.b §5), `_emit_baseline_for_rail` (R.2.b/c), `_emit_baseline_chains` (R.2.d), `_emit_baseline_daily_balances` (R.2.e). 16 unit tests in `tests/test_l2_baseline_seed.py` pin the entry-point API + helper determinism.
- [x] **R.2.b — Per-Rail leg loop.** Use volume heuristic from R.1.a. Maintains the account-balance state machine (R.1.d). Implements `_RailKind` classifier + `_RAIL_KIND_PARAMS` lookup table covering R.1.f §1's volume + §2's lognormal + §3's time-of-day band; `_classify_role` + `_STARTING_BALANCE_BY_ROLE_KIND` table for §5; `_materialize_baseline_template_instances` (20 customer-DDA per template, 5 merchant + 5 other); Poisson per-day firing sampler; lognormal amount sampler with clamp+resample on LimitSchedule cap; account-balance state machine update per leg; `_eligible_accounts_for_role` picker. Aggregating rails return `[]` for now — R.2.c handles bundling. Headline volume: 55,637 baseline legs for sasquatch_pr at the 2026-04-30 anchor (lands inside R.1.f §1's 50k-80k target band even with aggregating rails still empty).
- [x] **R.2.c — Multi-leg transfer assembly.** R.1.e implementation. Single-leg rails: one row per firing. Two-leg rails: two rows per firing with shared transfer_id, signed_amount summing to zero. Aggregating rails: many child legs share one parent transfer_id (bundled), spread across the day/EOM window. Implementation: `_populate_bundle_map` pre-computes `(child_rail, business_day) → bundle_id` for every aggregating rail's `bundles_activity` reference; `_emit_baseline_for_aggregating_rail` emits the per-period EOD/EOM parent legs (single-leg + two-leg) with `transfer_id` matching the bundle id; `_last_business_day_per_month` enforces monthly_eom-only firing. Children get `bundle_id` stamped at emit time so the L1 stuck_unbundled view stays clean for the baseline. Headline: sasquatch_pr now emits 55,836 baseline legs (199 added by aggregating-rail parents on top of R.2.b's 55,637 children); 10k+ bundle markers in the SQL.
- [x] **R.2.d — Chain firings.** When the L2 declares a Chain (parent rail fires → child rail fires), generator produces matching parent + child rows so the L2FT Chains sheet has Required-completion data. Required vs Optional chains generate at different completion rates (Required ~95%; Optional ~50%). Implementation: `state.firings` now records every parent firing (`(transfer_id, business_day, amount)` per rail name); `_emit_baseline_chains` walks `instance.chains` grouped by `(parent, xor_group)` and rolls per-firing completion via a separate RNG; xor_group siblings pick exactly one winner per parent firing via `crc32(parent_transfer_id) % len(group)`; `_emit_chain_child_leg` emits the child rail's legs (single-leg + two-leg) with `transfer_parent_id` set + amount sampled from the child rail's own lognormal kind. TransferTemplate-parented chains are skipped for now (only Rail parents tracked in `state.firings`); ~5,300 chain child firings on sasquatch_pr's 6 declared chains. Total baseline now 61,150 legs — solidly inside R.1.f §1's 50k-80k target band.
- [x] **R.2.e — Daily-balance materialization.** For every (account, day) pair in the window, compute the EOD balance from the leg state machine and emit a `<prefix>_daily_balances` row. The drift matview computes `stored - SUM(signed_amount)`; baseline rows must keep that at zero. Implementation: `_emit_baseline_daily_balances` walks `state.eod_balances` (populated by R.2.b/c/d's per-leg snapshots), looks up account metadata via `_build_account_meta_map`, and emits one `_balance_row` per (account, day) using the existing helper. Honors `instance.role_business_day_offsets` for non-midnight-aligned snapshots (M.4.4.14 mechanism). Drift invariant guarantee comes free from the state machine: `balances[account_id]` updates BEFORE the snapshot, so `daily_balances.money == SUM(signed_amount)` through the snapshot moment. Headline: 2,250 daily_balance rows for sasquatch_pr; full baseline now 63,400 rows / 47 MB SQL.

### R.3 — Plant overlay (re-use existing primitives)

- [x] **R.3.a — Plant primitives stay where they are** (`common/l2/seed.py`'s drift / overdraft / limit-breach / stuck-pending / stuck-unbundled / supersession primitives). Plants now land *additively* on the baseline rather than constituting the whole seed. Implementation: new `emit_full_seed(instance, scenarios, *, baseline_window_days=90, anchor=None, dialect)` entry point in `common/l2/seed.py` that emits baseline first, then plants concatenated; CLI `demo apply` swaps `emit_seed` → `emit_full_seed` so deployed dashboards get both layers. Plant transfer_id namespaces (`tr-drift-*`, `tr-overdraft-*`, `tr-breach-*`, etc.) are disjoint from baseline (`tr-base-*`, `tr-base-bundle-*`, `tr-base-chain-*`) so the layers can't collide. 5 emit_full_seed tests verify additive volume, namespace disjointness, and determinism.
- [ ] **R.3.b — Per-Rail plant density.** Driven by the Rail's `posting_requirements` shape (e.g., a Rail with `max_pending_age: PT4H` is a candidate for stuck-pending plants; a Rail with no `max_pending_age` is not). Default density: 0-3 plants per Rail; spec_example: lower density; sasquatch_pr: higher density.
- [ ] **R.3.c — One "broken Rail" per L2 instance.** For visual hierarchy: pick one Rail to be visibly broken (10-20 plants of one kind). Today's Exceptions KPI then has a magnitude that matters; the broken Rail surfaces immediately on the L2 Exceptions sheet's bar chart.
- [ ] **R.3.d — Investigation plant overlay.** Cascadia/Juniper-style fanout + anomaly + chain plants on the new baseline so Volume Anomalies' z-scores are statistically meaningful (the rolling 2-day SUM + stddev now has 90 days of baseline transactions to draw against).

### R.4 — Performance pass

- [ ] **R.4.a — Switch from one giant INSERT to chunked INSERTs.** Current seed is one statement; at 50-100k rows that's slow on both dialects. Chunk to ~1000 rows per INSERT. Consider Postgres `COPY FROM STDIN` and Oracle bulk-insert idioms (`INSERT ALL` or external table) if INSERT-chunked is too slow.
- [ ] **R.4.b — Benchmark `demo apply --all`.** Target: under 60s wall clock for the full baseline + plants on PG; under 90s on Oracle. Adjust generator volume defaults if it overshoots.
- [ ] **R.4.c — Generator runtime.** The Python-side generation itself (no DB roundtrips) should stay under 10s. Prefer list comprehensions + bulk string formatting over per-row appends.

### R.5 — Hash-lock + harness updates

- [ ] **R.5.a — Re-lock the SHA256 seed-hash test.** `test_seed_output_hash_is_locked` per app — paste the new hash once the generator is stable. Burns once on first land; protects against accidental drift afterward.
- [ ] **R.5.b — Update e2e harness assertions.** `assert_l1_plants_visible` + `assert_l2ft_matview_rows_present` may need updates if plant counts changed. Per the M.4.4.13 lesson: plants must surface in matviews + render on dashboards.
  - Note: the check will likely need to set filters in certain cases to narrow the plant on to the screen.
- [ ] **R.5.c — Volume Anomalies smoke.** New: assert that with 90 days of baseline, the rolling-2-day-stddev z-score on a planted spike is **> 3σ** (decision per follow-up Q4 — lands in the dashboard's "high" anomaly bar coloring band so it screams at first glance, not just "interesting"). Plant amount sized so it lands at mu + 3*sigma in the underlying normal that the lognormal samples from. Without this, "richer baseline" could land but Volume Anomalies still shows nothing.
- [ ] **R.5.d — L2 e2e test repoint.** Per R.1.f: today's L2FT harness asserts plants surface in the matview + the dashboard renders SOME content; it does NOT assert that every L2-declared primitive (Rail / Chain / TransferTemplate / LimitSchedule) actually has runtime evidence. With Phase R's exhaustive baseline that becomes asserttable: for every Rail in the L2 instance, assert N≥M legs in `<prefix>_current_transactions`; for every Chain, assert at least one parent + child firing pair; for every TransferTemplate with `expected_net=0`, assert that's actually true on its instances; etc. Likely turns into a new harness assertion file (`_harness_l2_coverage_assertions.py`) wired into `test_harness_end_to_end.py`. Audit + spec the assertion set as part of R.1.f's review gate so the tests get built alongside the generator.

### R.6 — Validation against deployed dashboards

- [ ] **R.6.a — Apply + deploy to PG.** `demo apply --all -c run/config.postgres.yaml --l2-instance tests/l2/sasquatch_pr.yaml -o run/out` then `deploy --all`.
- [ ] **R.6.b — Probe.** Use Q.1.a.6's `quicksight-gen probe --all` to confirm zero datasource errors against the new seed (catches per-Rail SQL surprises).
- [ ] **R.6.c — Eyes-on review.** Walk every dashboard sheet on the deployed PG instance. Acceptance bar: every L1 sheet shows a healthy baseline with visible exceptions; L2 Flow Tracing shows runtime evidence on every declared Rail / Chain / Template; Volume Anomalies has z-score signal; Money Trail's chain dropdown has multiple chains to choose from.
- [ ] **R.6.d — Repeat for Oracle.** `demo apply --all -c run/config.oracle.yaml ...`. Same probe + eyes-on bar.
- [ ] **R.6.e — "First impression" tune-up.** If the visual hierarchy is off (broken Rail too subtle, healthy baseline too noisy, etc.), adjust generator parameters and re-deploy.

### R.7 — Iteration gate + release

- [ ] **R.7.a — Decide release cut.** Phase R is meaningful enough to merit its own release — likely v7.2.0 (additive seed expansion; no breaking schema or CLI changes; existing demos regenerate cleanly).
- [ ] **R.7.b — Bump `__version__` + RELEASE_NOTES entry.** Cover the new "realistic baseline" demo + the per-Rail volume / amount profiles + the Investigation z-score signal.
- [ ] **R.7.c — Commit + merge to main + tag + push; release pipeline green.**
- [ ] **R.7.d — Resume Q.2.c (re-screenshot at 1280×900) against the v7.2.0 demo.**
- [ ] **R.7.e — Lift R.1.f spec out of PLAN.md into a docs-site reference page.** Once the implementation has stabilized + the headline numbers in the spec match what the generator actually produces, lift the design doc out of PLAN.md and into the docs site as durable reference. Likely target: `docs/handbook/seed-generator.md` (under Reference / handbook so integrators customizing for their own L2 instance can find it) OR `docs/reference/seed-generator.md` (if Q.2's IA work has carved a top-level Reference shelf by then). PLAN.md's R.1.f keeps a one-line pointer to the lifted doc.

---

## Backlog

Single grab-bag for everything not yet in a phase. Promote to a numbered phase entry when work starts. Full historical detail in `PLAN_ARCHIVE.md`.

### Punted from Phase M ship push

- **CLI workflow polish.** Materialize the SPEC's "Workflow Ideas" — `generate config (demo|template)`, `apply schema`, `apply data`, `apply dashboards`, `generate training`. Acceptance: a fresh integrator can run end-to-end from one YAML.
- **QS-UI kitchen-sink reference tool.** Standalone tool that consumes QS console "view JSON" output for every visual type and dumps it as a reference fixture. Defensive measure; deferred since the concrete editor-crash bugs got fixed.
- **Drop AR-only schema.sql carry-overs.** `ar_ledger_accounts` / `ar_subledger_accounts` dimension tables stay in `schema.sql` because Investigation's demo seed registers its own sub-ledgers there for FK integrity. Phase N's Investigation reshape decides whether Inv migrates off the AR dim tables — once it does, drop the carry-overs.

### L2 model gaps

- **Validator: every Transfer MUST match a Rail.**
- **Validator: no overlap on (role, transfer_type) entries.**
- **Multiple dashboards from one L2 instance** (shared prefix + naming).
- **PR dashboard → generic L2-validation dashboard** (re-skinning of L2FT for a different validation persona).
- **Lift seed primitives into `common/l2/seed.py`** (was M.2d.5).
- _(Promoted to Phase R — 3-month realistic baseline + embedded plants. See above.)_

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
