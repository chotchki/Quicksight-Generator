# Release Notes

## v5.0.1

### Phase L — Tree primitives + Executives app + mkdocstrings API reference (major)

> **v5.0.0 was cut but never published to prod PyPI.** The release pipeline reached the manual approval gate, at which point the underlying CI run on the same commit was discovered to be red — two e2e drilldown tests crashed at parametrize-collection time on a stock CI runner (no `config.yaml`, no `QS_GEN_*` env vars). The release was cancelled at the gate before `publish-pypi` ran. v5.0.1 ships the same Phase L work plus two release-pipeline reliability fixes that prevent the same situation from recurring. See "Release pipeline reliability" at the end of this entry. The v5.0.0 git tag was deleted; TestPyPI shows a v5.0.0 artifact (the pre-fix wheel) which will not be promoted.

Replaces the constants-heavy, manually-cross-referenced dashboard construction in the per-app `analysis.py` / `filters.py` / `visuals.py` modules with a tree of typed builder objects in `common/tree/`. Visuals reference `Dataset` nodes (not string identifiers); filter groups reference `Visual` nodes; cross-sheet drills reference `Sheet` nodes. Internal IDs (visual_id, filter_group_id, action_id, layout element IDs) auto-derive from tree position; URL-facing identifiers (`SheetId`, `ParameterName`) and analyst-facing identifiers (`Dataset` identifier, `CalcField` name) stay explicit. `App.emit_analysis()` / `emit_dashboard()` runs validation walks (dataset / calc-field / parameter / drill-destination references) — a missing reference fails at construction with a stack trace pointing at the wiring site, not at deploy with an opaque "InvalidParameterValue".

All three existing apps (Payment Reconciliation, Account Reconciliation, Investigation) ported to the tree, and a fourth app — **Executives**, board-cadence statistics over the shared base tables — built greenfield directly on the new primitives. Combined source reduction across the three ports: -47%.

The major bump is earned by:

- **Internal API change.** External callers importing `quicksight_gen.apps.{payment_recon,account_recon,investigation}.{analysis,filters,visuals}` for programmatic dashboard construction must update — those modules are gone, collapsed into a single `apps/<app>/app.py` per app. The new public construction surface is `quicksight_gen.common.tree` (App / Analysis / Dashboard / Sheet plus typed Visual / Filter / Control / Drill wrappers). Per the project's no-backwards-compat-shims rule, no compatibility re-exports.
- **New Executives app** added as the fourth dashboard.
- **Layer-separation cleanup.** The codebase is now structured around an explicit three-layer model: L1 (`common/tree/` — persona-blind primitives), L2 (`apps/<app>/app.py` — per-app tree assembly in domain vocabulary), L3 (SQL strings + `demo_data.py` + `common/persona.py` + theme presets — persona / customer flavor). The L1 invariant: zero `sasquatch` hits in `common/tree/`.

### What landed

**Typed tree primitives in `common/tree/` (L.1)**

- `App` / `Analysis` / `Dashboard` / `Sheet` are the top-level structural nodes; cross-references between them are object refs, not string IDs.
- Typed `Visual` subtypes: `KPI`, `Table`, `BarChart`, `Sankey`, plus `TextBox` for rich-text content. Each subtype validates its dataset / column references at emit time.
- Typed Filter wrappers: `CategoryFilter`, `NumericRangeFilter`, `TimeRangeFilter`, plus `FilterGroup` for sheet-wide / visual-pinned / all-sheets scoping.
- Typed Parameter declarations (`StringParameter` / `IntegerParameter` / `DecimalParameter` / `DatetimeParameter`) and matching Filter / Parameter `Control` wrappers (Dropdown, Slider, DateTimePicker, CrossSheet).
- Typed `Drill` actions with `Sheet` object-ref targets — the tree validates the destination at emit time so a typo'd drill target fails at construction, not at deploy.
- Typed `Dataset` + `Column` nodes; `ds["col"].dim()` / `.sum()` / `.date()` chained factories produce typed `Dim` / `Measure` slots that visuals consume directly. Column refs validate against the registered `DatasetContract` so column-name typos raise a loud `KeyError` at the wiring site.
- Typed analysis-level `CalcField`; auto-naming from tree position.
- Auto-ID resolver (L.1.16) for internal IDs; pyright strict on `common/tree/`; kitchen-sink app exercising every primitive shape (L.1.10.6).

**Apps ported to the tree (L.2 / L.3 / L.4)**

- L.2 — Investigation: 5 sheets, 5 datasets, walk-the-flow drills on the directional Sankeys, parameter-bound chain-root + anchor selection.
- L.3 — Account Reconciliation: 5 sheets, 13 datasets including the 3 cross-check rollups + 2 daily-statement datasets, per-tab filters, drill-down chain (Balances → Transactions, Transfers → Transactions, Today's Exceptions → per-check details).
- L.4 — Payment Reconciliation: 6 sheets, 11 datasets, mutual-filter Payment Reconciliation tab, cross-pipeline drills (Payments → Settlements → Sales).
- Combined source reduction across the three ports: -47%.

**Executives — fourth app, greenfield (L.6)**

- 4 sheets: Getting Started + Account Coverage + Transaction Volume Over Time + Money Moved.
- 2 custom-SQL datasets reading the shared base tables only — no Executives-specific schema. Per-transfer pre-aggregation (`WITH per_transfer AS`) collapses multi-leg transfers so a 2-leg $100 movement counts as one $100 transfer (not two $200) in the volume + money rollups.
- Account Coverage's Active KPI + Active bar carry a visual-pinned `activity_count >= 1` filter so they read as "accounts that moved money in the period" while the Open KPI/bar count every row — same dataset, different scope.
- The greenfield author wrote zero `constants.py` (sheet IDs inline in `app.py`, internal IDs auto-resolved per L.1.16) and used only the L.1 primitives — the validation that Phase L's API design is sound.

**Browser e2e for Executives (L.7)**

- 20 new tests across 4 modules in `tests/e2e/`. API + browser layers cover dashboard / analysis / 2-dataset existence, sheet structure (4 sheets with descriptions, per-sheet visual counts, the visual-pinned active-only filter scoping), embed URL, sheet-tab smoke, and per-sheet visual rendering via `TreeValidator(exec_app, page).validate_structure()`.
- The `test_exec_*.py` files derive expected sets from the tree (`exec_app.analysis.{sheets,parameters,filter_groups}`) instead of hand-listed dicts — the L.11 "tree IS the source of truth" pattern.
- Cleanup of three pre-existing structural-test debts surfaced during the run-the-suite step: two Investigation tests rewritten off legacy hardcoded `V_INV_*` VisualIds onto analyst-facing visual titles (then dropped the now-orphan V_INV_* exports from `apps/investigation/constants.py`); one PR test rewritten to derive from `pr_app.dataset_dependencies()` (was over-asserting via the fixture, which still listed the unreferenced `merchants-dataset`).

**Docs sweep + mkdocstrings-driven Python API reference (L.9)**

- New "Tree pattern" section in `CLAUDE.md` under Architecture Decisions covering the three-layer model (L1 / L2 / L3), the persona-blind primitives rule, and the "tree IS the source of truth" rule with three concrete tree-walking examples from the codebase.
- `CLAUDE.md` project-structure tree refreshed: `common/tree/` expanded as a package with all 13 sub-modules listed; per-app entries collapsed off the dropped `analysis.py` / `visuals.py` / `filters.py` shape into `app.py`-only; `common/{persona,drill,ids}.py` + `apps/executives/` added; tests + e2e listings refreshed.
- README updated for 4 apps throughout — new Executives table block in "The four apps" section, demo scenario block, deploy commands, project structure, customising section.
- mkdocstrings wired into the mkdocs build (`mkdocstrings[python]>=0.26` added to `docs` extras). 7 API reference pages under `src/quicksight_gen/docs/api/`: `index.md` (overview + three-layer model), `tree-structure.md`, `tree-visuals.md`, `tree-data.md`, `tree-filters-controls.md`, `tree-actions.md`, `common-foundations.md`.
- New customization handbook walkthrough: "How do I author a new app on the tree?" — L.6 Executives is the worked example. `mkdocs build --strict` clean.

**Release pipeline reliability**

- **Post-publish install verification (L.10.0).** Two new symmetric jobs in `.github/workflows/release.yml` — `verify-testpypi-install` (gates `publish-pypi`) and `verify-pypi-install` (gates `github-release`). Each polls `pip install quicksight-gen==<TAG>` from the relevant index with retries (CDN propagation lag), confirms `quicksight-gen --version`, and runs a smoke import of the public surface (`common.tree.{App,Sheet,visuals,filters,actions}` + each app's `build_<app>_app` entry point). Catches missing-package-data or stripped-import bugs the local-wheel `smoke` job can't see, and prevents a half-published-then-unfetchable package from getting a GitHub Release.
- **Release gated on tests passing (v5.0.1 follow-up).** Added a `tests` job at the start of `release.yml` that re-runs the same pytest+pyright matrix `ci.yml` runs (Python 3.12 + 3.13). `build` depends on `tests`, so any test failure stops the release before any publish step fires — preventing the v5.0.0 situation where TestPyPI publish ran despite CI being red on the same commit.
- **e2e drilldown collection-time crash (v5.0.1 fix).** `tests/e2e/test_drilldown.py` and `test_ar_drilldown.py` call helpers at module import time (pytest.mark.parametrize argument) that load `config.yaml`. On stock CI (no config, no `QS_GEN_*` env) the load raises `ValueError` *before* the `QS_GEN_E2E` gate in `conftest.py` has a chance to skip the test. Fix: catch the `ValueError` and return an empty parameter list — pytest then marks the test as "no parameters" and skips cleanly. On a configured dev box the full enumeration still runs.

### Migration path for external callers

For programmatic dashboard construction, replace per-app builder imports with the public tree API:

```python
# v4.x — gone
from quicksight_gen.apps.payment_recon.analysis import build_analysis
from quicksight_gen.apps.payment_recon.visuals import sales_overview_visual
from quicksight_gen.apps.payment_recon.filters import build_filter_group
from quicksight_gen.apps.payment_recon.constants import V_PR_SALES_KPI

# v5.0 — tree-based public API
from quicksight_gen.common.tree import App, Sheet
from quicksight_gen.common.tree.visuals import KPI, Table, BarChart, Sankey
from quicksight_gen.common.tree.filters import FilterGroup
from quicksight_gen.common.tree.actions import Drill
from quicksight_gen.apps.payment_recon.app import build_payment_recon_app
```

Read [`How do I author a new app on the tree?`](https://chotchki.github.io/Quicksight-Generator/walkthroughs/customization/how-do-i-author-a-new-app-on-the-tree/) for the worked-example narrative; the [API Reference](https://chotchki.github.io/Quicksight-Generator/api/) covers every public class.

The L.5 (default-vs-demo overlay) and L.8 (Executives handbook + walkthroughs) substeps were deferred to Phase M (Whitelabel-V2), where the persona-substitution surface gets unified across all four apps and the Executives copy lands in its final whitelabel-ready shape.

---

## v4.0.0

### Phase K.4 — Investigation app + `apps/` namespace re-org (major)

Adds a third independent QuickSight app — **Investigation**, the AML / compliance triage surface — alongside Payment Reconciliation and Account Reconciliation. Reads from the same shared `transactions` + `daily_balances` base tables (no schema change), backed by two new materialized views that pre-compute rolling-window pair statistics and recursive chain walks.

The major bump is earned by two breaking changes that ride along with the new app:

- The `payment_recon/` and `account_recon/` packages moved into a new `apps/` namespace (`quicksight_gen.apps.payment_recon` / `quicksight_gen.apps.account_recon`). Per the project's "no backward-compat shims" rule, no compatibility re-exports — external callers update their imports.
- The `quicksight_gen.training.distribute` and `quicksight_gen.training.publish` modules (superseded by `quicksight-gen export training` + `whitelabel.py` in v3.4.0 but never deleted) are gone. The `training/` tree is now pure content.

### What landed

**Re-org under `apps/` namespace + obsolete-script cleanup (K.4.1)**

- `src/quicksight_gen/payment_recon/` → `src/quicksight_gen/apps/payment_recon/`.
- `src/quicksight_gen/account_recon/` → `src/quicksight_gen/apps/account_recon/`.
- Every import across src + tests + scripts updated to `quicksight_gen.apps.{payment_recon,account_recon}`.
- `src/quicksight_gen/training/distribute.py` (handbook zipper — replaced by `export training`'s folder copy) and `src/quicksight_gen/training/publish.py` (string substitution — duplicated by `whitelabel.py`) deleted. `training/` is now pure content (handbook/, QUICKSTART.md, mapping.yaml.example).
- `src/quicksight_gen/docs/` (operator handbook, mkdocs source) and `src/quicksight_gen/training/` (audience-organized cross-training, whitelabel-able) stay separate trees with separate export paths. Merging the two is queued in Backlog under "Docs/Training Tree Merge"; today's split is the right call until K.4.x lands more targeted training examples.

**Investigation app skeleton + theme preset (K.4.2)**

- New `src/quicksight_gen/apps/investigation/` package mirroring `account_recon/`'s layout (`analysis.py`, `visuals.py`, `filters.py`, `datasets.py`, `demo_data.py`, `constants.py`, `etl_examples.py`).
- Wired into the CLI: `generate`, `deploy`, `demo apply` / `seed` / `etl-example` all accept `investigation` as a third app key; `--all` includes it.
- New `sasquatch-bank-investigation` theme preset (slate blue + amber alert palette).
- Five sheets: Getting Started + Recipient Fanout / Volume Anomalies / Money Trail / Account Network.

**Recipient Fanout sheet (K.4.3)**

- New `inv-recipient-fanout-dataset` (one row per (recipient leg, sender leg) pair sharing a `transfer_id`); recipient pool filtered to customer DDAs + merchant DDAs only so administrative sweeps don't dominate the ranking.
- Threshold filter is the analysis-level windowed calc field `recipient_distinct_sender_count = distinctCount({sender_account_id}, [{recipient_account_id}])`, gated by a `NumericRangeFilter` whose minimum is bound to a `pInvFanoutThreshold` integer parameter (slider 1–20, step 1, default 5).
- Three KPIs (qualifying recipients / distinct senders / total inbound) + recipient-grain ranked table sorted by distinct sender count desc.

**Volume Anomalies sheet (K.4.4)**

- New materialized view `inv_pair_rolling_anomalies` computes per-(sender, recipient) rolling 2-day SUM (`RANGE BETWEEN INTERVAL '1 day' PRECEDING AND CURRENT ROW` partitioned by sender+recipient) plus the population mean + sample standard deviation across all pair-windows; per-row z-score and 5-band z-bucket label projected at refresh time.
- σ threshold (`pInvAnomaliesSigma` integer parameter, default 2, slider 1–4 step 1) bound to a `NumericRangeFilter` on `z_score`, scoped `SELECTED_VISUALS` to KPI + table only — the distribution chart sees the full population so the cutoff lands in context.
- Visuals: KPI flagged-pair count + vertical bar chart (X = z_bucket, Y = COUNT) + table grouped to (sender, recipient, window_end) sorted by z_score desc.

**Money Trail sheet (K.4.5)**

- New materialized view `inv_money_trail_edges` walks `parent_transfer_id` chains via `WITH RECURSIVE`, flattened to one row per multi-leg edge with chain root, depth from root, source × target leg pair, and `source_display` / `target_display` strings (`name (id)`) for unambiguous dropdowns and tables.
- Visuals: native QuickSight Sankey as the headline + hop-by-hop detail table beside it. Filters: chain-root dropdown, max-hops slider, min-hop-amount slider.
- Single-leg PR transfers (`sale`, `external_txn`) appear in the table but don't draw Sankey ribbons — the matview projects multi-leg edges only.

**Investigation demo data + cross-app scenario coverage (K.4.6)**

- New `apps/investigation/demo_data.py` plants three converging scenarios on a single anchor account (Juniper Ridge LLC, `cust-900-0007-juniper-ridge-llc`):
  - Fanout cluster — 12 individual depositors × 2 ACH transfers each → Juniper.
  - Anomaly pair — Cascadia Trust Bank — Operations → Juniper, 8 baseline routine wires + 1 spike day ($25,000 wire vs ~$300–$700 baseline).
  - Money trail — 4-hop layering chain rooted on a Cascadia wire, fanning through Juniper into three shell DDAs (Shell A → B → C).
- Investigation registers its own internal ledger (`inv-customer-deposits-watch`) + two external ledgers so `demo seed investigation` is FK-safe standalone. Same Sasquatch National Bank persona — the Compliance / Investigation team is the third operational view of the same bank.
- `TestScenarioCoverage` assertions in `tests/test_investigation_demo_data.py`; per-app SHA256 seed hash locked.

**Cross-app drill plumbing — investigated, dropped (K.4.7)**

- Built `CustomActionURLOperation` model + `cross_app_drill()` URL-deep-link helper, wired three deferred Investigation → AR Transactions drills, proved the URL form `https://{region}.quicksight.aws.amazon.com/sn/dashboards/{id}/sheets/{sheet_id}#p.<param>=<<column>>` substitutes cleanly. Then **dropped the feature** — QuickSight doesn't sync sheet parameter controls to URL-set values: data filters correctly, but the on-screen control widgets continue to show "All". Same defect affects QS's own intra-product Navigation Action with parameters.
- Re-entry conditions documented in PLAN.md "QuickSight URL-parameter control sync — known platform limitation". The dropped K.4.7 code is recoverable from git history if a future static-link or non-parameterized URL feature wants it.

**Account Network sheet (K.4.8)**

- Second view over the K.4.5 matview, account-anchored instead of chain-rooted. Two side-by-side directional Sankeys (inbound on the left, outbound on the right, anchor visually meeting in the middle) + full-width touching-edges table below.
- Anchor parameter (`pInvANetworkAnchor`) backed by a small dedicated dataset wrapper (`inv-anetwork-accounts-ds`) that pre-deduplicates display strings, so the dropdown opens fast on a large matview.
- Walk-the-flow drill: right-click any table row → "Walk to other account on this edge" overwrites the anchor with the counterparty side; left-click any node in either directional Sankey performs the same walk (each directional Sankey has only one possible walk target). Per the K.4.7 control-sync defect, the dropdown widget may briefly lag behind a walk — sheet description tells analysts "trust the chart, not the control text".

**Browser e2e for Investigation (K.4.9)**

- 28 new tests across 6 modules in `tests/e2e/` mirroring AR's coverage shape, plus `inv_dashboard_id` / `inv_analysis_id` / `inv_dataset_ids` fixtures and matview warmups in the session-scoped Aurora pre-warm.
- API + browser layers cover: dashboard / analysis / 5-dataset existence, sheet structure (5 sheets with descriptions, per-sheet visual counts, K.4.8 directional-Sankey invariant — both inbound + outbound titles must surface), embed URL, sheet-tab smoke, and per-sheet visual rendering with TALL_VIEWPORT (1600×4000) for the Account Network's stacked layout.
- Three tests deferred for DOM follow-up (skipped with documented reasons): URL-hash parameter pre-seeding breaks dashboard loading, and the walk-the-flow drill needs a more reliable witness than touching-edges row count. The skipped surface is filter / drill propagation; the structural + render surface is fully covered.

**Investigation handbook + walkthroughs (K.4.10)**

- New `docs/handbook/investigation.md` plus four walkthroughs in `docs/walkthroughs/investigation/`, one per sheet's core question:
  - Who's getting money from too many senders? (Recipient Fanout)
  - Which sender → recipient pair just spiked? (Volume Anomalies)
  - Where did this transfer actually originate? (Money Trail)
  - What does this account's money network look like? (Account Network)
- Frames Investigation as **question-shaped** — pick the sheet whose question matches yours, no fixed reading order — vs. PR's pipeline-staged flow and AR's morning rotation.
- Every "Drilling in" section names the next sheet (intra-app) plus AR Transactions / PR pipeline tabs (cross-app at the row-evidence stage). `mkdocs.yml` nav extended with an Investigation Handbook block after PR; `docs/index.md` updated to count three apps.

### Conventions

- Investigation reads the shared base tables only — no investigation-specific schema, no app-specific dimension tables. Persona consistency: same Sasquatch National Bank, three operational views (Merchant Support / Treasury / Compliance).
- Sankey visuals use QuickSight's native `SankeyDiagramVisual` — feasibility validated in K.4.0's spike before any other K.4 code shipped.
- The two new matviews follow the same refresh contract as `ar_unified_exceptions`: declare `MATERIALIZED` in `schema.sql`, add `REFRESH MATERIALIZED VIEW <name>;` to the `demo apply` block in `cli.py`, document under [Materialized views](src/quicksight_gen/docs/Schema_v3.md#materialized-views) in Schema_v3.

### Migration

- **External callers importing `quicksight_gen.payment_recon.*` or `quicksight_gen.account_recon.*`**: update to `quicksight_gen.apps.payment_recon.*` and `quicksight_gen.apps.account_recon.*`. No compatibility re-exports — the old paths raise `ModuleNotFoundError`. Internal CLI / generate / deploy entry points are unchanged at the user-visible layer.
- **External callers importing `quicksight_gen.training.distribute` or `quicksight_gen.training.publish`**: both modules are deleted. Replacement is `quicksight-gen export training` (folder copy + whitelabel substitution in one step), which has been the supported path since v3.4.0.
- **ETL teams**: two new materialized views (`inv_pair_rolling_anomalies`, `inv_money_trail_edges`) join the existing `ar_unified_exceptions` under the same REFRESH contract. After every ETL load, run all three `REFRESH MATERIALIZED VIEW` statements — see [Materialized views](src/quicksight_gen/docs/Schema_v3.md#materialized-views) for the full contract. Skipping a refresh means anomaly z-scores and chain edges lag the source data; no data integrity loss, just stale operator-facing columns.
- **Deploy teams**: `quicksight-gen deploy` now manages a third dashboard (`qs-gen-investigation-dashboard`) + analysis + 5 Investigation datasets. `quicksight-gen cleanup` enumerates them under the same `ManagedBy:quicksight-gen` tag. `quicksight-gen demo apply --all` now seeds + refreshes Investigation alongside PR + AR.
- **Theme consumers**: a new `sasquatch-bank-investigation` preset is registered in `common/theme.py`. Existing PR (`sasquatch-bank`) + AR (`sasquatch-bank-ar`) presets unchanged.
- **No cross-app drill paths exist between Investigation and PR/AR.** K.4.7 dropped the URL-deep-link approach because QuickSight doesn't sync sheet parameter controls to URL-set values. Investigators leave the dashboard for AR Transactions / PR pipeline tabs by manually navigating; the Investigation handbook's "Drilling in" sections name the destination tab + filter explicitly to keep the path obvious.

---

## v3.8.0

### Phase K.3 — Lateness as a data column, not an operator threshold

Replaces the operator-applied "is this row past N days?" pattern with a per-leg `expected_complete_at` timestamp on `transactions` and a downstream `is_late` boolean predicate. PR's `late_default_days` config knob (and its slider) retire — the data answers, the slider only ever existed because the data didn't. AR gains an explicit Lateness picker on the Today's Exceptions and Trends sheets; the unified table surfaces `is_late` per row. Schema change is additive — the new column is NULLABLE with a `posted_at + INTERVAL '1 day'` COALESCE fallback, so existing ETL keeps working unchanged.

### What landed

**Schema + portability + ETL contract (K.3.0)**

- `transactions` gains `expected_complete_at TIMESTAMP NULL`. Not added to `daily_balances` — those are point-in-time snapshots; lateness is per-leg. The default formula `COALESCE(expected_complete_at, posted_at + INTERVAL '1 day')` is portable across the project's target RDBMS family (no JSONB, no Postgres-specific operators).
- New "Lateness as data" section in `docs/Schema_v3.md` documents the column as optional, the default formula, the `is_late` predicate SQL, and the multi-leg tie-breaker rule (the **earliest debit leg's** `expected_complete_at` becomes the transfer-level deadline).
- New "Optional: `expected_complete_at` (lateness)" section in `docs/handbook/etl.md` for the ETL team, with an "adopt one rail at a time" framing.

**Demo generators populate `expected_complete_at` per rail (K.3.1)**

- PR generator: card payments → T+3, external_txn rows → +1 hour (rail observations expected to settle almost immediately), sales / settlements / non-card payments → NULL (default applies).
- AR generator: instant rails (Fed wires, on-us internal) → same-day; ACH → T+2; non-rail-bound legs → NULL.
- Per-app SHA256 seed-hash assertions re-locked. New `TestExpectedCompleteAt` coverage classes pin the rail-specific values per generator.

**Datasets surface `is_late` + `expected_complete_at` (K.3.2)**

- `is_late STRING` (`"Late" / "On Time"` — labeled to match the codebase's `is_failed` / `is_returned` STRING convention so QS filter controls stay simple) and `expected_complete_at DATETIME` columns added to `ar_unified_exceptions` and the relevant per-check views, plus PR's exception + recon datasets. `DatasetContract` entries updated so the contract test catches projection drift.
- The `is_late` predicate is `CURRENT_TIMESTAMP > COALESCE(expected_complete_at, posted_at + INTERVAL '1 day')`. PR's recon dataset now derives `match_status` from the same predicate (`'matched'` / `'late'` / `'not_yet_matched'`) instead of the operator-threshold `(CURRENT_DATE - posted_at::date) > late_default_days` it used through K.2a.
- Shared `_lateness_columns()` helper in `payment_recon/datasets.py` keeps the SQL fragment in one place across the 6 PR datasets that surface lateness.

**KPIs / filters / visuals consume `is_late` (K.3.3)**

- AR Today's Exceptions + Trends sheets gain a Lateness picker (new `fg-ar-todays-exc-is-late` filter group + cross-sheet controls on both sheets). The unified Open Exceptions table surfaces `is_late` between `aging_bucket` and `account_id`.
- PR Late Transactions KPI subtitle updated to "Unmatched transactions past their expected completion time (per-row `is_late = 'Late'`)". The visual-pinned `match_status='late'` filter stays — it's the unmatched-AND-late semantic, which is the more actionable ops view than `is_late='Late'` alone (matched-but-late rows already resolved).
- `cfg.late_default_days` field + `QS_GEN_LATE_DEFAULT_DAYS` env var fully retired across `Config`, `README.md`, `docs/walkthroughs/customization/how-do-i-configure-the-deploy.md`, `CLAUDE.md`, and `SPEC.md`. Per the project's "no backward-compat shims" rule, no fallback / no flag — the deprecated knob is just gone.

**Handbook + walkthrough updates (K.3.4)**

- PR walkthrough `why-is-this-external-transaction-unmatched` rewritten to drop the hardcoded 30-day matching-window framing. Demo-data and "what it means" sections now reflect that with the rail-hour deadline (`expected_complete_at = posted_at + 1 hour` for external_txn), almost every unmatched external row is `match_status = 'late'`; orphan-recent vs orphan-late are reframed as aging buckets (urgency tiers) rather than match_status tiers.
- Customization handbook gains an "Optional ETL extensions" section introducing `expected_complete_at` (with the +1-day fallback) alongside the existing `metadata` extension, linking out to the schema's "Lateness as data" + the ETL handbook.
- AR + PR handbook Reference lists add Lateness-as-data cross-links to `Schema_v3.md`, with one-sentence framing for each app.

### Conventions

- Same theme as K.2 / K.2a: invariants encoded in the data shape itself rather than an operator-applied threshold. K.2 caught wrong-shape source-field bindings at the wiring line; K.2a caught wrong-kind-of-identifier mis-bindings at the same line; K.3 removes a whole class of "did the operator pick the right N?" inconsistency by moving the threshold into the row.
- The `is_late` column is STRING (`"Late" / "On Time"`), not BOOLEAN — matches the existing `is_failed` / `is_returned` STRING convention so QuickSight `CategoryFilter` controls stay uniform across the codebase.

### Migration

- **ETL teams**: `expected_complete_at` is fully optional. Every existing feed keeps working — when the column is NULL, the COALESCE fallback uses `posted_at + INTERVAL '1 day'`, which matches the conservative-default `is_late` semantic. Adopt rail-by-rail when convenient (the ETL handbook section recommends starting with whichever rail your team gets the most "is this really late or just slow?" questions about).
- **Dataset SQL consumers**: 6 PR datasets and `ar_unified_exceptions` gained `is_late` + `expected_complete_at` columns. Downstream consumers parsing `DatasetContract` will see new entries; existing column reads are unchanged.
- **`late_default_days` users**: the field is removed from `Config`. If you set it in `config.yaml` or via `QS_GEN_LATE_DEFAULT_DAYS`, that key is now ignored (and YAML loaders will not raise — it's just a silent no-op key). The slider on the PR Payment Reconciliation tab is gone; lateness comes from the data.

---

## v3.7.0

### Phase K.2a — Identifier scatter cleanup (typed constants for opaque IDs)

K.2 closed a class of cross-sheet drill bugs by encoding source-field / parameter shapes in the type system. K.2a applies the same approach to the rest of the identifier surface — filter group IDs, visual IDs, parameter names, demo-persona whitelabel strings, and the AWS enum-like fields (`ElementType`, `CrossDataset`, `Status`, `Scope`, `Trigger`). Before K.2a, these all appeared as bare string literals scattered across 12+ files each, with test fixtures hand-maintained against the literals from production code. A typo or rename in one place silently broke the binding without raising at deploy. After K.2a, every kind of identifier has a typed constant; mypy / pyright catches the wrong-kind-of-string at the call site instead of leaving it for a deploy-time visual mis-scope.

No analysis, dataset, schema, or runtime behavior change — type-system-only refactor.

### What landed

**Filter group ID constants (K.2a.1)**

- All 118 `fg-ar-*` / `fg-pr-*` literals promoted to `FG_*` module-level constants in `account_recon/constants.py` + `payment_recon/constants.py`. e2e existence tests now import `ALL_FG_AR_IDS` / `ALL_FG_PR_IDS` frozensets from the constants module instead of hand-maintaining `EXPECTED_IDS` against the production literals — adding a new filter group can no longer silently de-sync the test fixture.

**PR drill parameter constants (K.2a.2)**

- Added `P_PR_SETTLEMENT` / `P_PR_PAYMENT` / `P_PR_EXTERNAL_TXN` to `payment_recon/constants.py` mirroring AR's `P_AR_*`. Replaces ~75 plain-string occurrences of `pSettlementId` / `pPaymentId` / `pExternalTransactionId` across `payment_recon/analysis.py` + `recon_visuals.py` + tests.

**Visual ID constants (K.2a.3)**

- Largest mechanical sweep: all 314 visual ID literals are now `V_*` constants. `visuals.py` defines visuals via the constants; `analysis.py` `FilterGroup` scopes reference via the constants; e2e existence checks reference via the constants. Catches the K.2a-shaped silent bug — visual IDs flow into `SheetVisualScopingConfigurations.VisualIds`, where a typo silently widens scope (no error, just a filter that fails to apply to the expected visual).

**`NewType` wrappers in `common/ids.py` (K.2a.4)**

- New `common/ids.py` defines `SheetId`, `VisualId`, `FilterGroupId`, `ParameterName` as `NewType("...", str)`. The `*_ID` constants in both apps' `constants.py` are declared as the corresponding NewType, and function signatures across `analysis.py` / `filters.py` annotate accordingly. Same shape K.2 used for `ColumnShape` — wrong-kind-of-string fails at the call site, not in a deploy-time scope assertion.

**`DemoPersona` dataclass + auto-derived `mapping.yaml.example` (K.2a.5)**

- New `common/persona.py` introduces `DemoPersona` (a frozen dataclass with `institution`, `stakeholders`, `gl_accounts`, `account_labels`, `merchants`, `flavor`, `intentional_non_mappings` tuples) and a `SNB_PERSONA` instance — the single source of truth for whitelabel-substitutable strings ("Sasquatch National Bank", "Federal Reserve Bank", the `gl-1010` family, "Margaret Hollowcreek", etc.).
- `training/mapping.yaml.example` is now auto-derived via `derive_mapping_yaml_text(persona)`. A new `tests/test_persona.py::test_shipped_yaml_matches_derived` parity test fails loudly (printing the regenerated body) when the dataclass and the shipped YAML diverge — so a merchant rename in `demo_data.py` can no longer silently de-sync the publish-time substitution template. Connects to the post-K re-skinnable demo plan: the same `DemoPersona` instance the demo generators consumed at hash-lock time is what the substitution layer rewrites for the publish target, *after* the SHA256 seed-hash check.
- The follow-up of refactoring both `demo_data.py` modules to consume `DemoPersona` at every literal site is incremental and deferred — the SHA256 hash assertions need to stay green and that's a careful per-call refactor. The dataclass alone serves as source of truth for *what's substitutable*.

**AWS enum-like strings → `Literal` + class constants (K.2a.5b)**

- `ElementType`, `CrossDataset`, `Status`, `Scope`, `Trigger` were typed as bare `str` on the bearing dataclasses (`GridLayoutElement`, `FreeFormLayoutElement`, `FilterGroup`, `SheetVisualScopingConfiguration`, `VisualCustomAction`). A typo like `ElementType="VISULA"` survived to deploy time. The annotations are now `Literal[...]` so a typo fails under static analysis, and each bearing class now exposes `ClassVar` constants (`GridLayoutElement.VISUAL`, `FilterGroup.SINGLE_DATASET`, `SheetVisualScopingConfiguration.ALL_VISUALS`, `VisualCustomAction.DATA_POINT_CLICK` / `.ENABLED`) so call sites are IDE-discoverable.
- Swept all ~75 internal call sites to use the constants. Runtime is unchanged (Literal is a type-checker construct; ClassVar values resolve to the same string).

### Conventions

- Same theme as K.2: invariants encoded in the type system rather than in post-hoc validation tests. K.2 caught a wrong-shape source-field binding at the wiring line; K.2a catches a wrong-kind-of-identifier (visual ID where a sheet ID was expected) at the same line. The `DemoPersona` parity test is the one exception — encoded as a test rather than a type because the YAML is a serialized projection and "byte-equal" is the actual invariant; the test prints the regenerated body so the fix is paste-ready.

### Migration

- No migration needed for end users. The new constants module + `DemoPersona` dataclass are additive; no existing call site signature changed at runtime. Downstream consumers that import from the per-app `constants.py` modules will see new exported names but no removals.

---

## v3.6.1

### Docs — `ar_unified_exceptions` matview refresh contract

Re-cut of v3.6.0 with the operator-facing matview refresh contract written down. v3.6.0 shipped the conversion of `ar_unified_exceptions` to a `MATERIALIZED VIEW` (so the Today's Exceptions sheet renders under QuickSight Direct Query) and wired the refresh into `quicksight-gen demo apply` — but `docs/Schema_v3.md` did not mention the matview, so production ETL teams had no canonical reference for the refresh requirement. v3.6.1 adds it.

- **New "Materialized views" section in `docs/Schema_v3.md`** — sits between *Computed views catalogue* and *ETL examples*. Lists `ar_unified_exceptions`, the `REFRESH MATERIALIZED VIEW` requirement after each ETL load, the timing semantics for `days_outstanding` / `aging_bucket` (computed at refresh time, not query time — skipping a refresh lags the analyst-facing aging), and a "when to materialize" rule for future check views that cross the same read-cost threshold.
- **`docs/handbook/etl.md` cross-link** — *The contract* section now mentions the matview + REFRESH requirement and links to the Schema_v3 section. ETL team members reading the contract overview now see the requirement before they design their pipeline.

No code changes. No analysis, dataset, schema, or runtime behavior changes — `demo apply` was already running the REFRESH; this release just documents it for non-demo operators.

---

## v3.6.0

### Phase K.2 — Cross-sheet navigation parameter hygiene

This release closes a class of cross-sheet drill bugs where a destination sheet would silently render zero rows. Two underlying causes: (1) parameter-bound `CategoryFilter`s match the literal empty string when a parameter is at its sentinel default, suppressing every row; (2) drill source-field shapes coerced through `SINGLE_VALUED` string parameters could end up textually incompatible with the destination column they were meant to filter. K.2 makes both classes unrepresentable at the wiring site.

### What landed

**Calc-field PASS drill shape (K.2.1)**

- All six AR cross-sheet drill `FilterGroup`s switched from parameter-bound `CategoryFilter`s to a calc-field PASS shape: a per-drill calculated field returns `'PASS'` when the parameter is at its `__ALL__` sentinel OR when the row's column matches the parameter, and the filter retains only `'PASS'` rows. Removes the empty-string-match suppression that had every drill destination silently rendering zero rows when invoked from a non-defaulted source.
- `_DRILL_SPECS` becomes the single source of truth driving both the calc-field declarations and the matching `FilterGroup`s. `_drill_param_declaration()` raises if a name isn't in the derived sentinel-default set, so an incompatible declaration can't be silently constructed.

**Typed cross-sheet drill helpers (K.2.2)**

- New `common/drill.py` introduces `ColumnShape` (DATE_YYYY_MM_DD_TEXT, DATETIME_DAY, ACCOUNT_ID, SUBLEDGER_ACCOUNT_ID, LEDGER_ACCOUNT_ID, TRANSFER_ID, TRANSFER_TYPE), `DrillParam` (param + expected shape), `DrillSourceField` (source field + actual shape), and `cross_sheet_drill()` which refuses construction when the source-field shape can't assign to the destination param's expected shape. `SUBLEDGER_ACCOUNT_ID` and `LEDGER_ACCOUNT_ID` widen to `ACCOUNT_ID`; date encodings explicitly do not widen — that's the K.2 bug class (DATETIME silently coerced to a timestamp text that never matched a `TO_CHAR`'d YYYY-MM-DD column). The check fires at the wiring line, not in a downstream output-walking test.
- `build_dataset()` now takes a `visual_identifier` and registers each contract in a module-level registry, letting `field_source(visual_identifier, column_name)` resolve column shapes from the contract instead of duplicating shape annotations at every call site. Both `payment_recon/datasets.py` and `account_recon/datasets.py` register their full contract sets at import time so the registry is populated regardless of construction order.

**Drill-site migration + stale-param hygiene (K.2.3)**

- All 7 PR drill sites and all 6 AR drill sites migrated to `cross_sheet_drill()`. The 4 AR drills targeting the Transactions sheet flow through a new `_ar_drill_to_transactions()` helper that auto-resets every PASS-filtered param the caller doesn't explicitly write — closes a stale-param leak where a prior drill's value would silently narrow Transactions to zero rows. A `tests/test_account_recon.py::TestTransactionsDrillStaleParamHygiene` guard pins the helper's auto-reset set to `analysis._DRILL_SPECS` so a new drill spec can't bypass it.
- New `pArAccountId` parameter + `fg-ar-drill-account-on-txn` filter group added on the Transactions sheet for the K.1 Today's Exceptions account-day right-click drill (the K.1 spike landed these but the e2e dashboard-structure fixtures were never updated; synced here).
- New `tests/e2e/test_ar_cross_sheet_param_hygiene.py` (297 LoC) covers the full param-reset + PASS-filter behavior end-to-end against the deployed dashboard.

**Schema + Today's Exceptions drill bug fix**

- `ar_unified_exceptions` becomes a **MATERIALIZED VIEW** in `schema.sql`. The 14-block `UNION ALL` was too heavy for QuickSight Direct Query and the Today's Exceptions sheet wouldn't render. Operators must `REFRESH MATERIALIZED VIEW ar_unified_exceptions` after each ETL load; `demo apply` does this automatically.
- The Today's Exceptions account-day drill bound `exception_date` (DATETIME) to `pArActivityDate` (SINGLE_VALUED string), which QuickSight coerced to `"2026-04-07 00:00:00.000"`. The destination's `posted_date` filter compared that against `TO_CHAR(..., 'YYYY-MM-DD')` strings — never matched. Added an `exception_date_str` column to the unified exceptions projection (`DATE_YYYY_MM_DD_TEXT`) and switched the drill `SourceField` `FieldId` to bind that column instead. The K.2.2 type system would have caught this wiring at construction time.

**Conventions**

- `CLAUDE.md` gains a Conventions rule: **encode invariants in the type system, not in validation tests.** Typed wrappers + `__post_init__` validation + typed constructors that fail at the buggy line are preferred over post-hoc tests that walk generated output.

### Known issues

- 5 PR `FilterControl` dropdown e2e tests (`test_cashier_multi_select_narrows_sales`, `test_payment_method_narrows_payments`, three `test_show_only_toggle_narrows_and_clears` parametrize cases) time out in `_open_control_dropdown`. Pre-existing — failing on `v3.5.2` and on every K.2 commit, both serial and `--parallel 4`. Not a K.2 regression. Logged under `PLAN.md` Phase L Backlog > Test Reliability with the failing test ids, the broken selector, and a diagnostic path. Net e2e: 156 / 161.

---

## v3.5.2

### Release pipeline — SLSA build provenance + Node 24 actions

Supply-chain hardening for the release workflow. No analysis, dataset, or handbook changes.

- **SLSA build provenance attestations.** The release workflow's build job now runs `actions/attest-build-provenance@v4` against every artifact in `dist/`. Each release tag publishes a signed Sigstore attestation tying the wheel + sdist back to the exact commit, workflow run, and runner identity that produced them; visible at <https://github.com/chotchki/Quicksight-Generator/attestations>. Build job grants `id-token: write` + `attestations: write`; rest of the workflow keeps `contents: read` default.
- **All `actions/*` steps moved to latest majors** — `checkout` v4→v6, `setup-python` v5→v6, `upload-artifact` v4→v7, `download-artifact` v4→v8, `upload-pages-artifact` v3→v5, `deploy-pages` v4→v5. Clears the Node.js 20 deprecation warning ahead of the September 2026 runner removal. `softprops/action-gh-release` also bumped v2→v3.

---

## v3.5.1

### CI fix — boto3 in dev extras + workflow permissions

Re-cut of v3.5.0 (rejected at the PyPI approval gate) with two follow-up fixes that landed against `main` after the v3.5.0 tag was pushed.

- **`boto3>=1.34` added to `[project.optional-dependencies] dev`** in `pyproject.toml`. `tests/test_deploy.py` imports `quicksight_gen.common.deploy`, which has a module-level `import boto3`; the dev install previously only pulled `boto3-stubs` (type stubs, not the runtime package), so `pip install -e ".[dev]" && pytest` failed at collection time on a clean machine. Local `.venv` had boto3 from past `deploy` runs and masked the gap; CI on the v3.5.0 commit caught it.
- **Workflow-level `permissions: contents: read`** added to `.github/workflows/ci.yml` and `.github/workflows/release.yml` to satisfy CodeQL `actions/missing-workflow-permissions` findings (alerts #1–4). Per-job overrides on `coverage-badge` (`contents: write`), `publish-testpypi` / `publish-pypi` (`id-token: write`), and `github-release` (`contents: write`) are unchanged — they replace the workflow default for jobs that need elevated access.

No analysis, dataset, or handbook changes.

---

## v3.5.0

### Phase K.1 — AR Exceptions split + handbook rewrite + MIT relicense

This release rolls up Phase K.1 (the AR Exceptions density refactor and full AR Handbook rewrite) and a project-level relicense from the Unlicense to the MIT License. Dashboards: the AR Exceptions tab is gone, replaced by **Today's Exceptions** (unified-table operational view) and **Exceptions Trends** (rollups + aging matrix + per-check daily trend). Handbook: every per-check walkthrough rewrites against the new sheets. License: MIT replaces the Unlicense for clearer downstream usability.

### What landed

**AR Exceptions workflow split (K.1.0 – K.1.5)**

- **`ar_unified_exceptions` dataset** — UNION ALL across 14 per-check views with a `check_type` discriminator, severity-coloured tagging (`drift` / `overdraft` → red, `expected-zero` → orange, `limit-breach` → amber, others → yellow), and harmonized columns (`account_id`, `account_name`, `account_type`, `posted_at`, `balance_date`, `days_outstanding`, `aging_bucket`, `primary_amount`, `secondary_amount`). Wide+NULL projection — every check's specific column is first-class, NULL-filled where not applicable. Locked by `DatasetContract`.
- **Today's Exceptions sheet** — replaces the per-check KPI/table/aging blocks with one severity-coloured KPI strip + Check Type / Account / Aging / Transfer Type / Origin sheet controls + one *Open Exceptions* unified table sorted by severity then aging. Drill: right-click `account_id` → "View Transactions for Account-Day"; left-click `transfer_id` → Transactions sheet scoped to that transfer.
- **Exceptions Trends sheet** — new sheet hosting the 3 cross-check rollups (Balance Drift Timelines, Two-Sided Post Mismatch, Expected-Zero EOD), an aging matrix (5 buckets × 14 check types), and per-check daily trend lines.
- **Drill-scoping fix** — new `pArAccountId` parameter + `account_id`-bound filter group on the Transactions sheet; the unified Open Exceptions table writes both `pArAccountId` and `pArActivityDate` on right-click. Two system-aggregate checks (Concentration Master Sweep Drift, GL vs Fed Master Drift) carry neither `account_id` nor `transfer_id` and are intentionally un-drillable; reader cross-checks via the per-transfer companion check.
- **E2E coverage** — new parametrized `tests/e2e/test_ar_todays_exc_drill.py` over the 12 covered check_types (filter unified table to that check_type, dispatch matching click idiom, assert post-drill Transactions row count strictly less than baseline). Two new browser helpers (`right_click_first_row_of_visual`, `click_context_menu_item`) carry the right-click + menu-pick pattern.
- **Aurora warm-up + retry** — autouse session fixture issues `SELECT 1` + `COUNT(*)` against base tables; `_retry_on_playwright_timeout` wrapper survives one cold-start window for `wait_for_visual_titles_present` / `wait_for_visuals_present`.
- **Per-app dataset scoping in deploy** — `quicksight-gen deploy account-recon` (or `payment-recon`) no longer recreates the other app's datasets. `_dataset_ids_for_apps()` derives per-app DataSetIds from each loaded analysis's `Definition.DataSetIdentifierDeclarations`; deletes/creates skip files whose ID isn't in the allowed set. Guard test `tests/test_deploy.py::TestDatasetIdsForApps`.

**AR Handbook rewrite (K.1.6)**

- **17 walkthroughs rewritten** against the new sheets — 14 per-check (sub-ledger drift, ledger drift, non-zero transfers, sub-ledger limit breach, sub-ledger overdraft, sweep target non-zero EOD, concentration master sweep drift, ACH origination settlement non-zero EOD, ACH sweep without Fed confirmation, Fed activity without internal catch-up, GL vs Fed master drift, stuck in internal transfer suspense, internal transfer suspense non-zero EOD, internal reversal uncredited) + 3 rollups (balance drift timelines, two-sided post mismatch, expected-zero EOD). Each per-check walkthrough opens with a column-mapping table for the unified schema and routes drill instructions through the actual cell hints (pale-green `account_id` tint = right-click cue; accent-coloured `transfer_id` text = left-click cue). Three checks (Fed Activity Without Internal Catch-Up, Internal Transfer Stuck in Suspense, Internal Reversal Uncredited) had handbook-card titles that diverged from the dataset literal an operator sets as a Check Type filter; walkthroughs use the dataset literal so reader filter setting matches the screenshot.
- **22 fresh screenshots** captured — 3 shared Today's Exceptions (overview / breakdown bar / unified table) + 5 Trends (drift timelines / two-sided rollup / expected-zero rollup / aging matrix / per-check daily trend) + 14 per-check filtered Open Exceptions tables. Capture script (`scripts/generate_walkthrough_screenshots.py`) extended with `mode="full_sheet"` (clip from y=0 to lowest visual on the active sheet) and `_set_check_type_filter` (handles MUI listbox virtualization + prefix-collision-safe `^…$`-anchored regex deselection).
- **Handbook + training prose updated** — `handbook/ar.md` morning routine rewritten as a three-paragraph flow naming the two new sheets and the unified table; `Training_Story.md` GL Recon persona description updated to reference the new sheets.
- **mkdocs nav switched to horizontal tabs** — `navigation.tabs` added to Material features. The five handbooks (AR / PR / Data Integration / Customization / Training) render as tabs at the top of the page; left sidebar shrinks to the current handbook's entries (17 max for AR vs ~50 across all handbooks before). Fixed one nav label drift: "Fed Activity Without Internal Post" → "Fed Activity Without Internal Catch-Up" (matches dataset literal and walkthrough H1).
- **40 orphan PNGs deleted** — old per-check `<check>-01-kpi.png` / `<check>-02-table.png` / `<check>-03-aging.png` family removed from `src/quicksight_gen/docs/walkthroughs/screenshots/ar/` after the unified-table template made them obsolete.

**Relicense (K.1.7)**

- **MIT License replaces the Unlicense.** `LICENSE` rewritten to standard MIT text (Copyright © 2026 Christopher Hotchkiss). `pyproject.toml` `license = "Unlicense"` → `license = "MIT"`. Audit clean: only two runtime deps (`click` BSD-3-Clause, `pyyaml` MIT) and all optional deps (`psycopg2-binary`, `boto3`, `pytest`, `mkdocs-material`, `playwright`) are MIT-compatible; no source files carry headers needing update.
- **Beta tag removed.** `Development Status :: 4 - Beta` → `Development Status :: 5 - Production/Stable`. The project has been on a tagged-release PyPI cadence since v3.2.0 (Phase I.6) and the API surface has stabilized — beta no longer reflects reality.

---

## v3.4.0

### Ship docs + training kit in the wheel; add export commands

The wheel now bundles the full `docs/` + `training/` trees as `package-data`, and two new CLI commands (`quicksight-gen export-docs` and `quicksight-gen export-training`) write those bundles out into a target directory. Lets a `pip install quicksight-gen` user pull the handbooks and training scenarios down to disk without cloning the repo. No behavior change for source checkouts.

---

## v3.3.0

### Customization Handbook complete

Adds the full **Customization Handbook** (`handbook/customization.md` + `walkthroughs/customization/*.md`) — eight walkthroughs covering the database mapping, dataset-SQL swap, brand reskin, AWS deploy configuration, first-deploy walkthrough, app-specific metadata key extension, canonical-value extension, and customization testing. The handbook is wired into the docs site nav and the wheel's bundled docs. Phase J close-out — no analysis or dataset changes; this release ships the docs work entirely.

---

## v3.2.2

### Refactor — schema is the interface contract, not a demo artifact

Renames `quicksight_gen/demo/schema.sql` → `quicksight_gen/schema.sql` and the helper module `quicksight_gen.demo` → `quicksight_gen.schema`. The DDL is what production ETL writes against; the "demo" namespace was a misleading hangover from when the file lived under a top-level `demo/` directory beside the seed generators. The `quicksight-gen demo schema` CLI command is unchanged. Importers should switch from `from quicksight_gen.demo import generate_schema_sql` to `from quicksight_gen.schema import generate_schema_sql`.

---

## v3.2.1

### Fix — wheel ships demo schema

The v3.2.0 wheel didn't include `demo/schema.sql`, so `quicksight-gen demo schema` (and `demo apply`) failed against an installed wheel with `Schema file not found`. Patch release moves the schema into the package as `quicksight_gen/demo/schema.sql` (declared as `package-data`) and routes both CLI sites + the `TestSchemaSql` fixtures through a new `quicksight_gen.demo.generate_schema_sql()` helper. No behavior change for source checkouts.

---

## v3.2.0

### Phase H + Phase I — Handbooks, Daily Statement, sign-convention standardization, PyPI release pipeline

This release rolls up Phase H (handbook suite + walkthrough harness) and the bulk of Phase I (Daily Statement sheet, PR/AR cross-visibility unification, PR sign-convention fix, PyPI release plumbing). Dashboards are visually unchanged from v3.0.0; the seed shifts under the sign-convention fix (re-locked SHA256), and a new per-account Daily Statement sheet is added to the AR analysis. The CLI is now `pip install quicksight-gen` from PyPI on every tagged release, with a sample `out/` bundle attached to the GitHub Release for evaluators. (Version skips 3.1.0 — that tag was created during the Phase H merge before the release pipeline existed and never produced a PyPI artifact; left untouched on its original commit for history.)

### What landed

**Handbooks + walkthroughs (Phase H)**

- **MkDocs Material site** (`docs/`) deployed to GitHub Pages — Sasquatch palette + hero, with index pages for the AR Handbook, PR Handbook, Data Integration Handbook, and ETL training suite.
- **AR Handbook** — one walkthrough per AR Exceptions check (5 baseline + 9 CMS + 3 rollups), each with screenshots, scenario walkthrough, and SQL probe queries.
- **PR Handbook** — pipeline + matching walkthroughs for every merchant-support workflow (*Where's My Money*, mismatched settlements, unmatched external txns, returns, etc.).
- **Data Integration Handbook + ETL walkthroughs** — populate-transactions, validate-account-day, prove-ETL-is-working, what-to-do-when-demo-passes-but-prod-fails, add-metadata-key, tag-force-posted, extend-with-new-transfer-type.
- **`quicksight-gen demo etl-example`** CLI — emits the worked ETL example from `Schema_v3.md` as a runnable SQL script.
- **Walkthrough screenshot generator** — Playwright e2e harness reused to capture screenshots from the live deployed demo, keeping handbook screenshots in sync with the running dashboard.
- **`docs/Schema_v3.md` expansion** — per-key WHY narrative for every metadata key, end-to-end ETL examples for piping production data into the two base tables, and a new **Sign convention** subsection reconciling bank's-bookkeeping ("+= debit") and account-holder ("= money IN") readings.

**Daily Statement sheet (Phase I.1, I.2)**

- New **AR per-account daily statement** sheet (Opening Balance / Total Debits / Total Credits / Closing Stored / Drift KPIs + transaction-detail table with counter-leg account name resolution), reachable from any sub-ledger row on the AR Balances tab via right-click drill-down.
- **Two new datasets** — `ar-daily-statement-summary` (KPI strip) and `ar-daily-statement-transactions` (detail table), both following the greenfield "no artificial filters" convention.
- **PR KPI semantics regression test** (`tests/e2e/test_pr_kpi_semantics.py`) — locks the SUM-vs-COUNT and absolute-vs-signed semantics on every PR KPI against direct-DB SQL probes.
- **AR Exceptions KPI semantic coverage tests** — pinned visual-scoped filters on five PR/AR semantically-mismatched KPIs.
- **`ParameterControl` widgets** for the Daily Statement account picker (replaces `FilterControl` — gives nullable account selection + cleaner tab-load behavior).

**Cross-visibility unification (Phase I.4)**

- **`account_id NOT LIKE 'pr-%'` filters dropped** from `ar_subledger_overdraft` and `ar_subledger_daily_outbound_by_type` — PR merchant DDA rows now surface in AR exception views by intent.
- **`WHERE transfer_type IN (...)` filter dropped** from `build_ar_transactions_dataset` — PR transfer types (`sale`, `settlement`, `payment`, `external_txn`) now surface in the AR Transactions tab.
- **`ar_transfer_net_zero` widened to all transfer types**, with `expected_net_zero` flag derived in `ar_transfer_summary` so single-leg PR types (`sale`, `external_txn`) stay out of the AR Non-Zero Transfers KPI scope semantically rather than by hiding them.
- **Docs reframe** — CLAUDE.md / SPEC.md describe AR as a unified superset; PR is a tightly persona-scoped subset view. The pre-Phase I "PR-coexistence filters" framing is retired.

**PR sign convention standardization (Phase I.5)**

- **PR sale leg flipped to credit `merchant_sub`** (was debiting), aligning with the canonical `signed_amount > 0` = money IN to the account convention. Merchant DDA balances are no longer structurally negative; the drift-check invariant `daily_balances.balance = SUM(signed_amount)` holds across every account_type.
- **`-t.signed_amount` negation pattern retired** in three PR datasets (`build_sales_dataset`, `build_settlement_exceptions_dataset`, `build_sale_settlement_mismatch_dataset`) and the matching ETL example. PR datasets read the canonical sign directly.
- **SHA256 re-locked** to `6912a28c8902223a7a552194ee368f1e83df09d6779e5c735321a83c086c1cf0`.
- **Inverse cross-visibility assertion** — `tests/e2e/test_ar_cross_visibility.py::test_no_merchant_dda_is_structurally_negative` locks the fix (no merchant_dda runs negative across the entire seed window).

**PyPI release pipeline (Phase I.6)**

- **`pip install quicksight-gen`** (or `[demo]` extra) from PyPI on every tagged release.
- **Tag-triggered release workflow** (`.github/workflows/release.yml`) — six jobs: build, smoke-test wheel, bake sample bundle, publish to TestPyPI, manual-approval gate to PyPI, GitHub Release with sdist + wheel + `out-sample.zip`. Trusted Publisher OIDC; no API tokens in the repo.
- **`scripts/bake_sample_output.py`** + **`examples/config.yaml`** — produces a 39-file, ~86 KB sample of generated QuickSight JSON evaluators can inspect without running the generator.
- **`quicksight-gen --version`** flag, dynamic version source-of-truth on `quicksight_gen.__version__`.
- **README PyPI install snippet + version badge** — leads with the consumer install path before the developer-from-source path.

**CI + tooling**

- **GitHub Actions CI** — unit + integration tests on every push, build badge in README.
- **Code coverage badge** via pytest-cov + genbadge.
- **Cross-training handbook whitelabel kit** (`training/`) — strips the Sasquatch persona for licensees who want to fork the handbook structure without the demo branding.

### Notes

- **All 398 unit/integration tests** pass; e2e suite (gated on `QS_GEN_E2E=1`) covers both apps.
- **Same dataset IDs**, same dashboard IDs — safe in-place redeploy after `cleanup --yes` for any pre-3.1 stale resources.
- **Seed change**: PR sale leg sign flip changes the seed bytes; SHA256 re-lock applied. Existing demo databases need a re-`apply` to pick up the new seed (otherwise merchant DDA balances will read the old structurally-negative shape).
- **`pip install quicksight-gen`** lights up on the first published 3.1.0 tag. Source install (`pip install -e .`) continues to work for development.

---

## v3.0.0

### Phase G — Schema flatten + PR/AR data merger

The 12-table demo schema collapses to **two base tables**: `transactions` (every money-movement leg) and `daily_balances` (per-account end-of-day snapshots). PR and AR demo data now share the same physical tables; the `pr_*` legacy table family and the AR-only `transfer` / `posting` / `ar_*_daily_balances` tables are fully retired. App-specific attributes that used to live in dedicated columns now live in a portable `metadata TEXT` JSON column. Dashboards are visually identical to v2.x — only the underlying dataset SQL changed.

### What landed

- **Two-table feed contract** — `transactions` and `daily_balances` are the entire write surface a Data Integration Team has to populate. Every dataset SQL reads from these two tables plus the AR-only dimension tables (`ar_ledger_accounts`, `ar_subledger_accounts`, `ar_ledger_transfer_limits`). Six canonical `account_type` values (`gl_control`, `dda`, `merchant_dda`, `external_counter`, `concentration_master`, `funds_pool`) discriminate which app a row belongs to.
- **PR data merged in** — PR's sales / settlements / payments / external transactions / merchants now write to `transactions` + `daily_balances` instead of `pr_sales` / `pr_settlements` / `pr_payments` / `pr_external_transactions` / `pr_merchants`. PR-specific fields (`card_brand`, `cashier`, `settlement_type`, `payment_method`, `is_returned`, `return_reason`, etc.) move into the `metadata` JSON column. All 11 PR datasets rewritten to use `JSON_VALUE(metadata, '$.<key>')`.
- **AR data merged in** — AR's `transfer` + `posting` + `ar_ledger_daily_balances` + `ar_subledger_daily_balances` collapse into the same two base tables. Per-type ledger transfer limits (one row per ledger×type×day in the old `ar_ledger_transfer_limits` snapshots) collapse into the `daily_balances.metadata` JSON so the limit-breach view stays a single SELECT. All 21 AR datasets and computed views rewritten.
- **Portable JSON convention** — `metadata TEXT` columns are constrained `IS JSON` and queried only with SQL/JSON path functions (`JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`). No JSONB. No `->>` / `->` / `@>` / `?` operators. No GIN indexes on JSON. This is enforced both by code review and by `tests/test_demo_sql.py::TestSchemaSql::test_shared_base_layer_uses_portable_json`.
- **PostgreSQL 17+ requirement** — the SQL/JSON path functions are PG 17+. Pre-17 Postgres lacks `JSON_VALUE` / `JSON_QUERY` / `JSON_EXISTS` and the portability convention forbids the Postgres-only fallbacks. Documented in `docs/Schema_v3.md`, `README.md`, and `demo/schema.sql`.
- **`docs/Schema_v3.md`** — new feed contract document for the Data Integration Team persona: column specifications, canonical `account_type` / `transfer_type` values, the `metadata` JSON key catalog per app, and end-to-end ETL examples for piping production data into the two base tables.
- **Determinism re-locked with SHA256 hash assertion** — `tests/test_demo_data.py::TestDeterminism::test_seed_output_hash_is_locked` and the matching test in `tests/test_account_recon.py` assert the full seed SQL hashes to a known value. Any byte-level drift in the generator fails loudly.
- **Dataset contract preserved** — every dataset's `DatasetContract` (column name + type list) is unchanged from v2.x; the SQL implementation moved to the new tables but the projection is identical. This is the safety net that kept dashboards visually intact through the migration.
- **Legacy schema cleanup** — `pr_merchants`, `pr_sales`, `pr_settlements`, `pr_payments`, `pr_external_transactions`, `transfer`, `posting`, `ar_ledger_daily_balances`, `ar_subledger_daily_balances` are dropped. `DROP TABLE IF EXISTS` for each remains in `demo/schema.sql` for upgrade safety from older installations.

### Notes

- **349 unit/integration tests** (was 344), all green. Hash-lock tests added per app; new `TestSharedBaseLayer` class asserts every PR row also satisfies the AR base-layer projection contract.
- Same dataset IDs, same dashboard IDs — safe in-place redeploy after `cleanup --yes` to remove any pre-v3 stale resources.
- **Breaking change for self-hosted deployments**: pre-v3 callers that wrote directly to `pr_*` or `ar_*_daily_balances` need to migrate to `transactions` + `daily_balances`. See `docs/Schema_v3.md` for the mapping.
- **Postgres < 17 is no longer supported** for `demo apply`; production callers using a pre-existing datasource ARN are unaffected as long as that database supports SQL/JSON path syntax.
- `demo apply --all` and `deploy --all --generate` verified green end-to-end against live AWS.

---

## v2.0.0

### Phase F — AR restructure into Sasquatch National Bank Cash Management Suite

The AR demo abstraction shifts from "Farmers Exchange Bank — generic valley ledgers" to "Sasquatch National Bank — Cash Management Suite (CMS)". The same Pacific-Northwest bank from the PR side is now viewed through its treasury operations after SNB absorbed FEB's commercial book. The new account topology and four CMS-driven telling-transfer flows expose failure classes the old structure couldn't, and a new layer of cross-check rollups teaches analysts to recognize error *classes* before drilling into individual rows.

### What landed

- **CMS account topology** — eight internal GL control accounts (Cash & Due From FRB, ACH Origination Settlement, Card Acquiring Settlement, Wire Settlement Suspense, Internal Transfer Suspense, Cash Concentration Master, Internal Suspense / Reconciliation, Customer Deposits — DDA Control) sit above seven customer DDAs (three coffee retailers shared with PR plus four commercial customers — Cascade Timber Mill, Pinecrest Vineyards, Big Meadow Dairy, Harvest Moon Bakery).
- **Four CMS telling-transfer flows** — ZBA / Cash Concentration sweeps, daily ACH origination sweeps to the FRB Master Account, external force-posted card settlements, and on-us internal transfers through Internal Transfer Suspense. Each plants both success cycles and characteristic failures.
- **9 new CMS-specific exception checks** — sweep-target-nonzero, concentration-master-sweep-drift, ach-orig-settlement-nonzero, ach-sweep-no-fed-confirmation, fed-card-no-internal-catchup, gl-vs-fed-master-drift, internal-transfer-stuck, internal-transfer-suspense-nonzero, internal-reversal-uncredited. Each is a dedicated dataset + KPI + detail table + aging bar following the established Phase D visual pattern.
- **3 cross-check rollups** at the top of the Exceptions tab — expected-zero EOD rollup, two-sided post-mismatch rollup, and balance drift timelines rollup — teaching error-class recognition before per-check drill-down.
- **AR dataset count** — 9 → 21 (9 baseline + 9 CMS checks + 3 rollups). Exceptions tab visual count: 17 → 47.
- **AR theme rename** — `farmers-exchange-bank` preset renamed to `sasquatch-bank-ar`. Palette unchanged (valley green + harvest gold + earth tones); the AR dashboard still reads visually distinct from PR (forest green + bank gold) so users can tell the merchant and treasury views of the same bank apart at a glance.
- **AR Getting Started rewrite** — the demo flavor block now describes the SNB / CMS structure: 8 GL control accounts, 7 customer DDAs, four telling-transfer flows, and the cross-check rollups.
- **`CategoricalMeasureField` DATETIME fix** — added `_measure_date_count` helper for `DateMeasureField(COUNT)`; switched four CMS-check KPIs and two aging-bar callers off `balance_date` to ledger-account grouping (`CategoricalMeasureField` rejects DATETIME columns).

### Notes

- **344 unit/integration tests** (was 254), **101 e2e tests** (was 75), all green.
- Theme rename is backwards-incompatible: existing config files using `theme_preset: farmers-exchange-bank` must be updated to `sasquatch-bank-ar` before redeploy.
- Dataset IDs added; no existing dataset IDs renamed. Safe in-place redeploy after `cleanup --yes` to remove the dropped `qs-gen-ar-*` resources.
- `demo apply --all` and `deploy --all --generate` verified against live AWS.

---

## v1.5.0

### Phase D — Aging buckets, origin wiring, and shared visual pattern

Every exception check across both apps now carries aging information (how long the exception has been outstanding) and follows a consistent visual pattern: KPI count + detail table + horizontal aging bar chart. The `origin` attribute (deferred since Phase A) is wired into AR filters and exception detail.

### What landed

- **Aging buckets** — 5 hardcoded bands (`0-1 day`, `2-3 days`, `4-7 days`, `8-30 days`, `>30 days`) with numeric-prefixed labels for correct QuickSight sort order. `days_outstanding` (INTEGER) + `aging_bucket` (STRING) added to all 11 exception dataset contracts and SQL queries across both apps plus the Payment Recon dataset.
- **AR exception aging** — 5 aging bar charts added to the Exceptions tab (ledger drift, sub-ledger drift, non-zero transfers, limit breach, overdraft). Detail tables gain `aging_bucket` column. Exceptions tab: 12 → 17 visuals.
- **PR exception aging** — 5 aging bar charts added to the Exceptions & Alerts tab. Payment returns gains `days_outstanding` (previously missing). Sale-settlement and settlement-payment mismatch tables gain `days_outstanding` column in the visual. Exceptions tab: 7 → 12 visuals.
- **PR Payment Recon aging** — aging bar chart on the Payment Reconciliation tab. Tab: 6 → 7 visuals.
- **Origin filter** — multi-select on Transactions + Exceptions tabs. `origin` column added to non-zero-transfer and transfer-summary dataset contracts and SQL.
- **Shared `aging_bar_visual()`** — extracted to `common/aging.py`, used by all 11 aging bar charts across both apps.
- **Visual consistency** — all exception detail tables now consistently show `days_outstanding` + `aging_bucket`.

### Deferred

- **PR exception drill-downs (D.7)** — adding drill-down actions to PR exception tables requires new parameters and filter groups; deferred to Phase E which will rework the tab structure.
- **ReconciliationCheck abstraction (D.5)** — the aging bar helper was extracted; the full check abstraction doesn't cleanly cover all shapes (left≠right, row-matches-condition, unpaired). Per-check implementations are already consistent.

### Notes

- **310 unit/integration tests**, all green.
- No dataset ID changes from v1.4.0; safe in-place redeploy.

---

## v1.4.0

### Phase C — Ledger-level direct postings

Ledger accounts can now receive postings directly, not just aggregate sub-ledger balances. The drift invariant changes from 2-input (`stored ledger balance vs Σ sub-ledger balances`) to 3-input (`stored ledger balance vs Σ direct ledger postings + Σ sub-ledger stored balances`), catching discrepancies that were previously invisible.

### What landed

- **Schema changes** — `posting.ledger_account_id NOT NULL` (every posting knows its ledger); `posting.subledger_account_id` now nullable (NULL for ledger-level postings). Three new transfer types: `funding_batch`, `fee`, `clearing_sweep`.
- **Ledger-level demo scenarios** — 5 funding batches (1 ledger credit + N sub-ledger debits, net zero), 3 fee assessments (single ledger debit, intentionally non-zero — test data for exceptions), 2 clearing sweeps (2 ledger postings, net zero). Daily balance computation updated to incorporate direct postings.
- **3-input drift formula** — `ar_computed_ledger_daily_balance` view rewritten with subqueries: sub-ledger stored balance total + direct ledger posting total. Sub-ledger drift is unchanged.
- **Transactions dataset expanded** — `posting_level` column (`'Ledger'` / `'Sub-Ledger'`) added to contract and SQL. JOIN on `posting.ledger_account_id`, LEFT JOIN on sub-ledger. `COALESCE(subledger_name, ledger_name)` for display.
- **Posting Level filter** — multi-select dropdown on Transactions tab lets users isolate ledger-level vs sub-ledger activity.
- **AR type filter expanded** — `WHERE transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')` across all AR views and datasets.
- **9 scenario coverage tests** — `TestLedgerPostingScenarios` in `test_account_recon.py` verifying counts, NULL subledger, ledger FK, funding net-zero, fee non-zero, sweep net-zero, mixed-level funding.
- **PR/AR scope isolation verified** — zero transfer type overlap between apps; `pr-merchant-ledger` absent from `ar_ledger_daily_balances`.

### Notes

- **310 unit/integration tests** (was 301), all green.
- `demo apply --all` and `deploy --all --generate` verified against live AWS. Both analyses `CREATION_SUCCESSFUL`. `cleanup --dry-run` shows no stale resources.
- No dataset ID changes from v1.3.0; safe in-place redeploy.

---

## v1.3.0

### Phase B — Unified transfer schema + dataset column contracts

Both apps now share a common `transfer` + `posting` schema. AR datasets read exclusively from the unified tables; PR emits to them via dual-write (PR datasets still read legacy `pr_*` tables for domain-specific metadata). Every dataset declares an explicit column contract so the SQL is one implementation of a stable interface.

### What landed

- **Unified schema** — `transfer` and `posting` tables added to `demo/schema.sql`. `transfer` carries `transfer_id`, `parent_transfer_id` (self-ref for chains), `transfer_type`, `origin`, `amount`, `status`, `created_at`, `memo`, `external_system`. `posting` carries `posting_id`, `transfer_id` FK, `subledger_account_id` FK, `signed_amount`, `posted_at`, `status`.
- **AR fully migrated** — all 9 AR dataset SQL queries rewritten to project from `posting` + `transfer`. Legacy `ar_transactions` table dropped; AR views (`ar_transfer_summary`, `ar_subledger_daily_outbound_by_type`, etc.) rewritten to join `posting` + `transfer`. AR demo generator no longer emits `ar_transactions` INSERTs.
- **PR dual-write** — PR demo generator emits the full transfer chain (`external_txn → payment → settlement → sale`) linked by `parent_transfer_id`, with postings on PR-specific sub-ledger accounts (`pr-sub-{merchant}`, `pr-external-customer-pool`, `pr-external-rail`). Legacy `pr_*` tables still populated and read by PR datasets.
- **Dataset column contracts** — `DatasetContract` dataclass in `common/dataset_contract.py` with `ColumnSpec(name, type)`. All 20 dataset builders declare contracts; unit tests assert SQL projections match declared contracts.
- **Cross-app integrity tests** — posting FK integrity across apps, no ID collisions, transfer type enum coverage (all 8 CHECK values present in combined data).
- **Schema DDL ordering fix** — `transfer` + `posting` tables now created before AR views that reference them.

### Deferred

- **PR dataset cutover (B.6)** — PR datasets need domain-specific metadata (`card_brand`, `cashier`, `settlement_type`, `payment_method`) that lives on legacy `pr_*` tables. Cutover deferred until the customer decides which PR columns they actually need; at that point, extract metadata into slim tables and rewrite PR datasets to join `transfer`/`posting` with metadata.

### Notes

- **301 unit/integration tests** (was 255), **94 e2e tests** — all green.
- `demo apply --all` and `deploy --all --generate` verified against live AWS. `cleanup --dry-run` shows no stale resources.
- No dataset ID changes; safe in-place redeploy after `cleanup --yes` from v1.2.0.

---

## v1.2.0

### Phase A — Account Recon vocabulary rename + `origin` attribute

Account Reconciliation's internal vocabulary ("parent / child accounts") always read a little structural; the classical accounting pattern is **control account + subsidiary ledger**, and end users are accountants who already think in GL vocabulary. v1.2.0 aligns the code, SQL, QuickSight labels, and docs with that language, and plants an additive `origin` column on transactions for the later phases in the major evolution to consume.

### What landed

- **Vocabulary rename across AR** — user-visible across every AR tab:
  - Tables/views: `ar_accounts` → `ar_subledger_accounts`; drift/breach/overdraft views reshaped to `ar_subledger_*` / `ar_ledger_*`.
  - Columns: `account_id` → `subledger_account_id`, `parent_account_id` → `ledger_account_id` (cascades through every SELECT projection and dataset contract).
  - QuickSight labels: "Parent/Child Account" → "Ledger/Sub-Ledger Account" on every table, KPI, filter, drill-down, and Show-Only-X toggle.
  - Dataset IDs renamed from `qs-gen-ar-parent-*` / `qs-gen-ar-account-*` → `qs-gen-ar-ledger-*` / `qs-gen-ar-subledger-*`. **One-time cleanup required**: old tagged resources in the target account need `quicksight-gen cleanup --yes` after the v1.2.0 deploy, since dataset IDs are rename-as-delete-plus-create.
  - Drill-down parameters: `pArAccountId` → `pArSubledgerAccountId`, `pArParentAccountId` → `pArLedgerAccountId`.
- **`origin` attribute on transactions** — additive, tag-only in v1.2.0:
  - `ar_transactions.origin VARCHAR(30) NOT NULL DEFAULT 'internal_initiated' CHECK IN ('internal_initiated', 'external_force_posted')`.
  - Demo generator sprinkles ~10% `external_force_posted` (every 10th emitted leg) for deterministic coverage.
  - Surfaced as a visible column on Transaction Detail. **No filter, exception check, or drill consumes it yet** — Phase B/D will wire it in.

### Notes

- **255 unit/integration tests** (was 253) — added one scenario-coverage assertion for origin values and one dataset-contract assertion for the `origin` column. E2E verified against a live deploy with `./run_e2e.sh --parallel 4`.
- No behavioral changes in AR reconciliation logic — only vocabulary and one new column.
- Payment Recon is untouched: zero references to parent/child existed there.
- Phase B (unified transfer schema + column contract) will reshape PR's sales/settlements/payments into the same `transfer` primitives AR already uses. See `SPEC.md` "Suggested phasing".

---

## v1.1.0

### Filter-propagation browser e2e expansion

The browser e2e suite previously spot-checked a single date-range filter on one table per app. Every other filter was trusted to work if the dashboard JSON referenced it. v1.1.0 closes that gap on the Payment Recon side, captures one documented QuickSight limitation, and parallelizes the suite so the wider coverage fits the runtime budget.

### What landed

- **Payment Recon filter-propagation coverage** (Phases 1–2):
  - Shared filter-interaction helpers in `tests/e2e/browser_helpers.py` — `set_dropdown_value`, `set_multi_select_values`, `clear_dropdown`, `set_date_range`, `count_table_rows` / `count_table_total_rows` (pagination-aware), `count_chart_categories` (canvas-aware via aria-label + legend fallback), `read_kpi_value` / `wait_for_kpi_value_to_change`, plus `wait_for_*_to_change` pollers for each.
  - Split the shared `fg-date-range` filter group into four per-sheet groups (`fg-{sales,settlements,payments,exceptions}-date-range`), each scoped to its sheet's native timestamp column. The old `CrossDataset="ALL_DATASETS"` control rendered but was inert on sheets whose dataset didn't have a `sale_timestamp` column.
  - New parametrized tests for future-window, past-window, and in-window date filtering on Sales / Settlements / Payments.
- **Documented QS navigation filter-stacking** (Phase 5): drill-down-set parameters persist across tab-switches (`A → B → A` leaves B-derived filter on A). QuickSight has no API to clear a parameter on nav. Captured as `xfail(strict=False)` in `tests/e2e/test_filter_stacking.py`, documented under "Known limitations" in README, and called out on both Getting Started sheets (accent-colored bullet).
- **Parallelized e2e suite** (Phase 6): added `pytest-xdist`, default `-n 4` in `run_e2e.sh`, `--parallel N` override. Full 101-item suite drops from ~305s serial to ~133s at `-n 4` and ~81s at `-n 8`; `-n 12` flakes (timing-sensitive date-range narrowing).
- **Dedup pass** (Phase 1.8): five DOM-probe helpers (`selected_sheet_name`, `wait_for_sheet_tab`, `first_table_cell_text`, `wait_for_table_cells_present`, `click_first_row_of_visual`) plus `sheet_control_titles` / `wait_for_sheet_controls_present` / `wait_for_visual_titles_present` extracted from per-file copies into `browser_helpers.py`.

### Known gap

Account Recon filter-propagation coverage was deferred ahead of a major spec revision that will refactor AR heavily. Existing AR e2e still covers rendering, drill-downs, and Show-Only-X toggles; filter-propagation parity with PR will return after the revision lands.

### Notes

- **253 unit/integration tests**, **101 e2e tests** (94 passed / 6 skipped / 1 xfailed) — all green.
- No schema, dataset, or generated-resource ID changes beyond the internal split of `fg-date-range` into four per-sheet filter groups. Safe in-place redeploy.
- `run_e2e.sh --parallel 8` is the recommended stable ceiling on a modern Mac; `--parallel 1` forces serial.

---

## v1.0.1

### Post-release polish

Two small UX fixes from first round of v1.0.0 testing:

- **Payment Reconciliation tab — table order swapped.** Internal Payments now renders on the left, External Transactions on the right. Reading flow goes internal → external, matching the rest of the pipeline (sales → settlements → payments → external).
- **Account Recon Transfers tab — duplicate filter removed.** The "Show Only Unhealthy" SINGLE_SELECT toggle was redundant with the "Transfer Status" multi-select (both filtered on `net_zero_status`). Dropped the toggle; the multi-select stays.

### Notes

- Tests: 253 unit/integration (was 254 — one toggle assertion folded into a no-toggle assertion), 75 e2e — all green.
- No schema, dataset, or generated-resource ID changes; safe in-place redeploy.

---

## v1.0.0

### Spec complete — dual-dashboard restructure delivered

v1.0.0 ships the full spec: two independent QuickSight apps (Payment Reconciliation + Account Reconciliation) generated from Python, deployed via boto3, tested at four layers (unit, integration, API e2e, browser e2e). Both apps share one theme, account, datasource, and CLI surface, yet are selectable individually for fast iteration (`--all` exercises both, `payment-recon` / `account-recon` targets one).

### What landed since v0.5.0

- **Account Recon Phase 4** (v0.6.0): multi-select filters per tab (parent/child account, transfer status, transaction status); Show-Only-X SINGLE_SELECT toggles (unhealthy transfers, failed transactions, drift); left-click and right-click drill-downs covering all six user-research flows; Parent Drift Timeline alongside the existing Child Drift Timeline; same-sheet chart filtering on every new chart.
- **Account Recon Phase 5** (v0.7.0): per-type daily transfer limits (ACH / wire / internal / cash) enforced against parent limits fed upstream, plus child overdraft detection. Exceptions tab grew from 3 independent checks to 5 (parent drift, child drift, non-zero transfers, limit breaches, child overdrafts) laid out as paired half-width tables + two drift timelines for maximum density.
- **Account Recon browser e2e** (v0.8.0): 16 Playwright tests mirror PR's coverage — dashboard load, per-sheet visual counts, drill-downs (Balances→Txn, Transfers→Txn, Exceptions Breach→Txn), date-range filter narrowing, all five Show-Only-X toggles. Right-click `DATA_POINT_MENU` drill is covered structurally (Playwright menu-select is flaky). Screenshots namespaced per app under `tests/e2e/screenshots/{payment_recon,account_recon}/`.
- **Rich-text Getting Started sheets** (v1.0.0, Phase 6): both apps' landing tabs use proper typography — 36px welcome, 32px section headings, 20px subheadings, accent-colored links, bulleted per-sheet summaries — via a new `common/rich_text.py` XML composition helper. Theme accent resolves to hex at generate time (QuickSight text parser doesn't accept theme tokens).
- **Docs refresh** (v1.0.0, Phase 7): README rewritten for the two-app structure; CLAUDE.md updated for the `common/` + per-app module layout; SPEC.md swept — delivered checkboxes flipped, open questions collapsed into a Decisions section.

### Stats

- **~16,030 lines of Python** (10,570 in `src/`, 5,460 in `tests/`) + 485 lines of schema DDL.
- **254 unit / integration tests**, **75 e2e tests** (329 total), **436 assert statements**.
- **2 apps** (6 + 5 = 11 sheets), **20 datasets** (11 PR + 9 AR), **3 theme presets**, **1 shared datasource**.

### Notes

- The e2e suite is gated on `QS_GEN_E2E=1` and requires AWS credentials; `pytest` alone runs the 329 fast tests with no AWS dependency.
- Dataset Direct Query (no SPICE) — seed changes show up immediately after `demo apply`, no refresh step needed.
- `cleanup --dry-run` / `cleanup --yes` sweeps stale `ManagedBy: quicksight-gen` resources not in current `out/`.

---

## v0.5.0

### Account Reconciliation — second app

Phase 3 adds a second QuickSight app, Account Reconciliation, alongside the existing Payment Reconciliation dashboard. The AR dashboard covers a bank's double-entry ledger with two independent stored-balance feeds (parent-level and child-level) and reconciles both against the underlying transactions.

### New app

- **Account Reconciliation dashboard** — 5 tabs (Getting Started + Balances, Transfers, Transactions, Exceptions). Shared date-range filter; drill-downs and multi-select filters land in Phase 4.
- **Two independent drift checks** exposed side-by-side on the Exceptions tab:
  - Parent drift — stored parent balance vs Σ of its children's stored balances (points at the parent-balance upstream feed).
  - Child drift — stored child balance vs running Σ of posted transactions (points at the child-balance feed or a ledger miss).
- **Transfer reconciliation** — transfers are not a table; they're a `transfer_id` grouping of `ar_transactions`. `ar_transfer_summary` surfaces net-zero status and a representative memo per transfer. The Exceptions tab flags transfers whose non-failed legs don't sum to zero (failed counter-leg, keying error, fee drift).
- **`farmers-exchange-bank` theme preset** — earth tones, valley greens, harvest gold. Applies the "Demo — " analysis name prefix when selected.
- **Farmers Exchange Bank demo data** — 5 parent accounts (Big Meadow Checking, Harvest Moon Savings, Orchard Lending Pool, Valley Grain Co-op, Harvest Credit Exchange) moving money between 10 child accounts over ~40 days. Planted: 3 parent-day drifts, 4 child-day drifts (disjoint from parent cells), 4 failed-leg transfers, 4 off-amount transfers, 4 fully-failed transfers.
- **CLI — two-app aware** — `generate account-recon`, `demo schema|seed|apply account-recon`, `deploy account-recon`, and `--all` exercises both apps.

### Scope clarification (SPEC)

"Internal" vs "external" describes **this application's reconciliation scope**, not system ownership. All accounts (internal + external, parent + child) appear in the same tables; external-scope accounts are present but not reconciled (that's regulators' job). Parent-level and child-level stored balances may be fed by different upstream systems, which is why the two drift checks are independent.

### Resources

- Dashboard: `qs-gen-account-recon-dashboard`
- Analysis: `qs-gen-account-recon-analysis`
- 7 AR datasets: parent_accounts, accounts, transactions, parent_balance_drift, account_balance_drift, transfer_summary, non_zero_transfers
- 5 AR tables (`ar_parent_accounts`, `ar_accounts`, `ar_parent_daily_balances`, `ar_account_daily_balances`, `ar_transactions`) + 6 views (`ar_computed_account_daily_balance`, `ar_account_balance_drift`, `ar_computed_parent_daily_balance`, `ar_parent_balance_drift`, `ar_transfer_net_zero`, `ar_transfer_summary`)

### Notes

- AR browser e2e tests and cross-sheet drill-downs deferred to Phase 5.
- Phase 3 review caught a scope gap — child balances were not reconciled in the initial skeleton. Resolved in Phase 3.10 with an independent `ar_account_daily_balances` feed and a second drift view.

---

## v0.4.0

### Payment Reconciliation domain additions

Phase 2 bundles refunds, optional sales metadata, payment-method filtering, an expanded Exceptions tab, a Getting Started landing sheet, right-click drill-downs, and state-toggle filters into a richer Payment Reconciliation experience. Dashboard goes from 5 tabs to 6.

### New features

- **Refund support** — `sale_type` column on `pr_sales` with negative amounts; refund rows flow into settlements so signed sums net correctly.
- **Optional sales metadata** — taxes / tips / discount_percentage / cashier declared in `OPTIONAL_SALE_METADATA`. Each column auto-generates a typed filter control on Sales Overview (numeric → slider, string → multi-select).
- **Payment method filter** — multi-select dropdown scoped to Settlements + Payments tabs.
- **Expanded Exceptions & Alerts** — three new mismatch tables (sale↔settlement, settlement↔payment, unmatched external transactions) alongside the existing unsettled-sales and returned-payments tables.
- **Getting Started landing sheet** — now tab index 0, with one plain-text block per downstream sheet plus a demo-scenario flavor block when `--theme-preset sasquatch-bank` is active. Rich text / hyperlink formatting deferred to Phase 6.
- **Right-click drill-downs** — Sales `settlement_id` → Settlements, Payments `external_transaction_id` → Payment Reconciliation. Source cells styled with a pale tint to cue the menu. Plain left-click drills keep their accent-only styling for a visual distinction between the two click idioms.
- **Payment Reconciliation side-by-side tables** — External Transactions and Internal Payments render half-width rather than stacked; mutual click-filter still works.
- **State toggles (Show-Only-X)** — SINGLE_SELECT dropdowns on Sales ("Show Only Unsettled"), Settlements ("Show Only Unpaid"), Payments ("Show Only Unmatched Externally"). These replace the per-tab days-outstanding slider, which turned out to overlap with the existing date-range filter.
- **Orphan external transactions in demo data** — the generator now always emits ~13 ext txns with no internal payment link plus ~4 unmatched payments, so Payments toggle, Exceptions table, and Payment Reconciliation all have data out-of-the-box.

### Changed

- Dashboard sheet count: 5 → 6 (Getting Started added at index 0).
- Filter group count: raised from ~11 to 18+ (optional-metadata filters, state toggles, drill-down parameter filters, recon filters).
- Exceptions & Alerts visual count: 4 → 7.
- Demo data: refund rows added to sales; external transactions restructured to guarantee unmatched coverage.

### Removed

- **Days-outstanding slider** — removed from every tab. The date-range filter already covered the workflow and the slider duplicated intent. Replaced by Show-Only-X toggles on the three pipeline tabs.

### Notes

- Right-click menus rely on `DATA_POINT_MENU` trigger — only one left-click action per visual is allowed, so the menu trigger is how additional click targets surface without conflicting with charts' drill-down behavior.
- Every sheet still has a plain-language description; every visual still has a subtitle. Coverage asserted in unit and API e2e tests.

---

## v0.3.0

### End-to-end test harness

A two-layer e2e harness validates a deployed dashboard, complementing the existing unit suite. Tests are skipped by default unless `QS_GEN_E2E=1` is set, so a plain `pytest` run stays AWS-free.

**API layer (boto3, ~13s):** dashboard / analysis / theme / dataset existence and status, dashboard structure (sheets, visual counts, parameters, filter groups, dataset declarations), dataset import mode and key columns.

**Browser layer (Playwright WebKit headless, ~60s):** dashboard loads via a pre-authenticated embed URL, all 5 sheet tabs render, per-sheet visual counts in the actual DOM, Settlements→Sales and Payments→Settlements drill-down navigation, Payment Reconciliation mutual table filtering (external transaction click filters payments table), and date-range filter behavior (future date range empties Sales Detail).

### One-shot runner

`./run_e2e.sh` regenerates JSON, runs `deploy.sh`, then `pytest tests/e2e` so iteration is hands-off:

```bash
./run_e2e.sh                       # full cycle
./run_e2e.sh --skip-deploy api     # skip generate+deploy, API only
./run_e2e.sh --skip-deploy browser # skip generate+deploy, browser only
```

### New features

- 33 e2e tests across 8 test files under `tests/e2e/`
- Tunable timeouts via `QS_E2E_PAGE_TIMEOUT`, `QS_E2E_VISUAL_TIMEOUT` env vars (defaults 30s / 10s)
- Failure screenshots saved to `tests/e2e/screenshots/` (gitignored)
- New `e2e` optional dependency group: `pip install -e ".[e2e]"` then `playwright install webkit`

### Notes

- Embed URL must be generated against the **dashboard region**, not the QuickSight identity region (us-east-1). Embed URLs are **single-use** so fixtures are function-scoped.
- The conftest looks for config at `config.yaml` then `run/config.yaml` then env vars.

---

## v0.2.0

### Consolidated single-analysis architecture

The separate reconciliation analysis has been merged into the financial analysis as the **Payment Reconciliation** tab. The project now generates one analysis and one dashboard (down from two of each), reducing deployment complexity and enabling cross-sheet drill-down without URL-based linking.

### Payment-only reconciliation

Reconciliation now correctly focuses on payments -- the only records that leave the internal system. Sales and settlements no longer have external transaction IDs or recon views. This eliminated 3 datasets, 2 database views, and the `late_thresholds` table.

### New features

- **Payment Reconciliation tab** with 3 KPIs (matched amount, unmatched amount, late count), a stacked bar chart (match status by external system), and dual mutually-filterable tables (external transactions and internal payments)
- **Mutual table filtering** -- click an external transaction to see its linked payments; click a payment to filter back to its transaction
- **Config-driven late threshold** (`late_threshold_days`, default 30) replaces the database table. Users can also adjust interactively via the days-outstanding slider
- **Same-sheet chart filtering** on all tabs -- clicking a bar or pie slice filters the detail table on the same sheet
- **Cross-sheet drill-down** -- click a settlement row to jump to Sales filtered by that settlement; click a payment row to jump to Settlements

### Breaking changes

- `recon-analysis.json` and `recon-dashboard.json` are no longer generated. Delete them from AWS before deploying (`./deploy.sh --delete`)
- Dataset count reduced from 11 to 8. The removed datasets: `qs-gen-sales-recon-dataset`, `qs-gen-settlement-recon-dataset`, `qs-gen-recon-exceptions-dataset`
- `external_transaction_id` removed from sales and settlements datasets/schema
- `transaction_type` removed from external_transactions dataset/schema
- `late_thresholds` table removed from demo schema
- `build_recon_analysis()` and `build_recon_dashboard()` no longer exist

### Bug fixes

- Fixed `DefaultFilterControlConfiguration` rejection by using `SINGLE_DATASET` scope with direct filter controls for single-sheet filters
- Fixed `SetParametersOperation` requiring a preceding `NavigationOperation`
- Fixed QuickSight rejecting multiple `DATA_POINT_CLICK` actions on a single visual

---

## v0.1.0

Initial release. Financial analysis with 4 tabs (Sales, Settlements, Payments, Exceptions), reconciliation analysis with 4 tabs, demo data system, theme presets, and deploy script.
