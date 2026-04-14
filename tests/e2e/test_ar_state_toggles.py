"""Browser tests: AR Show-Only-X toggles are present on each pipeline tab.

Mirrors ``test_state_toggles.py`` for the AR dashboard. All five toggles
(three drift/overdraft on Balances, one on Transfers, one on Transactions)
are sheet-level controls — verify each renders on the right sheet.
"""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    sheet_control_titles,
    wait_for_dashboard_loaded,
    wait_for_sheet_controls_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


TOGGLES_BY_TAB = {
    "Balances": [
        "Show Only Parent Drift",
        "Show Only Child Drift",
        "Show Only Overdraft",
    ],
    "Transactions": ["Show Only Failed"],
}


@pytest.fixture
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


def test_toggles_present_per_tab(embed_url, page_timeout):
    """Each AR pipeline tab shows its expected Show-Only-X toggle(s)."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)

        for tab, expected_toggles in TOGGLES_BY_TAB.items():
            click_sheet_tab(page, tab, timeout_ms=page_timeout)
            wait_for_sheet_controls_present(page, timeout_ms=page_timeout)
            titles = sheet_control_titles(page)
            missing = [t for t in expected_toggles if t not in titles]
            assert not missing, (
                f"Tab '{tab}' missing toggle(s) {missing}. "
                f"Got titles: {titles}"
            )
