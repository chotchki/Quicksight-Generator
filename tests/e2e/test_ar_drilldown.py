"""Browser tests: AR drill-downs pass parameters to the target sheet."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_first_row_of_visual,
    click_sheet_tab,
    generate_dashboard_embed_url,
    screenshot,
    selected_sheet_name,
    wait_for_dashboard_loaded,
    wait_for_sheet_tab,
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


def test_balances_subledger_drills_to_transactions(embed_url, page_timeout):
    """Clicking a subledger_account_id in the Sub-Ledger Account Balances
    table should navigate to Transactions (with pArSubledgerAccountId set)."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Balances", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)

        click_first_row_of_visual(
            page, "Sub-Ledger Account Balances", timeout_ms=page_timeout,
        )
        wait_for_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        screenshot(
            page, "drilldown_balances_subledger_to_txn", subdir="account_recon",
        )
        assert selected_sheet_name(page) == "Transactions"


def test_transfer_summary_drills_to_transactions(embed_url, page_timeout):
    """Clicking a transfer_id in the Transfer Summary table should navigate
    to Transactions (with pArTransferId set)."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Transfers", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)

        click_first_row_of_visual(
            page, "Transfer Summary", timeout_ms=page_timeout,
        )
        wait_for_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        screenshot(
            page, "drilldown_transfers_to_txn", subdir="account_recon",
        )
        assert selected_sheet_name(page) == "Transactions"


def test_todays_exceptions_table_drills_to_transactions(
    embed_url, page_timeout,
):
    """Clicking a transfer_id in the Open Exceptions table on Today's
    Exceptions should drill into Transactions (with pArTransferId set).

    Phase K.1.2 replaces the per-check drill paths from the legacy
    Exceptions sheet with this single drill from the unified table."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Today's Exceptions", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=3, timeout_ms=page_timeout)

        click_first_row_of_visual(
            page, "Open Exceptions", timeout_ms=page_timeout,
        )
        wait_for_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        screenshot(
            page, "drilldown_todays_exc_to_txn", subdir="account_recon",
        )
        assert selected_sheet_name(page) == "Transactions"
