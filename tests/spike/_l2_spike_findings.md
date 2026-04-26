# Phase M.0 — vertical-slice spike findings

Notes captured during M.0 to inform M.1 library design + SPEC amendments. This file is updated as findings surface throughout M.0.x; it's reviewed and consolidated at the M.0.13 iteration gate.

Format per entry: surface point (which substep), observation, implication for SPEC, implication for M.1 library.

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

## F7 — `ScreenshotHarness` lives under `tests/e2e/` but is needed by production code

**Surfaced:** M.0.8 (writing `capture_drift_screenshot`)

**Observation:** `ScreenshotHarness` was built in L.1.10.7 as test infrastructure under `tests/e2e/screenshot_harness.py`. The `generate training` CLI command needs to invoke it during normal user workflow (rendering handbook pages with embedded screenshots), which means production code now imports from `tests/`. That import path is wrong — `tests/` is conventionally not part of the package surface.

**Implication for SPEC:** No change.

**Implication for M.1:**
- Promote `ScreenshotHarness` (and its supporting `browser_helpers` module) from `tests/e2e/` to `common/screenshot/` (or similar public-surface path).
- Existing test imports update to point at the new location.
- Playwright stays an optional dependency (`[e2e]` extra); the production module gracefully reports when it's not installed.

---

## F8 — Sheet has TWO IDs the spike reasoned about: `sheet_id` (URL-stable) and visual screenshot filenames

**Surfaced:** M.0.6 + M.0.8 (sheet construction + screenshot wiring)

**Observation:** The `Sheet` constructor takes `sheet_id` (an explicit, URL-stable identifier) plus auto-derived internal IDs. `ScreenshotHarness.capture_all_sheets()` returns `dict[sheet_id_str, Path]` keyed by the explicit sheet_id, with PNG filenames `<sheet_id>.png`. Lookups by sheet name would feel more natural for "I want the drift sheet's PNG" but require the harness to know about names; keying by sheet_id is more robust but forces callers to remember the explicit ID strings.

**Implication for SPEC:** No SPEC change — internal API design.

**Implication for M.1:**
- Consider extending the harness with `capture_by_name()` or returning `dict[Sheet, Path]` (object refs) so callers can lookup by Sheet node.
- Documentation should be clear that handbook templates referencing screenshots cite by `sheet_id` filename, not by name.

---
