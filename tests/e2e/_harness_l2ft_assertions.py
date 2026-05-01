"""L2 Flow Tracing Playwright assertions for the M.4.1 harness (M.4.1.e).


Mirrors the M.4.1.d L1 assertion module but for the L2 Flow Tracing
dashboard's surfaces. Per the M.4.1.e PLAN entry:

  - Rails sheet: ≥1 row per declared rail that the broad-mode
    scenario fires (every rail in rail_firing_plants with
    transfer_parent_id is None — chain-child plants use the same
    rail_name and would double-count).
  - Transfer Templates sheet: per planted TT firing, the
    template_name appears.
  - L2 Exceptions sheet: the KPI renders an integer
    (sanity check that the unified dataset rendered against
    the per-test prefix).

P.9f.f — The plant-visibility assertion is a Layer-1 DB query
against ``<prefix>_current_transactions``, NOT a sheet-text scrape.
Earlier versions of this module text-scraped the Rails sheet and
matched plant rail_names as substrings, but with sasquatch_pr's
57+ standalone rail firings on a single Rails sheet, QS's table
virtualization (~10 rows in DOM regardless of page size — see
CLAUDE.md "E2E Test Conventions") guaranteed plants below the fold
were invisible to the assertion. The Layer-1 matview query is
deterministic, fast (~5 ms per plant), and points at the
seed/matview pipeline if it fails — same diagnostic ladder L1
established in M.4.1.k. The L2 Exceptions KPI render
(``assert_l2_exceptions_kpi_renders``) remains the dashboard-side
smoke that proves the L2FT dataset SQL ran cleanly.

The 6 L2 Exceptions check_type categories are pinned constants
(they're CAST literals in the unified-exceptions dataset SQL —
see ``apps/l2_flow_tracing/datasets.py::build_unified_l2_exceptions_dataset``).
"""

from __future__ import annotations

from typing import Any

from quicksight_gen.common.sql import Dialect


# Plant kind → L2 Flow Tracing dashboard sheet name. The dispatch
# only covers L2-side kinds; L1 kinds are M.4.1.d's responsibility
# (handled by ``_harness_l1_assertions.L1_SHEET_FOR_PLANT_KIND``).
L2FT_SHEET_FOR_PLANT_KIND: dict[str, str] = {
    "rail_firing_plants": "Rails",
    "transfer_template_plants": "Transfer Templates",
}


# The 6 L2 hygiene check_type discriminator values the unified
# exceptions dataset emits (CAST literals in the UNION ALL branches
# of ``apps/l2_flow_tracing/datasets.py::build_unified_l2_exceptions_dataset``).
# Pinned here so the L2 Exceptions sanity assertion catches drift
# if a check_type label gets renamed without updating downstream
# expectations.
L2_EXCEPTION_CHECK_TYPES: frozenset[str] = frozenset({
    "Chain Orphans",
    "Unmatched Transfer Type",
    "Dead Rails",
    "Dead Bundles Activity",
    "Dead Metadata Declarations",
    "Dead Limit Schedules",
})


def assert_l2ft_matview_rows_present(
    db_conn: Any,
    prefix: str,
    planted_manifest: dict[str, list[dict[str, Any]]],
    *,
    dialect: Dialect = Dialect.POSTGRES,
) -> None:
    """For every L2 plant in the manifest, query
    ``<prefix>_current_transactions`` directly and assert the planted
    ``rail_name`` / ``template_name`` surfaces as ≥1 row.

    Mirrors ``_harness_l1_assertions.assert_l1_matview_rows_present``
    in shape + intent. Layer-1 fast-fail check that runs in <50ms
    per plant and points at the seed→matview-refresh pipeline if it
    fails. Replaces the earlier sheet-text-scrape check
    (``assert_l2ft_plants_visible``) which broke on sasquatch_pr
    where 57+ standalone rail firings on the Rails sheet pushed all
    but the first ~10 alphabetically-earliest below QS's
    virtualization fold (P.9f.f).

    For ``rail_firing_plants`` with ``transfer_parent_id IS NULL``:
    counts rows by ``rail_name``. Chain-child plants are skipped —
    they reuse the same rail_name as the standalone firing.

    For ``transfer_template_plants``: counts rows by ``template_name``.

    Args:
        db_conn: psycopg2 / oracledb connection to the demo DB.
        prefix: per-test L2 instance prefix (matches what
            ``apply_db_seed`` used).
        planted_manifest: ``build_planted_manifest`` output —
            keyed by plant kind.
        dialect: per-dialect placeholder syntax (``%s`` vs ``:1``).

    Raises:
        AssertionError on the first plant whose rail_name /
            template_name doesn't appear, with the matview name +
            plant + total-rows-in-matview for triage.
    """
    placeholder = ":1" if dialect is Dialect.ORACLE else "%s"
    full_view = f"{prefix}_current_transactions"

    rail_plants = [
        p for p in planted_manifest.get("rail_firing_plants", [])
        if p.get("transfer_parent_id") is None
    ]
    for plant in rail_plants:
        rail_name = plant.get("rail_name")
        assert rail_name is not None, (
            f"rail plant {plant!r} missing rail_name; can't verify"
        )
        with db_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {full_view} "
                f"WHERE rail_name = {placeholder}",
                (rail_name,),
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            cur.execute(f"SELECT COUNT(*) FROM {full_view}")
            total_row = cur.fetchone()
            total = total_row[0] if total_row else 0
        assert count > 0, (
            f"L2FT matview {full_view!r} has no row for "
            f"planted rail {rail_name!r} — seed→matview-refresh "
            f"pipeline regression. Total rows in the matview: {total}.\n"
            f"plant: {plant!r}"
        )

    tt_plants = planted_manifest.get("transfer_template_plants", [])
    for plant in tt_plants:
        template_name = plant.get("template_name")
        assert template_name is not None, (
            f"TT plant {plant!r} missing template_name; can't verify"
        )
        with db_conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) FROM {full_view} "
                f"WHERE template_name = {placeholder}",
                (template_name,),
            )
            row = cur.fetchone()
            count = row[0] if row else 0
            cur.execute(f"SELECT COUNT(*) FROM {full_view}")
            total_row = cur.fetchone()
            total = total_row[0] if total_row else 0
        assert count > 0, (
            f"L2FT matview {full_view!r} has no row for "
            f"planted template {template_name!r} — seed→matview-refresh "
            f"pipeline regression. Total rows in the matview: {total}.\n"
            f"plant: {plant!r}"
        )


def assert_l2_exceptions_kpi_renders(
    page: Any,
    *,
    timeout_ms: int = 30_000,
) -> None:
    """Sanity check: the L2 Exceptions sheet's "Open L2 Violations" KPI
    renders an integer (≥ 0) — proves the unified-exceptions dataset's
    CustomSql ran against the per-test prefix without errors.

    M.4.4.15 reframe — the previous assertion looked for at least one
    of 6 hardcoded ``check_type`` category labels in the sheet text
    (Chain Orphans / Unmatched Transfer Type / Dead Rails / Dead
    Bundles Activity / Dead Metadata Declarations / Dead Limit
    Schedules). For a clean SPEC-skeleton fixture (spec_example),
    the broad-mode scenario produces ZERO violations of any kind —
    the dataset returns an empty result set and the dashboard
    correctly shows "No data" on every visual + 0 on the KPI. That's
    the desired healthy-state render, not a failure.

    A KPI rendering a number — even 0 — proves the dataset SQL
    executed cleanly. SQL errors would have left the KPI blank
    (caught by ``wait_for_kpi_text_nonempty``'s timeout).
    """
    from quicksight_gen.common.browser.helpers import (
        click_sheet_tab,
        wait_for_kpi_text_nonempty,
    )

    click_sheet_tab(page, "L2 Exceptions", timeout_ms=timeout_ms)
    kpi_title = "Open L2 Violations"
    kpi_text = wait_for_kpi_text_nonempty(
        page, kpi_title, timeout_ms=timeout_ms,
    )
    cleaned = kpi_text.replace(",", "").strip()
    try:
        kpi_value = int(cleaned)
    except ValueError as exc:
        raise AssertionError(
            f"L2 Exceptions KPI {kpi_title!r} text {kpi_text!r} isn't "
            f"parseable as an integer — dataset may have a SQL error"
        ) from exc
    assert kpi_value >= 0, (
        f"L2 Exceptions KPI {kpi_title!r} rendered a negative count "
        f"({kpi_value}) — dataset COUNT(*) shouldn't be negative"
    )


