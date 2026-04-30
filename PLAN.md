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
    - [ ] N.3.l-ter — **DEFERRED to Phase O** (or its own sub-phase). Fuzzer expansion for Investigation matview coverage: add `InvFanoutPlant` / `InvAnomalyPlant` / `InvChainPlant` primitives in `common/l2/seed.py`, wire into `auto_scenario.default_scenario_for(mode="l1_plus_broad")`, re-lock seed_hash on `spec_example` + `sasquatch_pr`, tighten `_harness_inv_assertions.py` to assert specific planted rows surface. Skipped now because re-locking seed hashes without Aurora-side validation is risky; the L1-equivalent harness coverage proper requires the plant primitives to land first.
    - [x] N.3.m — Full unit suite + pyright + commit. Achieved at multiple commits along the way; final state: 1189 passed, pyright clean.
  - **Phase 5 — Drop legacy + docs.**
    - [x] N.3.n — Dropped the global `inv_pair_rolling_anomalies` + `inv_money_trail_edges` from `schema.sql` (truncated lines 1380-1563). Added explicit `DROP MATERIALIZED VIEW IF EXISTS` lines for upgrade safety. Updated `cli.py::_apply_demo` REFRESH calls to use the prefixed names.
    - [x] N.3.o — CLAUDE.md Investigation paragraph + demo apply paragraph + schema.sql comment reflect L2-fed status.
    - [ ] N.3.p — Aurora deploy verification of the L2-fed Investigation flow + planted Sasquatch Investigation persona (defer to combined N.3+N.4 deploy at end of N.4). The seed-data lift to common/l2/seed.py is the prerequisite (currently flat-table v5 plants don't surface in the prefixed Inv matviews).
  - **Cleanup carried into N.4** — `populate_app_info_sheet(theme=None)` fallback stays until Executives also migrates.

- [ ] **N.4 — Executives reshape + theme cleanup + Inv harness parity.** Closes Phase N's substantive work. Executives goes L2-fed, the deferred N.3.l-ter Inv plant primitives land here (so combined N.3+N.4 Aurora verify has actual data), the legacy `cfg.theme_preset` path gets fully removed, and the silent-fallback theme contract lands (no L2 theme block → no custom QS Theme resource emitted; AWS CLASSIC takes over).
  - **Phase 1 — App rewiring.**
    - [ ] N.4.a — Executives dataset SQL → prefixed base tables (`<prefix>_transactions` / `<prefix>_daily_balances`). Add `_require_prefix(cfg)` helper following N.3.d pattern.
    - [ ] N.4.b — `build_executives_app(cfg, *, l2_instance=None)`. Default to `default_l2_instance()` (same import path Investigation uses). Auto-derive `cfg.l2_instance_prefix`. Mirror L1.
    - [ ] N.4.c — Theme via `resolve_l2_theme(l2_instance)` in Executives; drop every `get_preset(cfg.theme_preset)` call. Pass `theme=theme` to `populate_app_info_sheet`.
    - [ ] N.4.d — CLI `_generate_executives` accepts + passes `l2_instance`. Demo apply Exec flow updated to thread `l2_instance` through `build_exec_analysis` / `build_executives_dashboard`.
  - **Phase 2 — Tests + harness parity.**
    - [ ] N.4.e — `test_executives.py` for L2-fed shape. `_TEST_CFG.l2_instance_prefix="spec_example"`; dataset ID assertions become `qs-gen-spec_example-exec-*`; analysis name follows L2 theme prefix.
    - [ ] N.4.f — `tests/e2e/conftest.py` Exec fixtures: add `exec_l2_prefix`, prefix segments on `exec_dashboard_id` / `exec_analysis_id` / `exec_dataset_ids`. Mirrors N.3.l for Investigation.
    - [ ] N.4.g — `tests/e2e/_harness_exec_assertions.py` (new). "Datasets queryable" check (`SELECT COUNT(*) FROM <prefix>_transactions / <prefix>_daily_balances`). Wire into `test_harness_end_to_end.py` as Layer 1c.
    - [ ] N.4.h — **Inv plant primitives + harness tightening (was N.3.l-ter).** Add `InvFanoutPlant` / `InvAnomalyPlant` / `InvChainPlant` to `common/l2/seed.py`. Wire each into `auto_scenario.default_scenario_for(mode="l1_plus_broad")` so fuzz instances + sasquatch_pr seed Inv matview rows. Re-lock `seed_hash` on `spec_example` + `sasquatch_pr` (validated by N.4.o Aurora deploy). Tighten `_harness_inv_assertions.py`: replace `assert_inv_matviews_queryable` with `assert_inv_planted_rows_visible(db_conn, prefix, manifest)` mirroring `assert_l1_matview_rows_present` shape. Per-plant unit tests (rejection + happy path). ~400-500 LOC; the meatiest substep in N.4.
  - **Phase 3 — Theme path cleanup (the v6.1.0 trigger).**
    - [ ] N.4.i — Drop `populate_app_info_sheet(theme=None)` fallback. Make `theme: ThemePreset` required (not `theme: ThemePreset | None`). All four apps now pass `theme=theme`; the fallback path is unreachable. Removes the `(theme or get_preset(cfg.theme_preset)).accent` indirection.
    - [ ] N.4.j — Drop `cfg.theme_preset` field + CLI `--theme-preset` flag. ~70-site sweep: `Config` dataclass, CLI option + `_generate_*` kwargs + `cfg.theme_preset = ...` mutations, last `get_preset(cfg.theme_preset)` call in Executives, test fixtures, YAML loader, test config helpers, docs.
    - [ ] N.4.k — `build_theme(cfg, theme: ThemePreset) -> Theme | None`. Return `None` when `theme is DEFAULT_PRESET` (no L2-declared theme). CLI skips `theme.json` write + skips theme deploy when `None` — silent-fallback contract: AWS QS CLASSIC takes over for instances that didn't declare a theme. Comment explains the design intent.
    - [ ] N.4.l — Drop `get_preset()` if unused after N.4.j sweep, OR inline `resolve_l2_theme`'s use of `get_preset("default")` to a direct `DEFAULT_PRESET` reference.
  - **Phase 4 — Verify + close.**
    - [ ] N.4.m — Full unit suite + pyright; commit. Expect ~70-100 LOC churn from N.4.j + hash-relock fallout from N.4.h.
    - [ ] N.4.n — CLAUDE.md sweep. Executives section reflects L2-fed status. Architecture Decisions theme paragraph drops per-app-preset framing. Document the silent-fallback contract on `build_theme`.
    - [ ] N.4.o — **Combined N.3 + N.4 Aurora deploy verify.** Closes N.3.p + Exec validation:
      - Deploy L1 + L2FT + Inv + Exec against `sasquatch_pr.yaml` (one institution YAML, four apps).
      - Verify each dashboard renders with the forest-green theme baked in.
      - Verify Inv matviews populate (per N.4.h plants).
      - Verify the silent-fallback path: deploy a fresh L2 instance YAML with NO `theme:` block; verify dashboards render against AWS CLASSIC.
      - Re-lock both `seed_hash` values with the actual planted-bytes from the deploy.

- [ ] **N.5 — End-of-phase iteration gate.** Cut **v6.1.0** — L2 YAML is the only configuration surface for app shape + theme. All four apps L2-fed, no per-app theme presets, no hand-rolled persona globals.

---

## Phase O — Docs + training render pipeline

**Goal.** Handbook + training pages render against the L2 instance's vocabulary instead of today's hand-written Sasquatch-flavored copy. Replaces `mapping.yaml` substitution.

- [ ] **O.1 — Docs render pipeline.**
  - Handbook prose templated against L2 persona vocabulary. mkdocs render step that takes `(L2 instance, neutral templates) → rendered handbook`.
  - The deferred L.5 "always-emitted persona leaks" cleanup happens here naturally (see `PLAN_ARCHIVE.md` for the audit findings).
  - Per F12 (`PLAN_ARCHIVE.md` M.0.10): any sub-step that invokes `ScreenshotHarness` MUST run a DB warm-up `SELECT 1` against `cfg.demo_database_url` right before fetching the embed URL — Aurora Serverless cold-start otherwise surfaces as QS's generic "We can't open that dashboard" error.
  - **Major idea**: add a sheet at the end of each dashboard and load the documentation into the dashboard itself (sibling to the existing `Info` canary sheet).
    - ANSWER: I reviewed the audit of what quicksight does and it seems way too limiting.
  - **L2 topology diagram render** (deferred from M.3.10d). The L2 instance is a graph; render as SVG via Graphviz `dot` (hierarchical) or `neato`/`sfdp` (force-directed) and embed in the handbook. Three plausible cuts: account-rail-account topology, chain DAG, layered combination. The `build_chains_dataset` in `apps/l2_flow_tracing/datasets.py` (CHAINS_CONTRACT) is the pre-shaped input for the chain DAG cut.

- [ ] **O.2 — Training render pipeline.**
  - Training site rendered from L2 + ScreenshotHarness regenerated per L2 instance.
  - Includes the deferred L.8 Executives handbook + walkthroughs (see `PLAN_ARCHIVE.md` Backlog).
  - Same `SELECT 1` warm-up requirement as O.1.

- [ ] **O.3 — Iteration gate.** Docs + training render against any L2 instance the integrator points at. Handbook publishing pipeline supports per-customer renders.

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
