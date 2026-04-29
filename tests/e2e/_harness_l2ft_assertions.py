"""L2 Flow Tracing Playwright assertions for the M.4.1 harness (M.4.1.e).

Mirrors the M.4.1.d L1 assertion module but for the L2 Flow Tracing
dashboard's surfaces. Per the M.4.1.e PLAN entry:

  - Rails sheet: ≥1 row per declared rail that the broad-mode
    scenario fires (every rail in rail_firing_plants with
    transfer_parent_id is None — chain-child plants use the same
    rail_name and would double-count).
  - Transfer Templates sheet: per planted TT firing, the
    template_name appears + per-instance completion_status reads
    as expected.
  - Chains sheet: per planted chain edge, the parent + child rails
    appear together. (Looser than L1 because chain rows show
    completion_status derived from runtime data, which is harder
    to predict deterministically without re-deriving the picker
    logic.)
  - L2 Exceptions sheet: the bar chart's check_type categories
    are all present (sanity check that the unified dataset
    rendered against the per-test prefix).

First-cut visibility check uses sheet-text substring matching
(same convention as the M.4.1.d L1 module). Tighter cell-level
assertions can layer on later as M.4.1.e-followups when QS table
reading proves stable.

The 6 L2 Exceptions check_type categories are pinned constants
(they're CAST literals in the unified-exceptions dataset SQL —
see ``apps/l2_flow_tracing/datasets.py::build_unified_l2_exceptions_dataset``).
"""

from __future__ import annotations

from typing import Any


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


def assert_l2ft_plants_visible(
    page: Any,
    planted_manifest: dict[str, list[dict[str, Any]]],
    *,
    timeout_ms: int = 30_000,
) -> None:
    """Walk every L2 plant kind in the manifest; assert each plant's
    identity appears on its expected L2 Flow Tracing sheet.

    For ``rail_firing_plants``: assert the ``rail_name`` substring
    surfaces on the Rails sheet. Chain-child plants (where
    ``transfer_parent_id`` is set) are skipped — they reuse the
    same rail_name as a standalone firing of the same rail, so
    the substring check is already satisfied by the standalone.

    For ``transfer_template_plants``: assert the ``template_name``
    substring surfaces on the Transfer Templates sheet.

    ``page`` MUST already be on the L2 Flow Tracing dashboard embed
    URL with initial dashboard load complete.

    Sheets with empty manifest entries are skipped.
    """
    from quicksight_gen.common.browser.helpers import click_sheet_tab

    # Rails sheet — distinct rail_names from non-chain firings.
    rail_plants = [
        p for p in planted_manifest.get("rail_firing_plants", [])
        if p.get("transfer_parent_id") is None
    ]
    if rail_plants:
        click_sheet_tab(page, "Rails", timeout_ms=timeout_ms)
        sheet_text = _active_sheet_text(page, timeout_ms=timeout_ms)
        for plant in rail_plants:
            rail_name = plant.get("rail_name")
            assert rail_name is not None, (
                f"rail plant {plant!r} missing rail_name; can't verify"
            )
            assert rail_name in sheet_text, (
                f"L2FT Rails sheet doesn't show planted rail "
                f"{rail_name!r}; expected the rail row to surface "
                f"after broad-mode plant + matview refresh\n"
                f"plant: {plant!r}"
            )

    # Transfer Templates sheet — distinct template_names.
    tt_plants = planted_manifest.get("transfer_template_plants", [])
    if tt_plants:
        click_sheet_tab(page, "Transfer Templates", timeout_ms=timeout_ms)
        sheet_text = _active_sheet_text(page, timeout_ms=timeout_ms)
        for plant in tt_plants:
            template_name = plant.get("template_name")
            assert template_name is not None, (
                f"TT plant {plant!r} missing template_name; can't verify"
            )
            assert template_name in sheet_text, (
                f"L2FT Transfer Templates sheet doesn't show planted "
                f"template {template_name!r}; expected the TT firing "
                f"to surface after broad-mode plant + matview refresh\n"
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


# Backwards-compat alias — the harness test still imports the old
# name. Kept as a thin wrapper so the rename can land in one commit
# without scattering test-file edits across this PR.
def assert_l2_exceptions_check_types_present(
    page: Any,
    *,
    timeout_ms: int = 30_000,
) -> None:
    """Deprecated — see ``assert_l2_exceptions_kpi_renders``."""
    assert_l2_exceptions_kpi_renders(page, timeout_ms=timeout_ms)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _active_sheet_text(page: Any, *, timeout_ms: int) -> str:
    """Return the rendered text of the currently active L2FT sheet.

    Same shape as the L1 assertions module's helper but inlined here
    to avoid cross-module coupling (the two assertion modules will
    likely diverge over time as L1 + L2FT surfaces drift).
    """
    from quicksight_gen.common.browser.helpers import (
        wait_for_table_cells_present,
    )

    try:
        wait_for_table_cells_present(page, timeout_ms=timeout_ms)
    except Exception:  # noqa: BLE001 — tables may not exist on every sheet
        pass
    visuals = page.query_selector_all(
        '[data-automation-id="analysis_visual"]'
    )
    if not visuals:
        return page.text_content("body") or ""
    return "\n".join(v.inner_text() for v in visuals)
