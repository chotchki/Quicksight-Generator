# PLAN — Filter-propagation browser e2e expansion

Goal: prove every filter on every sheet narrows every dependent visual the way a user would expect. Today the browser e2e suite only spot-checks the date-range filter on one table per app; everything else is structural (the filter is wired up in the dashboard JSON) without confirming the data actually moves.

Out of scope: the QuickSight "filter stacking on navigation" UX wart — when a user drills A → B → A, parameter filters set during the first navigation can linger and produce confusing counts. We've checked: there is no toggle in QuickSight's parameter / filter API that auto-clears these. **Document the behavior, do not try to fix it.** Phase 5 covers the doc work.

Conventions:
- Branch off `main`; one phase = one commit + one tag bump (`v1.1.x` per phase, `v1.1.0` cumulative on the merge).
- Every new test must be runnable in isolation — no implicit ordering with other filter tests in the same module (each test loads its own embed URL, embed URLs are single-use).
- After each phase, run the full unit suite + the new-or-touched browser tests. Full e2e (`./run_e2e.sh`) before tagging.
- Helpers go in `tests/e2e/browser_helpers.py` or a new sibling — never copy DOM-poking JS between test files.

## Carried-forward assumptions

- Demo data is deterministic (`random.Random(42)`) so we can hard-code expected before/after row counts when scenario coverage guarantees them. Where exact counts feel brittle, prefer "drops by ≥ N" or "drops to 0" assertions over equality.
- Multi-select dropdowns and SINGLE_SELECT toggles are reachable via `[data-automation-id="sheet_control_name"]` plus the dropdown's value list; the existing `_sheet_control_titles` helper finds the labels but we'll need a new helper to actually set a value.
- Cross-sheet filters (date-range, parent-account, child-account, transfer-type) are scoped via `CrossSheet` controls — the same source filter ID drives every tab. Setting once should propagate; we verify on each scoped tab.
- Navigation-induced filter stacking is observed and reproducible but **not fixable** within QuickSight's API surface (confirmed during v1.0.0 testing). Phase 5 captures it as a known limitation.

---

## Phase 1 — Filter-interaction helpers

Build the building blocks once; every later phase consumes them.

- [x] 1.1 Add `set_dropdown_value(page, control_title, value, timeout_ms)` to `browser_helpers.py`. Locates the FilterControl by its visible title (`sheet_control_name`), opens the dropdown, clicks the option whose text equals `value`, waits for the control's displayed selection to update.
- [x] 1.2 Add `set_multi_select_values(page, control_title, values, timeout_ms)` — same pattern, but tolerates multiple checked entries; deselects whatever's currently selected first so tests start from a clean state.
- [x] 1.3 Add `clear_dropdown(page, control_title, timeout_ms)` — picks the "All values" / blank entry so a multi-step test can reset between checks.
- [x] 1.4 Generalize the two existing date-range helpers (`_set_date` in `test_filters.py` and `test_ar_filters.py`) into `set_date_range(page, start, end, timeout_ms)` in the helpers module. Delete the per-file copies as part of 1.4.
- [x] 1.5 Add `count_table_rows(page, visual_title)` and `count_chart_categories(page, visual_title)` helpers. Both currently live as one-off `page.evaluate` blocks duplicated across filter / drilldown / mutual-filter tests — consolidate.
- [x] 1.6 Add `wait_for_table_rows_to_change(page, visual_title, before, timeout_ms)` — polls `count_table_rows` for the value to differ from `before`. Replaces the inline `page.wait_for_function` blocks. Returns the new count. (Renamed from `wait_for_visual_to_change` since chart-category change polling wasn't needed yet — add later if Phase 2 turns out to need it.)
- [x] 1.7 Smoke-checked helpers against the live AR Transfers tab — `set_multi_select_values("Transfer Status", ["not_net_zero"])` correctly narrows the Transfer Summary table. Smoke + debug test files deleted.
- [x] 1.8 Commit — `Phase 1: filter-interaction browser helpers`.

**Notes from Phase 1 implementation:**
- QS sheet controls live under `[data-automation-id="sheet_control"][data-automation-context="<Title>"]`. The value picker is `[data-automation-id="sheet_control_value"]` (a Material-UI Select combobox). The kebab-menu button (`sheet_control_menu_button`) is *not* the dropdown trigger — clicking it opens an "Options" menu (Reset/Edit), not the value list.
- Multi-select listbox options reorder on toggle, so the deselect-then-select loop snapshots labels first via JS evaluate, then clicks by `has_text=label` rather than by index.
- Dropdowns mount in a portal at the document root; `[role="listbox"] [role="option"]` is the right scoping selector.

**STOP** — review helper signatures before any tests are written against them, since the API will be hard to change after 5+ tests use it.

---

## Phase 1.5 — Pagination-aware row counting

Today's `count_table_rows` counts cells in the DOM, which for QS tables with more than ~30-50 rows is only the visible virtualization window, not the true filter result size. A filter that narrows 200 → 80 rows would show no change under our current helper, passing while the real assertion goes untested. Demo data is small enough that every table currently fits in one window, so the bug hides by accident.

Fix before Phase 2 writes any filter-narrowing test against a table larger than a viewport.

- [ ] 1.5.1 Grow demo data so at least one PR table and one AR table exceed the QS virtualization threshold (~50 rows rendered). Target: Sales detail grows from ~48 to ~120 rows by stretching `_DAYS_OF_HISTORY` in `payment_recon/demo_data.py`; AR Transactions detail grows to ~250 rows by doubling `_SUCCESSFUL_CROSS_SCOPE` / `_SUCCESSFUL_INTERNAL_INTERNAL`. Update the scenario coverage tests in `test_demo_data.py` and any hard-coded count assertions.
- [ ] 1.5.2 Deploy the expanded demo. Write a throwaway debug test (like the Phase 1 debug file) that dumps the DOM region around a virtualized table's footer — the goal is to find the automation-id / class for the "X-Y of Z" indicator. Candidates to look for: `data-automation-id="visual_count_label"`, a `pagination` class, or an aria-label like "Pagination: rows X through Y of Z".
- [ ] 1.5.3 Add `count_table_total_rows(page, visual_title)` to `browser_helpers.py`. Reads the pagination indicator text, parses the total, returns it. Raises a clear error if no indicator is found (so callers notice when a small table has no pagination UI and fall back to `count_table_rows` explicitly).
- [ ] 1.5.4 Add `wait_for_table_total_rows_to_change(page, visual_title, before, timeout_ms)` that polls the pagination indicator rather than DOM cells. Mirrors the existing `wait_for_table_rows_to_change` shape.
- [ ] 1.5.5 Decision point — two helpers or one? Tables with few rows (< viewport) don't render a pagination indicator, so the total-rows helper has to either error or fall through to DOM count. Settle in 1.5.3: prefer "explicit is better — two helpers, caller picks". Document the rule in CLAUDE.md's E2E Test Conventions.
- [ ] 1.5.6 Update the 3 existing refactored tests (`test_filters.py`, `test_ar_filters.py`, `test_recon_mutual_filter.py`) to use `count_table_total_rows` where the target table now paginates. Verify green against the live dashboard.
- [ ] 1.5.7 Commit — `Phase 1.5: pagination-aware row counting`.

**STOP** — if 1.5.2 fails to find a pagination indicator (e.g., QS uses pure virtualization without a visible count), escalate: either find a way to scroll-and-accumulate the total, or revisit whether this matters for the filter assertions Phase 2/3 actually make (inequalities may still hold — a filter that drops below viewport *will* show DOM-count change). The answer affects whether Phase 2 needs a different assertion pattern entirely.

---

## Phase 2 — Payment Recon filter coverage

Walk every PR filter and verify the visuals it claims to scope. Each `[ ]` is one new test (or one parametrize case).

### Date-range filter (sheets: Sales Overview, Settlements, Payments, Payment Reconciliation, Exceptions, Getting Started — verify scope per-tab)

- [ ] 2.1 On each pipeline sheet, push date range to a future window; assert every table on the sheet drops to 0 (or below the pre-filter count). Parametrized: one test, N sheets.
- [ ] 2.2 Push date range to a *past* window with no demo data; same assertion. Catches one-sided range bugs.
- [ ] 2.3 Set date range to the demo's known active window (Feb–Mar 2026 for the seed); confirm Settlements detail row count matches the seeded settlement count from `test_demo_data.py`'s scenario coverage.

### Optional-metadata filters (Sales Overview only)

- [ ] 2.4 Numeric filter (taxes / tips slider) — drag to top of range; assert Sales Detail rows drop and the by-merchant bar chart's category count shrinks. Mirror with a bottom-of-range case.
- [ ] 2.5 String filter (cashier multi-select) — pick one cashier; assert KPI sums drop and detail table only shows rows for that cashier (sample 3 random cells, confirm cashier column matches).
- [ ] 2.6 Discount-percentage range — same shape as 2.4.

### Payment-method filter (sheets: Settlements, Payments)

- [ ] 2.7 On Settlements, multi-select a single method; assert by-merchant-type bar chart re-renders, settlements table shrinks. Then switch to Payments tab without changing the filter and assert Payments tables also shrink (cross-sheet propagation).

### Days-outstanding slider — *removed in v0.4.0* per RELEASE_NOTES

- [ ] 2.8 Confirm via DOM that no "days outstanding" control is present on any pipeline tab. Belt-and-braces against regression.

### Show-Only-X toggles (Sales / Settlements / Payments)

- [ ] 2.9 Toggle "Show Only Unsettled" on Sales — assert Sales Detail row count equals the count of un-settled sales in the demo (from existing scenario assertions); assert by-merchant bar chart's bars are a subset of pre-toggle bars.
- [ ] 2.10 Toggle "Show Only Unpaid" on Settlements — same shape.
- [ ] 2.11 Toggle "Show Only Unmatched Externally" on Payments — same shape.
- [ ] 2.12 Toggle each, then *clear* it, and assert the row count returns to the pre-toggle baseline. Catches sticky-filter bugs.

### Same-sheet chart-click filtering

- [ ] 2.13 Click a bar in the by-merchant chart on Sales Overview; assert Sales Detail filters to that merchant only. Mirror for Settlements (by-merchant-type) and Payments (status pie slice).
- [ ] 2.14 Click a *second* bar (different category) — assert the table updates to the new selection (not "merchant A AND merchant B").

### Payment Reconciliation tab (mutual filter — already partially covered)

- [ ] 2.15 The existing `test_recon_mutual_filter.py` only covers external-row → payments-table direction. Add the reverse: click an Internal Payment row, assert the External Transactions table narrows to the linked transaction. Use `scroll_visual_into_view` since the payments table is below the fold post-swap.
- [ ] 2.16 Click the bar chart's status segment; assert *both* tables filter (the chart action targets both visual IDs).

- [ ] 2.17 Commit — `Phase 2: PR filter-propagation browser e2e`. Tag `v1.1.0-rc1` or just hold to the cumulative `v1.1.0`.

**STOP** — run the new suite end-to-end; if any assertion is brittle (intermittent row-count timing) reformulate before AR work uses the same shape.

---

## Phase 3 — Account Recon filter coverage

Same shape as Phase 2; AR has more cross-sheet filter scope so order matters.

### Date-range (sheets: Balances, Transfers, Transactions, Exceptions)

- [ ] 3.1 Future window — every detail table on every tab drops to 0. Parametrized.
- [ ] 3.2 Demo-active window — Transaction Detail row count matches the seed transaction count.

### Parent-account multi-select (cross-tab — Balances, Transfers, Transactions, Exceptions)

- [ ] 3.3 Pick one parent on Balances tab; assert child accounts table shows only that parent's children. Switch to Transactions; assert transaction table is filtered to the same parent's accounts (verify by sampling rows).
- [ ] 3.4 Switch to Exceptions; assert the parent-drift timeline (or table) only shows that parent.

### Child-account multi-select (cross-tab)

- [ ] 3.5 Pick one child; assert Transactions tab filters to that child. Confirm Balances tab's child table also reduces.
- [ ] 3.6 Combine parent + child filters; verify intersection (not union) on Transactions.

### Transfer-type multi-select (cross-tab — Transfers, Transactions, Exceptions)

- [ ] 3.7 Pick "ach" only; assert Transfers summary table only shows ach transfers; Transactions tab shrinks; Exceptions limit-breach table only shows ach breaches.

### Transfer-status multi-select (Transfers tab only — single-dataset scope)

- [ ] 3.8 Pick "not_net_zero"; assert Transfers summary table = the non-zero count. Confirms our v1.0.1 toggle removal didn't break the underlying multi-select.
- [ ] 3.9 Pick "net_zero"; confirm fully-failed transfers (net=0, all legs failed) appear here — proves the v1.0.1 user concern is addressed at the data level.

### Show-Only-X toggles (Balances, Transactions)

- [ ] 3.10 Toggle each of the four remaining toggles ("Show Only Parent Drift", "Show Only Child Drift", "Show Only Overdraft", "Show Only Failed"); assert table narrows; clear; assert it returns.
- [ ] 3.11 DOM-check that the Transfers tab has *no* SINGLE_SELECT toggle (regression guard for v1.0.1).

### Same-sheet chart-click filtering

- [ ] 3.12 Click a bar in the AR transfer-status chart; assert summary table narrows to that status.
- [ ] 3.13 Click a parent-drift point in the Exceptions timeline; assert the parent-drift table below filters to that parent (if action exists; check `analysis.py` and skip with a marker if not wired).

- [ ] 3.14 Commit — `Phase 3: AR filter-propagation browser e2e`.

**STOP** — review intermittency. AR has 5 toggles + 4 cross-sheet filters; if test runtime balloons past ~5 minutes, split the test file along sheet boundaries.

---

## Phase 4 — Cross-cutting interactions

Filter behavior that crosses the seams between filters, drill-downs, and tabs.

- [ ] 4.1 Set date range on Sales; click a row to drill into Settlements; confirm date range *and* drill-down filter both apply on the destination sheet (intersection, not last-write-wins).
- [ ] 4.2 Apply Show-Only-Unpaid on Settlements; drill a row into Sales; confirm the destination sheet receives the parameter filter and the source-sheet toggle does not "leak" (toggles are SINGLE_DATASET scoped — verify that contract holds end-to-end).
- [ ] 4.3 Same shape on AR: set parent filter, drill from Balances to Transactions, confirm intersection.

- [ ] 4.4 Commit — `Phase 4: cross-cutting filter + drilldown interactions`.

---

## Phase 5 — Document the navigation filter-stacking caveat

Navigation-driven parameter filters can stack across drill-downs (A → B → A leaves a B-derived filter on A). QuickSight has no API to clear a parameter on tab-switch.

- [ ] 5.1 Reproduce the stacking under test: drill PR Sales → Settlements (sets `pSaleSettlementId`) → click the cross-sheet date filter and return to Sales; assert (or just screenshot for evidence) that the previous parameter is still set. This becomes a *characterization* test, not a failure — mark it `xfail(strict=False)` with a reason citing the limitation.
- [ ] 5.2 Add a new "Known Limitations" section to README.md describing the stacking behavior and the workaround (refresh the dashboard tab).
- [ ] 5.3 Add the same caveat to both Getting Started sheets via `common/rich_text.py` — a single bullet under the clickability legend, accent-colored. Update `test_demo_data.py` / generate tests if any "expected text" assertions need to grow.

- [ ] 5.4 Commit — `Phase 5: document QS navigation filter-stacking limitation`.

---

## Phase 6 — Suite-runtime budget + parallelism

After Phases 2–4 the browser suite will roughly triple in size. Make sure `./run_e2e.sh` stays under the team's tolerance (~5 min today, target ≤ 10 min after expansion).

- [ ] 6.1 Time the new suite. If > 10 min, mark the slowest 1/3 of tests with `@pytest.mark.slow` and let `./run_e2e.sh` skip them by default; add `--full` flag to include.
- [ ] 6.2 Investigate `pytest-xdist` for parallel browser sessions (each test already creates an isolated `webkit_page`, but embed URL fixtures are function-scoped and single-use — should be safe to parallelize at file granularity).
- [ ] 6.3 If 6.2 lands, document the `-n auto` flag in `run_e2e.sh --help` text and CLAUDE.md.

- [ ] 6.4 Commit — `Phase 6: e2e suite runtime budget`.

---

## Phase 7 — Release v1.1.0

- [ ] 7.1 Update RELEASE_NOTES.md — one entry covering all phases. Stats: count of new tests, runtime delta, filter coverage matrix.
- [ ] 7.2 Update CLAUDE.md "E2E Test Conventions" with the new helpers and the slow-test marker convention.
- [ ] 7.3 Tag `v1.1.0`, push branch, push tag, fast-forward main.

---

## Decisions to make in flight (will resolve as we go)

- **How to test multi-select dropdowns reliably.** QuickSight's dropdowns animate; the DOM may show options before they're clickable. If `set_multi_select_values` is flaky we may need an explicit "wait for options menu open" sub-helper. Decide during Phase 1.
- **Hard-coded counts vs. inequality assertions.** Demo data is deterministic, but plant counts can shift if anyone tweaks `demo_data.py`. Prefer inequalities (`< before`, `== 0`) where the test reads naturally; reserve equality for the handful of cases where the count is the point (e.g., "Show Only Unpaid" should equal `_OFF_AMOUNT_TRANSFERS + _FAILED_LEG_TRANSFERS`).
- **Parametrize granularity.** Some sheets share filter shapes (date-range across all four AR tabs). Lean on `pytest.mark.parametrize` per filter+sheet pair so failures pinpoint which combination broke; resist combining into a single multi-sheet loop.
- **Screenshot policy.** Today, only filter tests screenshot. With 30+ new tests, screenshots could explode — only screenshot on the *clearing* assertion (the easy-to-eyeball "should be 0 rows" state) per filter, not every step.
