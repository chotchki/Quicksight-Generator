"""Characterization: QS navigation-driven parameter filters stack
across drill-down round-trips. Covers PLAN 5.1.

After a drill-down sets a parameter on the destination sheet, the
parameter stays set when the user tabs away and back — QuickSight
has no API to clear a parameter on tab-switch. This test captures
the behavior with ``xfail(strict=False)`` so it neither fails the
suite nor silently disappears.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    click_sheet_tab,
    count_table_total_rows,
    first_table_cell_text,
    generate_dashboard_embed_url,
    screenshot,
    selected_sheet_name,
    wait_for_dashboard_loaded,
    wait_for_sheet_tab,
    wait_for_table_cells_present,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=dashboard_id,
    )


@pytest.mark.xfail(
    strict=False,
    reason="QuickSight has no API to clear a parameter on tab-switch — "
    "drill-down-set parameters stay active after the user tabs away and "
    "back. Documented in README 'Known Limitations'.",
)
def test_drilldown_parameter_persists_after_tab_roundtrip(
    embed_url, page_timeout,
):
    """Expected: tabbing away from a drill-down destination and back
    clears the drill-down parameter. Actual: the parameter persists,
    so the destination sheet stays filtered to one row."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Settlements", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        settlement_id = first_table_cell_text(page, row=0, col=0)
        assert settlement_id.startswith("stl-")

        page.click(
            '[data-automation-id="sn-table-cell-0-0"]', timeout=page_timeout,
        )
        wait_for_sheet_tab(page, "Sales Overview", timeout_ms=page_timeout)
        assert selected_sheet_name(page) == "Sales Overview"

        filtered_rows = count_table_total_rows(
            page, "Sales Detail", timeout_ms=page_timeout,
        )
        assert filtered_rows >= 1, "Drill-down should land on ≥1 filtered row"

        # Tab-switch round-trip: Sales → Settlements → Sales.
        click_sheet_tab(page, "Settlements", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)
        click_sheet_tab(page, "Sales Overview", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        screenshot(
            page, "filter_stacking_after_roundtrip", subdir="payment_recon",
        )
        after_rows = count_table_total_rows(
            page, "Sales Detail", timeout_ms=page_timeout,
        )
        # Desired behavior: parameter clears on tab-switch → many rows.
        # Actual: parameter persists → still filtered to a handful.
        assert after_rows > filtered_rows * 5, (
            f"Expected Sales Detail to unfilter after tab round-trip "
            f"(drilldown→{filtered_rows} rows, after round-trip→{after_rows}); "
            f"small delta indicates pSettlementId stacked across nav."
        )
