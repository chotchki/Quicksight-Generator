"""Browser tests: AR filter controls narrow the underlying visuals.

We verify the shared date-range filter by pushing it to a future window
and confirming the Transaction Detail table empties out. The date-range
filter is bound to ``ar_transactions.posted_at`` with ALL_DATASETS
cross-dataset scoping, so the Transactions sheet is where the filter
binding is most direct. Phase 3 of PLAN.md expands the matrix.
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
    wait_for_table_cells_present,
    wait_for_table_total_rows_to_change,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


def test_date_range_filter_narrows_transactions(embed_url, page_timeout):
    """Setting the date range to a future window should empty (or
    significantly reduce) the Transaction Detail table."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=5, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        before = count_table_total_rows(
            page, "Transaction Detail", timeout_ms=page_timeout,
        )
        assert before > 1, (
            f"Transaction Detail should have multiple rows pre-filter, "
            f"got {before}"
        )

        set_date_range(page, "2099/01/01", "2099/12/31", timeout_ms=page_timeout)
        after = wait_for_table_total_rows_to_change(
            page, "Transaction Detail", before, timeout_ms=page_timeout,
        )
        screenshot(page, "filter_date_range_future", subdir="account_recon")
        assert after < before, (
            f"Transaction Detail should shrink from {before} rows "
            f"after future date range, got {after}"
        )
