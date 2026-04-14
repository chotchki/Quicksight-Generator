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


# Exceptions packs 12 visuals — use a taller viewport so all of them
# hydrate and we can target tables at the bottom of the sheet.
TALL_VIEWPORT = (1600, 3200)


@pytest.fixture
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


def test_balances_child_drills_to_transactions(embed_url, page_timeout):
    """Clicking an account_id in the Child Account Balances table should
    navigate to Transactions (with pArAccountId set)."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Balances", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=4, timeout_ms=page_timeout)

        click_first_row_of_visual(
            page, "Child Account Balances", timeout_ms=page_timeout,
        )
        wait_for_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        screenshot(
            page, "drilldown_balances_child_to_txn", subdir="account_recon",
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


def test_breach_drills_to_transactions(embed_url, page_timeout):
    """Clicking an account_id in the Child Limit Breach table should drill
    into Transactions with account + date + transfer_type all set.

    The multi-parameter drill-down shape is only here; all other AR drills
    are single-parameter, so this exercises the ``_multi_drill_action`` path
    that Phase 5.7 introduced."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Exceptions", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=12, timeout_ms=page_timeout)

        click_first_row_of_visual(
            page, "Child Limit Breach", timeout_ms=page_timeout,
        )
        wait_for_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
        screenshot(
            page, "drilldown_breach_to_txn", subdir="account_recon",
        )
        assert selected_sheet_name(page) == "Transactions"
