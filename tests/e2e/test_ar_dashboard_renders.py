"""Browser test: verify the deployed Account Recon dashboard loads."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    generate_dashboard_embed_url,
    get_sheet_tab_names,
    screenshot,
    wait_for_dashboard_loaded,
    webkit_page,
)


EXPECTED_SHEETS = {
    "Getting Started",
    "Balances",
    "Transfers",
    "Transactions",
    "Exceptions",
}


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


class TestArDashboardLoads:
    def test_embed_url_generated(self, embed_url):
        assert embed_url.startswith("https://"), (
            f"Embed URL does not look valid: {embed_url[:80]}"
        )

    def test_dashboard_page_loads(self, embed_url, page_timeout):
        with webkit_page(headless=True) as page:
            page.goto(embed_url, timeout=page_timeout)
            wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
            screenshot(page, "dashboard_initial_load", subdir="account_recon")
            assert page.title(), "Page has no title — embed likely failed"

    def test_all_five_sheet_tabs_visible(self, embed_url, page_timeout):
        with webkit_page(headless=True) as page:
            page.goto(embed_url, timeout=page_timeout)
            wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
            tab_names = set(get_sheet_tab_names(page))
            missing = EXPECTED_SHEETS - tab_names
            assert not missing, (
                f"Missing AR sheet tabs: {missing}. Found: {sorted(tab_names)}"
            )
