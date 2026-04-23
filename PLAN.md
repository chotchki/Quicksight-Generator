# PLAN — Phase K: persona-driven layout work (shipped)

K.1 + K.2 (+ v3.6.1 doc patch) + K.2a + K.3 + K.4 shipped — see `PLAN_ARCHIVE.md` for the rolled-up summaries and `RELEASE_NOTES.md` for the per-version detail.

# PLAN — Phase L: tree walker + builder pattern → v5.0.0

Goal: replace the constant-heavy, manually-cross-referenced dashboard construction in `apps/{payment_recon,account_recon,investigation}/{analysis,filters,visuals}.py` with a tree of typed builder objects in `common/`. Each app becomes one of three things composed top-down:

1. **L1 — Tree primitives** (`common/`). Persona-blind. The QuickSight API surface plus type-safe composition: `App → Dashboard / Analysis → Sheet → (Parameters | FilterGroups | Visuals | Controls)` plus cross-sheet filter wiring. The tree resolves IDs and cross-references for you (FilterGroup scope refers to a Visual node, not a string ID); the existing `models.py` dataclasses stay as the JSON-emission layer.
2. **L2 — Default app assemblies** (`apps/`). Generic bank-domain implementations of PR / AR / Investigation / Executives — persona-agnostic in code, build dashboards every implementer's bank can deploy unchanged. These are *examples* of how to drive the tree, the way Sasquatch is the example data.
3. **L3 — Demo overlay**. The Sasquatch persona — theme preset, demo seed generator, persona-specific Getting Started copy — composed *on top of* the L2 default tree. Implementers replace this layer to ship their own brand without forking L2.

The tree's existence is the test case for the layer separation: anything Sasquatch-specific that leaks into L1 or L2 means the API isn't right yet.

**Locked decisions** (from review):
- **No auto-derived IDs.** Resource IDs stay explicit. Auto-deriving from titles risks breaking deployed dashboard URLs and drill targets when titles change; it also collides easily (first-letter schemes break on synonym titles). The tree wires references for you, but the IDs themselves are author-supplied.
- **Tree primitives are persona-blind.** No `Sheet.if_persona(...)` hooks; no persona threading through the constructors. Persona awareness lives in the L3 overlay layer that wraps or replaces L2 nodes. Easier to add a hook later than to rip one out.
- **Emit through the existing `models.py` dataclasses.** No parallel JSON emission path. The tree's job is to assemble + cross-reference + validate; `to_aws_json()` stays the serialization contract. Reduces L's blast radius and keeps the e2e structure tests valid against L's output.
- **Aim for byte-identical or documented-diff JSON during porting.** Anything else is a regression that needs explanation. The structural e2e tests are the contract.
- **Drop the aggregate constants** (`ALL_FG_AR_IDS`, `ALL_FG_PR_IDS`, `ALL_FG_INV_IDS`, `ALL_P_AR`, `ALL_P_INV`, etc.) as each app ports — the tree IS the source of truth, walking it produces the same set.
- **Executives is the greenfield proof, not the spike.** Existing-app port (L.0 + L.2) comes first — porting against real complexity stress-tests the API against the worst case. Executives (L.6) lands after the API has been worked over by three ports + the layer-separation cleanup.
- **Cross-references are object refs, not string IDs.** `FilterGroup(scope=[visual_a, visual_b])` not `FilterGroup(scope_ids=["v-foo", "v-bar"])`. Same for drill destinations — `Sheet` references, not `SheetId` strings. This is the load-bearing decision for the strong-typing direction: the type checker catches scope-on-wrong-sheet, drill-into-nonexistent-sheet, and parameter-control-mismatched-shape at the construction line, not at deploy time. String-keyed lookups would lose this and reduce the tree to a typed-dict pattern.
- **mkdocstrings strict-mode is warn-only** through Phase L. Lots of API churn coming; a missing-docstring error gate would block iteration. Tighten to error in a follow-up docstring sweep once L lands.

**Iteration is expected.** The L.1 primitives are unlikely to land right on the first pass — both L.2 (first port against real complexity) and L.6 (greenfield by a first-time author) will surface API friction that calls back into L.1. When that happens, **re-open L.1 sub-steps and revise the primitives** rather than working around the friction in the calling code. The two natural iteration gates: after L.2 (does the API hold up for porting?) and after L.6 (does the API hold up for greenfield?). v5.0.0 is the destination, not a deadline.

- [x] **L.0 — Tree spike (`spike/l-tree-account-network` branch).** Smallest possible port to validate the tree primitives produce JSON that the existing `models.py` accepts and that the deployed dashboard renders unchanged. Acceptance: byte-identical (or documented-semantic-equivalent) JSON for the Account Network sheet. **Result: byte-identical on first run, no iteration needed.** Spike's primitives cherry-pick into L.1.
  - [x] L.0.1 — Read the existing Account Network sheet code end-to-end: `apps/investigation/analysis.py::_build_account_network_sheet`, the relevant builders in `visuals.py` (Sankeys + table), the relevant filter groups in `filters.py` (anchor + min-amount + scoped CategoryFilters), and the constants in `constants.py`. Cross-references catalogued: visual IDs into `SheetVisualScopingConfiguration.VisualIds`, parameter names into `ParameterControl` + `LinkToDataSetColumn`, dataset identifiers into both, calc-field column references into the analysis-level `is_anchor_edge` / `is_inbound_edge` / `is_outbound_edge` / `counterparty_display`.
  - [x] L.0.2 — Sketched minimal L1 types as plain dataclasses in `common/_tree_spike.py`: `SheetNode`, `VisualNode`, `ParameterControlNode`, `GridSlot`. Spike-scoped to the SheetDefinition level — analysis-level pieces (parameters, calc fields, filter groups, dataset declarations) are out of scope for L.0 and land in L.1. Visual + control nodes delegate to existing private builders via a `Callable[[], Visual]` factory; L.1 will lift those mechanics into typed `Visual` subtypes.
  - [x] L.0.3 — Wired cross-references as object refs per locked decision: `GridSlot.visual: VisualNode` (object ref), `SheetNode.place(visual_node, ...)` validates the node is registered on the sheet. Worked ergonomically — `add_visual()` returns the ref, calls to `place()` chain naturally. No circular-reference issues at the SheetDefinition scope.
  - [x] L.0.4 — Tree-built the Account Network sheet end-to-end alongside the existing builder; deep-diff via `_strip_nones(asdict(...))` (SheetDefinition isn't a top-level model so no `to_aws_json` on it — used the same dict-stripping shape Analysis emission uses). Test: `tests/test_l0_spike.py::test_account_network_sheet_byte_identical_through_tree`.
  - [x] L.0.5 — Diff was empty on first run. No iteration needed.
  - [x] L.0.6 — Findings captured below; cherry-pick decision: **lift the spike's primitives into L.1**.

  **L.0 Findings.**

  *Validated:*
  - Tree composition with object refs (`GridSlot.visual: VisualNode`) works ergonomically. `add_visual()` returns the ref; `place()` validates registration before slotting. Type checker carries the wiring.
  - The `emit()`-per-node interface generalizes naturally — every node returns its corresponding `models.py` instance; `SheetNode.emit()` walks children and assembles the `SheetDefinition`.
  - Existing private visual builders compose cleanly into the tree as factory callables. Spike didn't need to reimplement Sankey / table mechanics; L.1 lifts them at its own pace.
  - The `FilterControls=[]` (empty list, not `None`) detail mattered for byte-identity — `_strip_nones` preserves empty lists. Documented in the spike module so L.1 doesn't accidentally drop it.

  *To lift into L.1:*
  - The four spike types (`SheetNode`, `VisualNode`, `ParameterControlNode`, `GridSlot`) are the right starting shape. L.1 keeps the object-ref + `emit()` pattern and extends with: `App`, `Dashboard`, `Analysis`, `FilterGroup`, `ParameterDecl`, `CalculatedField`, `DatasetDeclaration`, `CrossSheetFilter`, drill actions.
  - Replace the `Callable[[], Visual]` factory pattern with typed `Visual` subtypes per visual kind (Sankey, Table, KPI, Bar, …) — typed fields drive `emit()` rather than delegating to a callable.
  - Move the layout constants (`_FULL`, `_TABLE_ROW_SPAN`, `_THIRD`, …) into a shared `common/` layout helper.
  - **ID-appears-once principle.** Each `SheetId` / `VisualId` / `FilterGroupId` / `ParameterName` literal appears at the constructor of the node that owns it — and only there. Every other reference is the local Python variable holding the node ref (`inbound`, `outbound`, `sheet`, `anchor_param`, etc.), so cross-references are object-typed. The spike demonstrates this for `SheetNode` and `VisualNode` — when L.1 lifts the visual mechanics into typed `Visual` subtypes, the underlying `SankeyDiagramVisual.VisualId` (and equivalents) is read off the parent node at emit time, not duplicated. Endgame: the per-app `constants.py` modules collapse — IDs live at the construction site of their owning tree node and nowhere else.

  *Not exercised by spike — must be designed in L.1:*
  - **Filter group cross-references** — `FilterGroup.scope = [visual_a, visual_b]`. Spike only modeled the SheetDefinition; filter groups live at analysis level. L.1 must validate that every scoped visual is on the sheet that the filter group's scope selects.
  - **Cross-sheet drill destinations** — `Sheet` refs in drill actions. The Account Network walk-the-flow is same-sheet self-reference and didn't surface this.
  - **Calc field references** — should they be tree nodes (so the tree validates `is_anchor_edge` is referenced in a field-well / filter that exists)? Or remain plain dicts? Lean toward tree nodes for symmetry, but defer the call to L.1.1 design pass.
  - **Parameter declarations** — App-level vs Analysis-level placement, and how controls reference them by object ref (not by string name).
  - **Dataset declarations** — App-level; logical identifier → ARN mapping. Same reference-by-object pattern.

- [ ] **L.1 — Tree primitives in `common/`.** New module(s) under `common/` (working name `common/tree.py`; split into a `common/tree/` package if it grows past ~600 lines). Acceptance: primitives module shipped with full unit coverage; `to_aws_json()` over a tree-built `App` round-trips through deploy paths (no missing fields); the L.0 spike's Account Network port re-implemented against the full primitive set still emits byte-identical JSON.
  - [ ] L.1.1 — Catalog every visual kind in use across the three apps (KPI, table, bar vertical, bar horizontal, pie, line, Sankey, Sankey-directional, σ distribution chart, etc.) and decide: one `Visual` class with a typed `kind`, or one subclass per kind? Pick by which makes cross-reference inference (FilterGroup scope) easier.
  - [ ] L.1.2 — Implement core structural types: `App`, `Dashboard`, `Analysis`, `Sheet`. Parent-child wiring; `Sheet.add_visual(...)` etc.; tree walks itself.
  - [ ] L.1.3 — Implement `Visual` (and subtypes if chosen). Field-well builders (Category / Value / SmallMultiples / Source / Target / Weight) typed against the dataset columns the visual reads.
  - [ ] L.1.4 — Implement `ParameterDecl` (string / integer / decimal / date variants matching the existing `models.py` parameter classes).
  - [ ] L.1.5 — Implement `FilterGroup` with cross-reference to `Visual` nodes. `FilterGroup(scope=[v1, v2])` not `FilterGroup(scope_ids=["v-id-1", "v-id-2"])`. Validation: every scoped visual must be on the same sheet (raise at construction).
  - [ ] L.1.6 — Implement `FilterControl` + `ParameterControl` variants used today (dropdown / slider / date-range). Wire each to its source `FilterGroup` or `ParameterDecl` by reference.
  - [ ] L.1.7 — Implement `CrossSheetFilter` (the AR Today's Exceptions Check Type pattern) + drill actions (left-click = `DATA_POINT_CLICK`, right-click = `DATA_POINT_MENU`, navigate / set-parameter ops). Drill destination = `Sheet` reference, not `SheetId`.
  - [ ] L.1.8 — Implement JSON emission: each tree node's `emit()` returns the existing `models.py` dataclass; tree-walk assembles the full `Analysis` + `Dashboard`. Round-trip test against a known-good output.
  - [ ] L.1.9 — Implement construction-time validation hooks: scope-on-same-sheet, drill source/destination shape compatibility (re-use `common/drill.py`'s `ColumnShape` from K.2), parameter-control type matches parameter declaration, dataset references resolve.
  - [ ] L.1.10 — Module docstrings on every public class + helper. These will feed L.9.10 (mkdocstrings auto-generated API reference).
  - [ ] L.1.11 — Unit tests: tree assembly, ID resolution, cross-reference resolution, validation rejections (bad scope, bad drill shape), JSON emission shape, builder ergonomics. Mirror the `test_drill.py` shape from K.2.
  - [ ] L.1.12 — Re-port the L.0 spike's Account Network sheet against the full L.1 primitives — same byte-identity bar. This is the gate for L.2.

- [ ] **L.2 — Port Investigation to the tree.** Smallest existing app + freshest code = lowest port risk and the natural follow-on to L.1. Acceptance: byte-identical (or documented-diff) `investigation-analysis.json` + `investigation-dashboard.json`; full unit suite green; e2e green at deploy time (28 Investigation tests + 3 deferred K.4.9 skips unchanged). **First iteration gate** — friction here calls back into L.1.
  - [ ] L.2.1 — Port Getting Started sheet (no filters / visuals beyond the rich-text boxes — the simplest sheet, gets the app-level skeleton in place).
  - [ ] L.2.2 — Port Recipient Fanout sheet (3 KPIs + ranked table + threshold slider + date range).
  - [ ] L.2.3 — Port Volume Anomalies sheet (KPI + σ distribution + ranked table; SELECTED_VISUALS scoping for the σ filter is a load-bearing case for the tree's scope API).
  - [ ] L.2.4 — Port Money Trail sheet (2 visuals — Sankey + hop-by-hop table — plus chain-root dropdown / max-hops / min-hop-amount controls).
  - [ ] L.2.5 — Account Network sheet — already validated through L.0 + L.1.12; this step just confirms it stays green inside the full app port (the directional Sankeys + table + walk-the-flow drills exercise the tree's drill action API end-to-end).
  - [ ] L.2.6 — App-level wiring: dashboard + analysis assembly, dataset declarations, cross-sheet filter wiring (none today on Investigation), parameter declarations, theme reference.
  - [ ] L.2.7 — Drop `ALL_FG_INV_IDS` + `ALL_P_INV` from `apps/investigation/constants.py`. The tree's emitted set replaces them.
  - [ ] L.2.8 — Update e2e structural tests (`tests/e2e/test_inv_dashboard_structure.py`) to walk the tree's emitted parameter / filter-group set instead of importing `ALL_*` constants.
  - [ ] L.2.9 — Diff `out/investigation-analysis.json` + `out/investigation-dashboard.json` before/after the port. Document any non-byte-identical diffs.
  - [ ] L.2.10 — Run full unit suite (`pytest`); fix regressions.
  - [ ] L.2.11 — Run full e2e suite (`./run_e2e.sh`); fix regressions.
  - [ ] L.2.12 — **Iteration gate** — review the L.1 friction surfaced during the port. If anything was awkward, list it as L.1 follow-up sub-steps and circle back to L.1 before starting L.3.

- [ ] **L.3 — Port Account Reconciliation to the tree.** Largest existing app (~7 sheets including Today's Exceptions / Exceptions Trends / Daily Statement, 14 exception checks, ~20 filter groups, ~80 visuals) — tests the tree primitives against the worst-case complexity. Acceptance: byte-identical AR JSON; full unit suite green; e2e green.
  - [ ] L.3.1 — Port Getting Started sheet.
  - [ ] L.3.2 — Port Balances sheet.
  - [ ] L.3.3 — Port Transfers sheet.
  - [ ] L.3.4 — Port Transactions sheet (origin multi-select + date filters; the tree's filter-control API gets a stress test here).
  - [ ] L.3.5 — Port Today's Exceptions sheet (unified table + 14 per-check filter groups + Check Type cross-sheet control — biggest single sheet in the codebase).
  - [ ] L.3.6 — Port Exceptions Trends sheet (3 cross-check rollups + per-check daily trend grid).
  - [ ] L.3.7 — Port Daily Statement sheet.
  - [ ] L.3.8 — App-level wiring (datasets, parameters, theme, cross-sheet filters incl. the AR-internal drills).
  - [ ] L.3.9 — Drop `ALL_FG_AR_IDS` + `ALL_P_AR` aggregates.
  - [ ] L.3.10 — Update e2e structural tests for AR.
  - [ ] L.3.11 — Diff JSON before/after; document any non-byte-identical diffs.
  - [ ] L.3.12 — Run full unit + e2e suites; fix regressions.

- [ ] **L.4 — Port Payment Reconciliation to the tree.** Medium complexity; the Payment Reconciliation tab's side-by-side mutual-filter pattern is the only PR-special-case the tree needs to express cleanly. Acceptance: byte-identical PR JSON; full unit suite green; e2e green.
  - [ ] L.4.1 — Port Getting Started sheet.
  - [ ] L.4.2 — Port Sales Overview sheet.
  - [ ] L.4.3 — Port Settlements sheet.
  - [ ] L.4.4 — Port Payments sheet.
  - [ ] L.4.5 — Port Exceptions & Alerts sheet.
  - [ ] L.4.6 — Port Payment Reconciliation tab — the side-by-side mutual-filter pattern (clicking an external txn filters its payments and vice versa) is unique to this sheet. Likely needs a `Sheet.add_mutual_filter_pair(table_a, table_b)` helper or similar; lift from `recon_filters.py`.
  - [ ] L.4.7 — App-level wiring (datasets, parameters, drill actions across the pipeline tabs, theme).
  - [ ] L.4.8 — Drop PR's filter group + visual ID aggregate constants.
  - [ ] L.4.9 — Update e2e structural tests for PR.
  - [ ] L.4.10 — While the recon filters are restructured, investigate the 5 hanging PR FilterControl dropdown e2e tests (Test Reliability backlog item below). If the structural pattern naturally refactors away under the tree, fix as part of the port; otherwise leave in backlog.
  - [ ] L.4.11 — Diff JSON before/after; document any non-byte-identical diffs.
  - [ ] L.4.12 — Run full unit + e2e suites; fix regressions.

- [ ] **L.5 — Layer separation: default vs demo overlay.** With all three apps ported, audit the L1 + L2 surface for persona leaks. Acceptance: `quicksight-gen generate --all` against a non-demo config produces a fully-rendering generic dashboard with zero Sasquatch references; `demo apply --all` continues to produce the Sasquatch-flavored output it does today.
  - [ ] L.5.1 — `grep -ri "sasquatch\|snb\|bigfoot\|juniper\|cascadia\|farmers exchange" src/quicksight_gen/common/ src/quicksight_gen/apps/{payment_recon,account_recon,investigation}/{analysis,filters,visuals,datasets,etl_examples,constants}.py` — every match is a leak that must move to L3.
  - [ ] L.5.2 — Categorize each leak: persona-specific copy (move to L3 overlay), generic copy that happens to mention SNB (rephrase generically), or structural (refactor).
  - [ ] L.5.3 — Define the L3 overlay API surface. Two candidate shapes:
    - (a) **Wrapper:** `DemoOverlay(theme="sasquatch-bank-investigation", getting_started_extras={...}, demo_seed=sasquatch_inv_demo_data).apply_to(default_inv_app)` — overlay returns a new tree with persona copy + theme injected.
    - (b) **Composition:** the L2 `build_investigation_app()` returns the bare tree; `build_investigation_demo_app()` in a separate module composes overlay on top.
    - Pick by which keeps `apps/{pr,ar,inv}/` files most persona-free.
  - [ ] L.5.4 — Move Sasquatch-specific Getting Started rich-text copy from sheet builders into the L3 overlay (today the Investigation Getting Started mentions "Sasquatch National Bank shared base ledger" — that copy belongs to demo, not default).
  - [ ] L.5.5 — Make the demo theme preset explicit: default tree builds against `default` theme; demo overlay opts into `sasquatch-bank*`. Update CLI default-vs-demo behavior to match.
  - [ ] L.5.6 — Wire the existing `demo_data.py` files into the L3 overlay layer (no changes to the demo SQL itself — just where it attaches).
  - [ ] L.5.7 — Verify generic-mode rendering: a fresh `generate --all` against a non-demo config produces zero Sasquatch references in any emitted JSON (script the check).
  - [ ] L.5.8 — Verify demo-mode rendering: `demo apply --all` produces output byte-identical to pre-L.5 (modulo any documented diffs from L.2-L.4).
  - [ ] L.5.9 — Document the three-layer model in `CLAUDE.md` under Architecture Decisions. Include the "Sasquatch lives only in L3" rule with a code example.

- [ ] **L.6 — Executives app on the new tree from scratch.** Greenfield use of the tree pattern as the proving ground that the API works for first-time authors, not just for porting existing apps. **Second iteration gate** — friction here calls back into L.1. Per Training_Story.md: counts across the data, transactions over time, money moved per type. Acceptance: 4th app deploys alongside the other 3; full unit + e2e suites green; the L.6 author writes ~no `constants.py` (the tree carries the IDs).
  - [ ] L.6.1 — Design pass: name the sheets, list visuals per sheet, identify dataset queries needed. Likely 3–4 sheets — Getting Started + Account Coverage (counts per ledger / sub-ledger / customer / merchant) + Transaction Volume Over Time (line charts per `transfer_type`) + Money Moved (totals per rail / per type, period-over-period).
  - [ ] L.6.2 — New `apps/executives/` package skeleton. Constants module probably empty (the tree carries IDs); `datasets.py` holds dataset SQL + `DatasetContract`s.
  - [ ] L.6.3 — Build dataset SQL — account counts, transaction volumes, money totals. Reads existing `transactions` + `daily_balances` + AR dimension tables; matview only if a query chokes Direct Query.
  - [ ] L.6.4 — Build Getting Started + Account Coverage sheet end-to-end against the tree.
  - [ ] L.6.5 — Build Transaction Volume Over Time sheet.
  - [ ] L.6.6 — Build Money Moved sheet.
  - [ ] L.6.7 — Wire cross-app drills: any "show me the rows" on a metric drills into AR Transactions filtered to the relevant `account_id` / `transfer_type` / date range.
  - [ ] L.6.8 — Theme: probably new preset `sasquatch-bank-executives` (slate / navy with executive-report seriousness) — or reuse default + Sasquatch overlay if the slate fits.
  - [ ] L.6.9 — Unit tests: dataset contract checks, visual builders, sheet wiring, drill shape validation. Mirror the `test_investigation.py` shape.
  - [ ] L.6.10 — Wire into CLI: `executives` is a valid app key for `generate` / `deploy` / `demo apply / seed`; `--all` includes it. Update `cli.py`.
  - [ ] L.6.11 — Demo seed: probably none — executives reads the shape the other apps already plant. Confirm the Account Coverage / Volume / Money visuals have non-empty data with the existing PR + AR + Investigation seeds.
  - [ ] L.6.12 — **Iteration gate** — review the L.1 friction surfaced during greenfield. List items as L.1 follow-up; circle back to L.1 before L.7 if the friction is structural.

- [ ] **L.7 — Browser e2e for Executives.** Mirror the K.4.9 / AR e2e shape. Acceptance: ~20–25 new tests collected; full e2e suite green.
  - [ ] L.7.1 — Add `exec_dashboard_id`, `exec_analysis_id`, `exec_dataset_ids` session-scoped fixtures to `tests/e2e/conftest.py`.
  - [ ] L.7.2 — `test_exec_deployed_resources.py` (dashboard / analysis / dataset existence).
  - [ ] L.7.3 — `test_exec_dashboard_structure.py` (sheet count, per-sheet visual counts, parameter set, filter group set — walking the tree's emitted set).
  - [ ] L.7.4 — `test_exec_dashboard_renders.py` (embed URL + tab smoke).
  - [ ] L.7.5 — `test_exec_sheet_visuals.py` (parametrized per-sheet visual counts + spot-checked titles).
  - [ ] L.7.6 — `test_exec_filters.py` if there are any (sheet-level period selectors, etc.).
  - [ ] L.7.7 — `test_exec_drilldown.py` if cross-app drills land — verify the click navigates / sets the destination param.
  - [ ] L.7.8 — Run full e2e suite; fix regressions.

- [ ] **L.8 — Executives handbook + walkthroughs.** New `docs/handbook/executives.md` + walkthroughs per sheet's core question. Acceptance: `mkdocs build --strict` clean.
  - [ ] L.8.1 — Read the L.6 sheet shape; draft the question per sheet that becomes a walkthrough title.
  - [ ] L.8.2 — Draft `docs/handbook/executives.md` overview. Frame the executives team as a fourth persona — exec / board reporting cadence, scan-for-trends posture, drill into the operational sheets when something looks off.
  - [ ] L.8.3 — Draft 3–4 walkthroughs in `docs/walkthroughs/executives/*.md` (one per sheet's question). Mirror the established Story → Question → Where to look → What you'll see in the demo → What it means → Drilling in → Next step → Related shape.
  - [ ] L.8.4 — Update `mkdocs.yml` nav: add Executives Handbook block after Investigation.
  - [ ] L.8.5 — Update `docs/index.md` to count four apps; surface the Executives handbook in the Operator handbooks section.
  - [ ] L.8.6 — Verify `mkdocs build --strict` clean.

- [ ] **L.9 — Docs sweep + Python API doc generation.** New "Tree pattern" section in `CLAUDE.md` under Architecture Decisions covering L1 → L2 → L3 layering and the "Sasquatch lives only in L3" rule. README updates to count four apps and replace the constants-driven framing with the tree-driven one. New customization handbook walkthrough using the L.6 work as the worked example. **Plus mkdocstrings-driven Python API reference** (the `common/` tree is now meaty enough to need it). Acceptance: `mkdocs build --strict` clean; `pytest` green; all docs accurate against the post-L codebase; API reference rendered for every public class in `common/`.
  - [ ] L.9.1 — Add new "Tree pattern" section to `CLAUDE.md` under Architecture Decisions covering the three-layer model, the persona-blind primitives rule, and the "tree IS the source of truth" rule.
  - [ ] L.9.2 — Update `CLAUDE.md` project-structure tree to add `common/tree.py` (or `common/tree/` package) and any new sub-modules.
  - [ ] L.9.3 — Update `README.md` "ships three independent QuickSight apps" → four, including Executives.
  - [ ] L.9.4 — Add Executives table to README's "The four apps" section, mirroring the existing PR / AR / Investigation tables.
  - [ ] L.9.5 — Add Executives demo scenario block to README's Demo scenarios section.
  - [ ] L.9.6 — Add `sasquatch-bank-executives` to README + CLAUDE theme preset lists.
  - [ ] L.9.7 — Add Executives datasets to the README + CLAUDE `out/` tree listings.
  - [ ] L.9.8 — Drop the "Constant-heavy / builder pattern" bullets from PLAN.md's "Evolving the app" section (the work the section called for is now done).
  - [ ] L.9.9 — Add new customization handbook walkthrough: "How do I author a new app on the tree?" — L.6's work is the worked example; cross-link the API reference (L.9.10).
  - [ ] L.9.10 — **Wire mkdocstrings into the mkdocs build.** Recommended tool: `mkdocstrings[python]` — auto-generates API reference pages from type hints + docstrings, integrates with the existing mkdocs-material site, no separate doc build step. Sub-steps:
    - Add `mkdocstrings[python]` (and `mkdocs-gen-files` if we want literate-style page generation) to `pyproject.toml` dev extras.
    - Configure `mkdocs.yml`: add `mkdocstrings` to `plugins`; configure handlers for the `quicksight_gen` package.
    - Create `docs/api/index.md` + per-module pages (`docs/api/common-tree.md`, `docs/api/common-models.md`, `docs/api/common-drill.md`, `docs/api/common-dataset-contract.md`, etc.) — each page is a thin `::: quicksight_gen.common.tree` directive that renders the module's public API.
    - Add the API reference section to `mkdocs.yml` nav (probably as the last top-level item: "API Reference").
    - Verify `mkdocs build --strict` still passes — strict mode will flag broken docstring references and rendering errors. Configure mkdocstrings handler to **warn** (not error) on missing docstrings per locked decision; tighten to error in a follow-up sweep once L lands.
  - [ ] L.9.11 — Verify `mkdocs build --strict` clean with the new API reference pages.
  - [ ] L.9.12 — Run full unit suite green.

- [ ] **L.10 — Release as v5.0.0 (major).** Earned by: internal API change (external callers importing `quicksight_gen.apps.*.analysis` / `.filters` / `.visuals` for programmatic dashboard construction need to update — the new public surface is the `common/` tree); the new Executives app; the layer-separation cleanup. Per the project's no-backwards-compat-shims rule, no compatibility re-exports of the old per-app builder modules.
  - [ ] L.10.1 — Bump `__version__` from 4.0.0 → 5.0.0 in `src/quicksight_gen/__init__.py`.
  - [ ] L.10.2 — Write the v5.0.0 entry in `RELEASE_NOTES.md` covering: tree pattern + three-layer model, the apps porting (L.2–L.4), the layer-separation cleanup (L.5), the new Executives app (L.6 + L.7 + L.8), the new mkdocstrings API reference (L.9), and the migration path for external callers (old `apps/*/analysis.py` builder imports → new `common.tree` API).
  - [ ] L.10.3 — Tick L.0 – L.10 in PLAN.md (the file you're reading).
  - [ ] L.10.4 — Run `quicksight-gen --version` to confirm 5.0.0; run full unit suite green.
  - [ ] L.10.5 — Commit on the `phase-l-10-release-v5-0-0` branch.
  - [ ] L.10.6 — Merge to main (`--no-ff` per K convention).
  - [ ] L.10.7 — Tag `v5.0.0` annotated.
  - [ ] L.10.8 — Push main + tag.
  - [ ] L.10.9 — Verify the release pipeline (Phase I.6 release workflow) runs green: TestPyPI publish → manual approval gate → PyPI publish → GitHub Release with sdist + wheel + sample bundle.

**Sequencing.** L.0 first — the tree spike's only job is to validate that the L1 API can produce JSON the existing models accept; if it can't, redesign before any porting. L.1 lands the full primitives once the spike validates. Port apps L.2 → L.3 → L.4 in increasing complexity (Investigation smallest, AR largest) so each port stress-tests the API a little more than the previous one. L.5 (layer separation) lands after porting because we can't see the persona-specific surface clearly until all three apps are on the tree. L.6 (Executives greenfield) follows L.5 so it's built against the cleaned-up two-layer API. L.7–L.8 (e2e + handbook for Executives) mirror the K.4.9 → K.4.10 shape and stack at the end where everything they reference exists. L.9 sweeps the docs. L.10 publishes.

**Out of scope** (queued for Phase M or later):
- Whitelabel-V2 (relationship/flow modeling for demo data) — Phase M headline.
- Docs/training tree merge + template-rendered docs — bundled into Phase M with whitelabel-V2 as one initiative (the persona dataclass should drive both the seed generator AND the doc renderer in lockstep).
- CLI scope revisit — its role is changing as customization extends; revisit in M or later once the new tree + whitelabel layers settle.
- App Info tab, Audit Enhancements, Data Evaluation tooling, the 5 PR FilterControl dropdown e2e tests (unless L.4 incidentally fixes them) — stay in backlog.

# Phase M — Whitelabel-V2 + docs/training (preview)

Will be planned in detail when L lands. Headline: replace today's string-substitution whitelabel (one canonical Sasquatch copy + a `mapping.yaml` substitution at export time) with a relationship/flow-aware persona model — define what an institution looks like operationally (account topology, settlement cadences, customer mix, rail composition, scenario shapes) as a typed dataclass, then have a deterministic generator consume that model and emit both the seed SQL **and** the rendered handbook/training content in lockstep. The persona is the source of truth; every shipped artifact is rendered from it.

Bundles in three currently-queued items:
- Whitelabel-V2 (the relationship/flow modeling layer + generator)
- Docs/Training Tree Merge (deferred from K.4.1)
- Template-rendered docs (replaces string-substitution whitelabel)

CLI scope revisit likely lands here too — `quicksight-gen` grows from a generator/deployer into a customization platform, and `export training` / `export docs` / `whitelabel apply` may collapse or restructure. Decide at M kickoff.

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
