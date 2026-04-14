"""Browser tests: drill-down from one sheet to another with parameter pass-through."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
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


def test_settlements_to_sales_drilldown(embed_url, page_timeout):
    """Clicking a settlement_id in the Settlements detail table should
    navigate to Sales Overview (with pSettlementId set)."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Settlements", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        settlement_id = first_table_cell_text(page, row=0, col=0)
        assert settlement_id.startswith("stl-"), (
            f"Expected first column to hold settlement_id, got {settlement_id!r}"
        )

        # Click the settlement_id cell — DATA_POINT_CLICK fires the drill-down
        page.click('[data-automation-id="sn-table-cell-0-0"]', timeout=page_timeout)

        # Sheet should switch to Sales Overview
        wait_for_sheet_tab(page, "Sales Overview", timeout_ms=page_timeout)
        screenshot(page, "drilldown_settlements_to_sales", subdir="payment_recon")

        assert selected_sheet_name(page) == "Sales Overview"


def test_payments_to_settlements_drilldown(embed_url, page_timeout):
    """Clicking a settlement_id in the Payments detail table should
    navigate to Settlements with pSettlementId set."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Payments", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        # Find a column whose value looks like a settlement id (stl-…). The
        # exact column index for settlement_id depends on the visual's field
        # ordering; scan the first row.
        settlement_col = None
        for c in range(20):
            cell = page.query_selector(f'[data-automation-id="sn-table-cell-0-{c}"]')
            if cell is None:
                break
            if cell.inner_text().strip().startswith("stl-"):
                settlement_col = c
                break
        assert settlement_col is not None, (
            "No settlement_id column found in Payments detail table"
        )

        page.click(
            f'[data-automation-id="sn-table-cell-0-{settlement_col}"]',
            timeout=page_timeout,
        )
        wait_for_sheet_tab(page, "Settlements", timeout_ms=page_timeout)
        screenshot(page, "drilldown_payments_to_settlements", subdir="payment_recon")
        assert selected_sheet_name(page) == "Settlements"
