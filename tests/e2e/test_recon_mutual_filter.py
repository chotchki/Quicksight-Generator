"""Browser tests: payment recon mutual table filtering."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_first_row_of_visual,
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_table_cells_present,
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


def test_clicking_external_txn_filters_payments(embed_url, page_timeout):
    """Clicking an External Transactions row should reduce the Internal Payments row count."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Payment Reconciliation", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=6, timeout_ms=page_timeout)
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        before = count_table_total_rows(
            page, "Internal Payments", timeout_ms=page_timeout,
        )
        assert before > 1, (
            f"Internal Payments table should have multiple rows before filtering, got {before}"
        )

        click_first_row_of_visual(page, "External Transactions", timeout_ms=page_timeout)
        after = wait_for_table_total_rows_to_change(
            page, "Internal Payments", before, timeout_ms=page_timeout,
        )
        screenshot(
            page,
            "recon_mutual_filter_external_to_payments",
            subdir="payment_recon",
        )
        assert 0 < after < before, (
            f"Internal Payments should filter to < {before} rows after click, got {after}"
        )
