# Phase M.0 — vertical-slice spike findings

Notes captured during M.0 to inform M.1 library design + SPEC amendments. This file is updated as findings surface throughout M.0.x; reviewed and consolidated at the M.0.13 iteration gate.

Format per entry: surface point (which substep), observation, implication for SPEC, implication for M.1 library.

---

## Consolidation (M.0.12)

12 findings logged. Categorized by what they trigger:

**SPEC amendment** *(real changes to SPEC.md):*
- **F5 — InstancePrefix regex/length pin** → applied at M.0.13.

**M.1 library design** *(concrete asks the M.1 plan needs to absorb):*
- **F1 — Rail-references-Role validation** is already in SPEC's load-time list; M.1.7 tests cover it.
- **F2 — Rail as discriminated union** (TwoLegRail / SingleLegRail) — M.1.1 dataclass shape.
- **F3 — Two-pass validation** (cross-entity: TransferTemplate.LegRails ↔ Rail.expected_net interplay) — M.1.3.
- **F4 — `Decimal(str(value))` coercion** uniformly across Money-typed YAML fields — M.1.2.
- **F6 — Two parallel "Dataset" types** (api `DataSet` vs tree `Dataset`); rename or wrap to remove the colloquial collision — M.1.4 / library-side cleanup.

**Refactor (touches existing code beyond M.1):**
- **F7 — Promote `ScreenshotHarness` out of `tests/e2e/`** to a public `common/screenshot/` (or similar). Production code can't import from `tests/`. Add as a new M.1 substep.
- **F8 — Sheet screenshot dict keyed by `sheet_id` string** (not Sheet ref). M.1's harness API design.

**Confirmations (no plan change, but worth pinning):**
- **F9 — Existing `deploy()` + `build_datasource()` + `build_theme()` reuse cleanly** for an L2-driven app. M.6 (CLI workflow) inherits them; doesn't need to redesign.
- **F10 — L2 InstancePrefix splice over `cfg.resource_prefix` works** — confirms the SPEC's Storage Isolation rule materializes in practice. M.6 default should adopt this.
- **F11 — Two-input CLI split (`--instance` + `--config`)** — adopt for the production CLI in M.6.

**Operational lesson (no SPEC, no library — pattern for M.7/M.8):**
- **F12 — Aurora Serverless cold-start manifests as QS's generic "We can't open that dashboard"** error. Every screenshot/browser-side CLI path needs an explicit DB warm-up (`SELECT 1` via psycopg2 right before fetching the embed URL). v5.0.2 e2e suite already has the pattern; lift it.

**Net for M.1+:** SPEC amendment small (F5). M.1 plan absorbs F1-F8 into existing/new substeps; M.6 inherits F9-F11; M.7/M.8 inherits F12.

---

## F1 — `Account.Role` is effectively required for Rail-referenced accounts

**Surfaced:** M.0.2 (writing `slice.yaml`)

**Observation:** SPEC declares `Account.Role` as optional (`Role?: Role`). In practice, any Account referenced by a Rail's `source_role` / `destination_role` / `leg_role` MUST have a Role declared — otherwise the Rail's role-resolution can't pick a concrete account. For the spike (1 Rail touching both accounts), both Accounts had to carry a Role despite the SPEC marking it optional.

**Implication for SPEC:**
- Option (a) — Tighten: add a validation rule "every Account that appears in a Rail's role-resolution graph MUST have a `role` field set." Makes the requirement explicit at load time.
- Option (b) — Leave optional, document implicitly: an Account with no Role simply isn't reachable from any Rail; trying to reach a Role no Account declares is what fails. Validation would still need to catch the orphan-rail-role case.

Both are valid; (a) is a slightly cleaner rule. Either way, "Role is required when ..." needs documenting.

**Implication for M.1:**
- The YAML loader's validation MUST reject a Rail whose `source_role` / `destination_role` / `leg_role` doesn't resolve to at least one declared `Account.Role` (or AccountTemplate.Role).
- Add to M.1.7's rejection-test audit table: "rail references undeclared role."

---

## F2 — Rail two-leg vs single-leg is a clean structural mutual-exclusion

**Surfaced:** M.0.3 (writing `loader.py`)

**Observation:** The SPEC declares Rail as having two field groups (two-leg: `source_role + destination_role + expected_net`; single-leg: `leg_role + leg_direction`) with the rule "exactly one of the two groups." This naturally splits at validation time: a Rail that mentions ANY two-leg field disqualifies it from single-leg, and vice versa. Cleanly enforceable at load-time with no runtime ambiguity.

**Implication for SPEC:** Already articulated in SPEC — no change needed. Just confirms the structural cut.

**Implication for M.1:**
- The library's typed Rail dataclass should express this as a discriminated union (e.g. `TwoLegRail` and `SingleLegRail` as separate classes deriving from a base) rather than one dataclass with all fields nullable.
- Discriminated union → pyright catches "leg_role on a two-leg rail" at the wiring site, not at load.
- M.1.7 rejection test: "rail with both two-leg and single-leg fields rejected."

---

## F3 — `expected_net` requirement is state-dependent on TransferTemplate membership

**Surfaced:** M.0.3 (writing `loader.py`)

**Observation:** Per SPEC: a two-leg rail that fires standalone Transfers MUST have `expected_net`; a two-leg rail that's a leg-pattern of a TransferTemplate (via LegRails) MUST NOT carry `expected_net` (it lives on the template). The spike doesn't have TransferTemplates so the rule degenerates to "always require." But M.3 will need cross-entity validation: deciding whether a Rail's `expected_net` is required depends on whether some TransferTemplate references it in `leg_rails`.

**Implication for SPEC:** Already accurately articulated.

**Implication for M.1:**
- The two-pass validation pattern (load all entities, then cross-validate) is needed for this and other cross-entity rules. Single-pass per-entity validation isn't sufficient.
- Test case for M.1.7: "two-leg rail with expected_net set AND listed in some TransferTemplate.LegRails → reject as conflict."

---

## F4 — Decimal coercion from YAML requires `Decimal(str(value))`

**Surfaced:** M.0.3 (writing `loader.py`)

**Observation:** `yaml.safe_load` returns `int` or `float` for numeric YAML values; constructing `Decimal` from `float` loses precision (`Decimal(0.1) == Decimal('0.1000000000000000055511151231257827...')`). The fix is to round-trip through `str`: `Decimal(str(yaml_value))` produces the expected `Decimal('0.1')`. The spike applied this to `expected_net` and `expected_eod_balance`.

**Implication for SPEC:** No change — this is a YAML/Python plumbing concern.

**Implication for M.1:**
- The library's loader MUST apply `Decimal(str(...))` coercion uniformly across every Money-typed YAML field (`expected_net`, `expected_eod_balance`, `cap` in LimitSchedules, etc.).
- A small helper `_load_money(raw: object) -> Decimal | None` keeps the rule in one place.

---

## F5 — `instance` (the InstancePrefix) needs a pinned identifier regex

**Surfaced:** M.0.3 (writing `loader.py`)

**Observation:** SPEC says InstancePrefix is "SQL-identifier-safe" but doesn't pin the regex. The spike picked `^[a-z][a-z0-9_]*$` (lowercase start, alphanumeric + underscore). Postgres identifier rules allow uppercase but force lowercase if unquoted, leading to the well-known quoted-vs-unquoted-identifier hazard. Locking lowercase-only avoids the whole class.

**Implication for SPEC:** Pin the regex explicitly: `^[a-z][a-z0-9_]*$`, max length ≤ 30 chars (leaves room for the longest table-name suffix within Postgres' 63-char identifier limit).

**Implication for M.1:**
- Centralize the identifier regex + length cap as a module constant; reuse for any other identifier-typed field that lands in v1 (Role names? TransferType names?). Each gets validated at load.

---

## F6 — Two parallel "Dataset" concepts; tree node wraps API DataSet

**Surfaced:** M.0.6 (writing `build_dashboard`)

**Observation:** `quicksight_gen.common.models.DataSet` (the AWS-API-shaped dataclass returned by `build_dataset()`) and `quicksight_gen.common.tree.Dataset` (the typed tree node used by visuals to subscript columns: `ds["col"]`) are different types with the same colloquial name. The wiring is: build the API DataSet → wrap in a tree Dataset node passing `identifier` (matches `visual_identifier` from `build_dataset`) + `arn`. The contract registry inside `build_dataset` connects the two by name.

**Implication for SPEC:** No SPEC change — this is internal library plumbing.

**Implication for M.1:**
- The two-step "build API DataSet → wrap in tree Dataset" feels redundant. M.1 should consider whether `build_dataset()` could return the tree node directly (or a (api_dataset, tree_node) pair to make the dependency explicit).
- At minimum: pick a unique name. Calling them both `Dataset`/`DataSet` is a confusion source — consider renaming the API one to `DataSetModel` or the tree one to `DatasetRef`.

---

## F7 — `ScreenshotHarness` lives under `tests/e2e/` but is needed by production code — RESOLVED M.1.10

**Surfaced:** M.0.8 (writing `capture_drift_screenshot`)

**Observation:** `ScreenshotHarness` was built in L.1.10.7 as test infrastructure under `tests/e2e/screenshot_harness.py`. The `generate training` CLI command needs to invoke it during normal user workflow (rendering handbook pages with embedded screenshots), which means production code now imports from `tests/`. That import path is wrong — `tests/` is conventionally not part of the package surface.

**Resolution (M.1.10):** Promoted to `src/quicksight_gen/common/browser/`:
- `helpers.py` (was `tests/e2e/browser_helpers.py`)
- `screenshot.py` (was `tests/e2e/screenshot_harness.py`)
- Re-exported via `quicksight_gen.common.browser` package.

`SCREENSHOT_DIR` now resolves relative to cwd (overridable via `QS_E2E_SCREENSHOT_DIR`) so the e2e `screenshot()` helper still writes to `tests/e2e/screenshots/` from the repo root. The package is NOT in the pyright strict gate yet (browser_helpers loosely types Playwright Page as plain `page` parameter); tightening is queued for when M.6/M.7/M.8 surface what production really needs.

---

## F8 — Sheet has TWO IDs the spike reasoned about: `sheet_id` (URL-stable) and visual screenshot filenames — RESOLVED M.1.10

**Surfaced:** M.0.6 + M.0.8 (sheet construction + screenshot wiring)

**Observation:** The `Sheet` constructor takes `sheet_id` (an explicit, URL-stable identifier) plus auto-derived internal IDs. `ScreenshotHarness.capture_all_sheets()` originally returned `dict[sheet_id_str, Path]` keyed by the explicit sheet_id string, with PNG filenames `<sheet_id>.png`. Lookups by sheet name would feel more natural for "I want the drift sheet's PNG" but require the harness to know about names; keying by sheet_id is more robust but forces callers to remember the explicit ID strings.

**Resolution (M.1.10):** Reshaped harness API to key on object refs:
- `capture_all_sheets()` → `dict[Sheet, Path]`
- `capture_per_visual(sheet)` → `dict[VisualLike, Path]`
- `capture_with_state(...)` → `dict[Sheet, Path]`

On-disk filenames stay `<sheet_id>.png` / `<visual_id>.png` so prior images overwrite cleanly. Callers now lookup with `paths[my_sheet]` from the same App they constructed — no parallel sheet_id strings. The spike's `capture_drift_screenshot` re-wired to `paths[drift_sheet]` (`drift_sheet = app.analysis.sheets[0]`).

---

## F9 — Existing `deploy()` + `build_datasource()` + `build_theme()` reuse cleanly for a new app

**Surfaced:** M.0.10 (real-AWS deploy via the spike CLI)

**Observation:** The spike's `apply dashboards` writes its JSON bundle in the existing convention (`<app>-analysis.json` + `<app>-dashboard.json` + `theme.json` + `datasource.json` + `datasets/<id>.json`) and calls `quicksight_gen.common.deploy.deploy(cfg, out_dir, ["spike-drift"])` directly. Deploy succeeded on first run — DataSource + Theme + Dataset + Analysis + Dashboard all created cleanly under the `spk-` prefix, no QS API surprises. The existing infrastructure is reusable as-is for the new L2-driven workflow.

**Implication for SPEC:** No change.

**Implication for M.1:**
- The `deploy()` API + the JSON file naming convention can stay. M.1's library can wrap them; doesn't need to redesign them.
- `build_datasource()` lives under `apps/payment_recon/datasets.py` but is generic (doesn't know about PR specifically). Should move to `common/` so other apps + the spike don't need cross-app imports for it.

---

## F10 — L2 InstancePrefix over `cfg.resource_prefix` is the right composition

**Surfaced:** M.0.10 (CLI rewrite for `--instance` + `--config`)

**Observation:** The AWS config YAML's `resource_prefix: "qs-gen"` would collide with the existing demo's resources if used as-is. The spike CLI splices `cfg.resource_prefix = inst.instance` immediately after loading both — so `qs-gen` from `run/config.yaml` becomes `spk` for the spike deploy. Two L2 instances (production demo + spike) coexist in the same AWS account because their prefixes differ.

This is the SPEC's storage isolation rule (L2 InstancePrefix scopes every generated resource ID) materialized in the actual deploy, and it works.

**Implication for SPEC:** No change — this confirms the Storage Isolation section's design.

**Implication for M.1:**
- The "L2 instance prefix overrides AWS config prefix" rule should be the default behavior of the production CLI's load path, not a per-command splice. Cleanest: the loader returns a Config where `resource_prefix = inst.instance` already, and the AWS YAML's prefix is informational/default-only.

---

## F11 — Two CLI inputs (`--instance` + `--config`) work; existing `--config` convention preserved

**Surfaced:** M.0.10 (CLI rewrite)

**Observation:** Renaming the spike's L2 YAML option from `--config` to `--instance` (`-i`) and adding `--config` (`-c`) for the AWS YAML preserves the existing CLI's `-c` convention. Two required options per command read cleanly: `apply schema --instance slice.yaml --config run/config.yaml`. The two-input split mirrors LAYER 1 (universal AWS coords + Postgres URL) vs LAYER 2 (per-integrator institution).

**Implication for SPEC:** No change.

**Implication for M.1:**
- The production CLI should adopt the same `--instance` / `--config` split. `quicksight-gen apply schema -c run/config.yaml -i sasquatch_ar.yaml` becomes the workflow shape for M.6.
- Default for `--config` could fall back to `config.yaml` in CWD (matches existing `quicksight-gen` convention) if not specified.

---

## F12 — Aurora Serverless cold-start manifests as a generic "We can't open that dashboard" error in the embed UI

**Surfaced:** M.0.10 (debugging the screenshot capture against the deployed dashboard)

**Observation:** The screenshot pipeline ran cleanly (embed URL fetched, Playwright launched, navigation succeeded) but every screenshot showed QuickSight's generic error page: *"We can't open that dashboard. This usually happens when you don't have access permission, it's from another Quick account, or it was deleted."* I burned significant time chasing permissions (verified — identical to working dashboards), embed-URL targeting (verified — same `get_user_arn()` default the existing tests use), and selector-wait timing (irrelevant — same error regardless of wait shape).

**Actual root cause (per user):** The backing Aurora Postgres is autoscaling Serverless v2 that **goes to sleep after 5 minutes of inactivity**. The dashboard's data-fetch silently failed against the cold DB, and QuickSight's embed UI surfaced that as the same generic "we can't open" page that permissions / scope / deletion errors produce — masking the actual cause.

The v5.0.2 e2e test suite already handles this — every browser test has a **DB warm-up phase** before the actual capture. The spike CLI doesn't (yet).

**Implication for SPEC:** No SPEC change.

**Implication for M.1:**
- **Every screenshot / browser-side test path needs a warm-up step.** A simple `SELECT 1` against `cfg.demo_database_url` via psycopg2 right before fetching the embed URL would have wakened the cluster + made the spike's first capture work.
- M.7 (docs render pipeline) and M.8 (training render pipeline) — both will invoke ScreenshotHarness against deployed dashboards. Both need a built-in warm-up. Don't repeat my debugging time.
- The v5.0.2 e2e test conftest is the reference implementation; lift its warm-up pattern when M.7/M.8 wire screenshot capture into the production CLI.

**Diagnostic lesson for me:** When QuickSight shows a generic "We can't open that dashboard" error, treat **DB connectivity** as the FIRST hypothesis (not the last). Permissions / embed scope / cross-account issues all surface as the same UI text but are far less common than a sleepy backing database.

---
