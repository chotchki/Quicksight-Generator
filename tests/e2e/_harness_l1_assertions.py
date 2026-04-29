"""L1-dashboard Playwright assertions for the M.4.1 harness (M.4.1.d).

Per-plant-kind assertions that navigate the deployed L1 dashboard
to the right sheet and verify the planted row surfaces. Takes a
loaded Playwright Page (already on the L1 embed URL) + the
planted_manifest from M.4.1.b.

Per the M.4.1.d PLAN entry:
  - DriftPlant → Drift sheet shows account_id + delta_money
  - OverdraftPlant → Overdraft sheet shows account_id
  - LimitBreachPlant → Limit Breach sheet shows account_id +
    transfer_type
  - StuckPendingPlant → Pending Aging sheet shows the planted leg
  - StuckUnbundledPlant → Unbundled Aging sheet shows the planted leg
  - SupersessionPlant → Supersession Audit sheet shows the corrected
    pair
  - Today's Exceptions KPI count == sum of planted L1 SHOULD-violation
    scenarios

First-cut assertion strategy: rather than reading specific table
cells (cell selectors are brittle to QS table virtualization), do a
sheet-text substring check. The planted ``account_id`` strings are
unique enough per (rail, day, count) that finding them in the
sheet's rendered text is a reliable visibility proof. Tighter cell-
level assertions can layer on later as M.4.1.d-followups when QS
table reading proves stable.

Why this is a separate module: the dispatch logic (plant-kind →
sheet name) is testable without a live browser. The actual
assertion bodies need a Playwright Page so they only run inside the
harness test.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any


# Plant kind → L1 dashboard sheet name. Drives the dispatch in
# ``assert_l1_plants_visible``. Plant kinds NOT in this map (e.g.
# transfer_template_plants, rail_firing_plants) are L2 Flow Tracing
# concerns — handled by ``_harness_l2ft_assertions.py`` (M.4.1.e).
L1_SHEET_FOR_PLANT_KIND: dict[str, str] = {
    "drift_plants": "Drift",
    "overdraft_plants": "Overdraft",
    "limit_breach_plants": "Limit Breach",
    "stuck_pending_plants": "Pending Aging",
    "stuck_unbundled_plants": "Unbundled Aging",
    "supersession_plants": "Supersession Audit",
}


# Plant kind → L1 invariant matview name (no prefix). Drives the
# fast pre-render assertion that confirms the seed → matview
# pipeline landed each planted scenario as a queryable row.
# Decoupled from the sheet-name dispatch: the matview names mirror
# the schema.py CREATE MATERIALIZED VIEW names exactly, while the
# sheet names are the human-readable dashboard labels.
#
# Supersession is intentionally absent — supersession isn't its own
# matview; it's a property of multiple `entry` rows in `transactions`
# for the same `id`. The dashboard's Supersession Audit sheet derives
# from a per-dashboard view, not a planted-violation matview. Defer
# the supersession matview check to a follow-up if the audit sheet
# starts losing rows.
L1_MATVIEW_FOR_PLANT_KIND: dict[str, str] = {
    "drift_plants": "drift",
    "overdraft_plants": "overdraft",
    "limit_breach_plants": "limit_breach",
    "stuck_pending_plants": "stuck_pending",
    "stuck_unbundled_plants": "stuck_unbundled",
}


# Plant kinds that contribute to Today's Exceptions KPI count.
# Supersession is diagnostic, not a SHOULD-violation, so excluded.
L1_SHOULD_VIOLATION_PLANT_KINDS: frozenset[str] = frozenset({
    "drift_plants",
    "overdraft_plants",
    "limit_breach_plants",
    "stuck_pending_plants",
    "stuck_unbundled_plants",
})


def expected_todays_exceptions_kpi_count(
    planted_manifest: dict[str, list[dict[str, Any]]],
) -> int:
    """Sum of every L1 SHOULD-violation plant kind in the manifest.

    The L1 dashboard's Today's Exceptions sheet has a KPI showing
    the total open violation count. Per the M.4.1.d contract, this
    KPI MUST equal the sum of planted SHOULD-violation scenarios
    (drift + overdraft + limit_breach + stuck_pending + stuck_unbundled).
    Supersession isn't a SHOULD-violation; transfer_template /
    rail_firing aren't L1 plants — neither contributes.
    """
    return sum(
        len(planted_manifest.get(kind, []))
        for kind in L1_SHOULD_VIOLATION_PLANT_KINDS
    )


def assert_l1_matview_rows_present(
    db_conn: Any,
    prefix: str,
    planted_manifest: dict[str, list[dict[str, Any]]],
) -> None:
    """For every L1 plant kind in the manifest, query the prefixed
    invariant matview directly and assert the planted ``account_id``
    surfaces as a row.

    **The fast-fail layer of the harness (M.4.1.k)**. Catches seed →
    matview-refresh pipeline regressions in <1s per query, BEFORE
    we open Playwright. If this assertion fails, the dashboard render
    check would also fail — but the matview-side error message points
    straight at the seed/matview layer, not the dashboard layer.
    The dashboard render check is the SECONDARY layer; it catches
    bugs that survive the matview check (dataset SQL filters,
    visual config, dashboard-side date filter, QS rendering quirks).

    Pattern matches the established "verify the lower layer first"
    diagnostic ladder from CLAUDE.md (psycopg2 → describe_data_set →
    dashboard render — narrowest blame radius first).

    Args:
        db_conn: psycopg2 connection to the demo Aurora cluster.
        prefix: per-test L2 instance prefix (matches what
            ``apply_db_seed`` used).
        planted_manifest: ``build_planted_manifest`` output from
            M.4.1.b — keyed by plant kind.

    Raises:
        AssertionError: on the first planted plant whose ``account_id``
            doesn't appear in its expected matview, with the matview
            name + plant + row count for triage.
    """
    for kind, matview in L1_MATVIEW_FOR_PLANT_KIND.items():
        plants = planted_manifest.get(kind, [])
        if not plants:
            continue
        full_view = f"{prefix}_{matview}"
        for plant in plants:
            account_id = plant.get("account_id")
            assert account_id is not None, (
                f"plant {plant!r} in kind {kind!r} has no account_id; "
                f"can't verify against matview {full_view!r}"
            )
            with db_conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) FROM {full_view} WHERE account_id = %s",
                    (account_id,),
                )
                row = cur.fetchone()
                count = row[0] if row else 0
                cur.execute(f"SELECT COUNT(*) FROM {full_view}")
                total_row = cur.fetchone()
                total = total_row[0] if total_row else 0
            assert count > 0, (
                f"L1 invariant matview {full_view!r} has no row for "
                f"planted {kind} account_id={account_id!r} — seed→"
                f"matview-refresh pipeline regression. Total rows in "
                f"the matview: {total}.\n"
                f"plant: {plant!r}"
            )


def widen_l1_date_range(
    page: Any,
    *,
    today: date,
    days_back: int = 30,
    timeout_ms: int = 30_000,
) -> None:
    """Set the L1 dashboard's universal date filter wide enough to
    span every planted scenario, BEFORE the visibility assertions run.

    Why: ``apply_db_seed`` anchors plants to ``DEFAULT_HARNESS_TODAY``
    (date(2030, 1, 1)) so the seed hash is deterministic across runs.
    The L1 dashboard's universal date-range filter (M.2b.1) defaults
    to a rolling 7-day window ending at the dashboard's "now" — which
    is the actual current wall-clock date, NOT the harness's pinned
    today. The plants therefore sit several years outside the default
    window and every visibility check trivially fails.

    Setting the filter on ONE sheet propagates to all data-bearing
    sheets (the params are analysis-level — see M.2b.1 in app.py),
    so we only navigate once. We pick "Drift" because it's the first
    data-bearing sheet that always exists for any L2 instance with
    a TwoLegRail.

    Args:
        page: loaded Playwright Page on the L1 dashboard.
        today: the same ``today`` ``apply_db_seed`` used (typically
            ``DEFAULT_HARNESS_TODAY``). Plants land at this anchor
            minus their ``days_ago``; setting the filter window to
            end at this date ensures they all fall inside.
        days_back: width of the window. Default 30 covers all current
            plant kinds (max ``days_ago`` is ~7); leaves headroom for
            future fixture changes.
        timeout_ms: per-step picker wait timeout.
    """
    from quicksight_gen.common.browser.helpers import (
        click_sheet_tab,
        set_parameter_datetime_value,
    )

    click_sheet_tab(page, "Drift", timeout_ms=timeout_ms)
    start = today - timedelta(days=days_back)
    end = today
    set_parameter_datetime_value(
        page, "Date From", start.strftime("%Y/%m/%d"),
        timeout_ms=timeout_ms,
    )
    set_parameter_datetime_value(
        page, "Date To", end.strftime("%Y/%m/%d"),
        timeout_ms=timeout_ms,
    )
    # Give QS a beat to propagate the param change + re-query visuals.
    # The set_parameter_datetime_value helper waits for the input but
    # not for the downstream visual rerender.
    page.wait_for_timeout(2000)


def assert_l1_plants_visible(
    page: Any,
    planted_manifest: dict[str, list[dict[str, Any]]],
    *,
    timeout_ms: int = 30_000,
) -> None:
    """Walk every plant kind in the manifest; assert each plant's
    account_id surfaces on its expected L1 sheet.

    ``page`` MUST already be on the L1 dashboard embed URL with the
    initial dashboard load complete (caller calls
    ``wait_for_dashboard_loaded`` before invoking this helper).

    Raises ``AssertionError`` with the offending plant + sheet name
    on the first miss. M.4.1.f's failure manifest dump can re-iterate
    the manifest from the raised exception's context.

    Sheets that have no planted rows (the manifest entry is empty)
    are skipped — no need to navigate to a sheet that has nothing
    to assert.
    """
    from quicksight_gen.common.browser.helpers import click_sheet_tab

    for kind, sheet_name in L1_SHEET_FOR_PLANT_KIND.items():
        plants = planted_manifest.get(kind, [])
        if not plants:
            continue
        click_sheet_tab(page, sheet_name, timeout_ms=timeout_ms)
        sheet_text = _active_sheet_text(page, timeout_ms=timeout_ms)
        for plant in plants:
            account_id = plant.get("account_id")
            assert account_id is not None, (
                f"plant {plant!r} in kind {kind!r} has no account_id; "
                f"can't verify on {sheet_name!r}"
            )
            assert account_id in sheet_text, (
                f"L1 sheet {sheet_name!r} doesn't show planted {kind} "
                f"account_id={account_id!r}; expected the row to be "
                f"visible after the seed + matview refresh\n"
                f"plant: {plant!r}"
            )


def assert_todays_exceptions_kpi_matches(
    page: Any,
    planted_manifest: dict[str, list[dict[str, Any]]],
    *,
    timeout_ms: int = 30_000,
) -> None:
    """Today's Exceptions KPI count == sum of planted SHOULD-violation
    scenarios. Plant kinds excluded from the rollup (supersession,
    TT, rail-firing) don't contribute.

    Reads the KPI's text content via the existing
    ``wait_for_kpi_text_nonempty`` helper, parses out the number,
    compares to ``expected_todays_exceptions_kpi_count``.
    """
    from quicksight_gen.common.browser.helpers import (
        click_sheet_tab,
        wait_for_kpi_text_nonempty,
    )

    expected = expected_todays_exceptions_kpi_count(planted_manifest)
    click_sheet_tab(page, "Today's Exceptions", timeout_ms=timeout_ms)
    # KPI title on the L1 dashboard's Today's Exceptions sheet.
    kpi_title = "Open Exceptions Today"
    actual_text = wait_for_kpi_text_nonempty(
        page, kpi_title, timeout_ms=timeout_ms,
    )
    # KPI text typically renders as just the integer (no commas at
    # this scale); parse defensively.
    actual_clean = (
        actual_text.replace(",", "").strip()
    )
    try:
        actual = int(actual_clean)
    except ValueError as exc:
        raise AssertionError(
            f"Today's Exceptions KPI {kpi_title!r} text {actual_text!r} "
            f"isn't parseable as an integer"
        ) from exc
    assert actual == expected, (
        f"Today's Exceptions KPI {kpi_title!r}: expected {expected} "
        f"(sum of planted L1 SHOULD-violations across drift / "
        f"overdraft / limit_breach / stuck_pending / stuck_unbundled), "
        f"got {actual}"
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _active_sheet_text(page: Any, *, timeout_ms: int) -> str:
    """Return the rendered text of the currently active sheet.

    Uses the QS dashboard's analysis container (the parent of every
    visual on the active sheet) so tab labels + sheet controls
    aren't included — purely the sheet body content.

    Falls back to the whole page body if the analysis container
    selector doesn't match (older QS builds, embedded variants).
    """
    from quicksight_gen.common.browser.helpers import (
        wait_for_table_cells_present,
    )

    # Make sure the sheet's tables have hydrated before reading text.
    try:
        wait_for_table_cells_present(page, timeout_ms=timeout_ms)
    except Exception:  # noqa: BLE001 — tables may not exist on every sheet
        pass
    el = page.query_selector('[data-automation-id="analysis_visual"]')
    if el is None:
        return page.text_content("body") or ""
    # Read text from EVERY visual on the sheet, not just the first
    # — different plant kinds may surface in different visuals.
    visuals = page.query_selector_all(
        '[data-automation-id="analysis_visual"]'
    )
    return "\n".join(v.inner_text() for v in visuals)
