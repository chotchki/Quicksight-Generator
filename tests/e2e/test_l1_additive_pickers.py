"""AA.A.6 — generic additive-pickers row-survival test for L1 sheets.

Pattern: for each L1 sheet with ≥2 pickers, fetch a known-good anchor
row from the underlying matview, drive every picker to that row's
values *additively*, assert the target visual still renders ≥1 row.

Catches three classes of regression in one test body:

- A picker over-narrows and zeros the table even when matching a
  known anchor row (WHERE clause is wrong column / wrong operator).
- A picker's binding goes stale (e.g. AA.E.2's silent miss — dropdown
  bound to bare ``account_id`` while WHERE expected the display-form
  concat).
- Combined filters compose wrongly (AND vs OR mixup; double-quoted
  literal; etc).

Parametrized over ``[qs, app2]`` via ``l1_dashboard_driver`` so a
parity gap = a real wiring divergence.

Spike resolution (AA.A.6 PLAN entry, locked 2026-05-17): path (1) —
DB-direct anchor query (precedent: ``_daily_statement_pick.py``). The
"intersect-advertised-options" path was rejected as fragile to seed
shape; the "split-into-bespoke" path was rejected because it loses
the generic-coverage benefit that's the whole point of AA.A.6.

v1 scope: Drift + Overdraft (structurally identical: date range +
Account + Account Role pickers + Table target). Daily Statement is
covered by the pre-existing ``test_daily_statement_*`` tests via the
bespoke ``find_account_day_with_data`` helper; not re-wired here.
Follow-on commits will extend ``L1_PICKER_SPECS`` to Limit Breach /
Today's Exceptions / Transactions / Pending Aging / Unbundled Aging
(those need per-sheet picker→column mapping; some have off-table
columns like Today's Exceptions' Check Type that the generic shape
handles via the spec's ``anchor_columns``).
"""

from __future__ import annotations

import pytest

from tests.e2e._picker_anchor import (
    PickerSpec,
    SheetAnchorSpec,
    apply_anchor_to_pickers,
    fetch_anchor_row,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


# Per-sheet picker→column maps. To extend: add a new SheetAnchorSpec
# entry following the same shape — the test body below picks it up
# automatically.
#
# Anchor column choices:
#   - Always include every column referenced by a picker's `column`
#     OR its `format` callable (e.g. account_display needs both
#     account_name + account_id).
#   - `anchor_order` biases the pick: typically `business_day_start
#     DESC` so the anchor lands on a recent day (matches what an
#     analyst sees on open). For sheets where the matview is empty
#     often (zero violations on a fresh seed), the row-survival
#     assertion is meaningful only when the seed actually plants
#     something for that sheet — confirm via ``data apply`` first.
L1_PICKER_SPECS: tuple[SheetAnchorSpec, ...] = (
    SheetAnchorSpec(
        sheet_name="Drift",
        target_visual="Leaf Account Drift",
        anchor_table="{p}_drift",
        anchor_columns=(
            "account_id", "account_name", "account_role", "business_day_start",
        ),
        anchor_order="business_day_start DESC",
        pickers=(
            PickerSpec(
                label="Date From", kind="date_from",
                column="business_day_start",
            ),
            PickerSpec(
                label="Date To", kind="date_to",
                column="business_day_start",
            ),
            PickerSpec(
                label="Account", kind="dropdown", column="account_id",
                format=lambda a: f"{a['account_name']} ({a['account_id']})",
            ),
            PickerSpec(
                label="Account Role", kind="dropdown", column="account_role",
            ),
        ),
    ),
    SheetAnchorSpec(
        sheet_name="Overdraft",
        target_visual="Overdraft Violations",
        anchor_table="{p}_overdraft",
        anchor_columns=(
            "account_id", "account_name", "account_role", "business_day_start",
        ),
        anchor_order="business_day_start DESC",
        pickers=(
            PickerSpec(
                label="Date From", kind="date_from",
                column="business_day_start",
            ),
            PickerSpec(
                label="Date To", kind="date_to",
                column="business_day_start",
            ),
            PickerSpec(
                label="Account", kind="dropdown", column="account_id",
                format=lambda a: f"{a['account_name']} ({a['account_id']})",
            ),
            PickerSpec(
                label="Account Role", kind="dropdown", column="account_role",
            ),
        ),
    ),
)


@pytest.mark.parametrize(
    "spec", L1_PICKER_SPECS, ids=lambda s: s.sheet_name,
)
def test_l1_additive_pickers_keep_anchor_row(
    l1_dashboard_driver, cfg, spec: SheetAnchorSpec,
):
    """For each L1 sheet with ≥2 pickers: fetch a known-good anchor
    row, drive every picker to that row's values, assert the target
    table still has ≥1 row.

    Failure shapes:

    - **Anchor matview empty** → fixture raises ``RuntimeError`` from
      ``fetch_anchor_row``; the matview legitimately has zero rows for
      the sheet's violation kind. Either the seed plants nothing here
      (check ``auto_scenario.py`` + ``TestScenarioCoverage``) or the
      refresh didn't run.

    - **Pre-pick visual empty** → the target table renders zero rows
      before any pick. The matview row exists in the DB but isn't
      reaching the visual — dataset SQL bug, parameter default issue,
      or the universal date filter's default excludes the anchor's day.

    - **Post-pick visual empty** → target had rows pre-pick, anchor
      exists in the matview, but the combined-pick narrowing zeroes
      the table. The smoking gun for AA.A.6's class of regression:
      one of the picker WHERE clauses is wrong (wrong column, wrong
      operator, wrong format expectation — e.g. AA.E.2's
      ``account_id`` vs ``account_display`` miss).
    """
    driver, dashboard_arg = l1_dashboard_driver
    driver.open(dashboard_arg, sheet=spec.sheet_name)
    driver.wait_loaded(spec.target_visual)

    # Snapshot pre-pick so the assertion message can report whether
    # the visual is empty before or after the narrow.
    before = driver.table_rows(spec.target_visual)
    assert len(before) > 0, (
        f"{spec.sheet_name!r}: target visual {spec.target_visual!r} "
        f"empty BEFORE any pick. The matview ({spec.anchor_table}) "
        f"likely has zero rows for the default date window, or the "
        f"dataset SQL filters them out at load. Check the seed + "
        f"matview refresh state."
    )

    anchor = fetch_anchor_row(cfg, spec)
    apply_anchor_to_pickers(driver, spec, anchor)
    driver.wait_loaded(spec.target_visual)
    after = driver.table_rows(spec.target_visual)
    driver.screenshot()

    assert 0 < len(after) <= len(before), (
        f"{spec.sheet_name!r}: anchor row {dict(anchor)!r} should "
        f"survive the all-pickers-narrowed-to-anchor state. Got "
        f"{len(after)} rows (was {len(before)} pre-pick). One of the "
        f"picker WHERE clauses is wrong column / wrong operator / "
        f"wrong value format — drill into the failure capture's "
        f"network.txt to see which dataset SQL came back empty."
    )
