"""Browser tests: filter controls actually filter the underlying visuals.

We only validate the date-range filter on the Sales Overview sheet —
it's the most user-facing filter and exercises the same parameter /
filter-group machinery as the rest. Phase 2 of PLAN.md expands the
matrix.
"""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    screenshot,
    set_date_range,
    wait_for_dashboard_loaded,
    wait_for_table_total_rows_to_change,
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


def test_date_range_filter_narrows_sales_detail(embed_url, page_timeout):
    """Setting the date range to a future window should empty (or
    significantly reduce) the Sales Detail table on Sales Overview."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Sales Overview", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=5, timeout_ms=page_timeout)
        page.wait_for_selector(
            '[data-automation-id^="sn-table-cell-0-0"]',
            timeout=page_timeout,
            state="attached",
        )

        before = count_table_total_rows(page, "Sales Detail", timeout_ms=page_timeout)
        assert before > 1, (
            f"Sales Detail should have multiple rows before filtering, got {before}"
        )

        set_date_range(page, "2099/01/01", "2099/12/31", timeout_ms=page_timeout)
        after = wait_for_table_total_rows_to_change(
            page, "Sales Detail", before, timeout_ms=page_timeout,
        )
        screenshot(page, "filter_date_range_future", subdir="payment_recon")
        assert after < before, (
            f"Sales Detail should filter to < {before} rows after future date range, got {after}"
        )
