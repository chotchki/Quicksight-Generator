"""Browser test: verify the deployed L1 dashboard loads.

M.2c.4. Smoke layer — confirms embed URL generates, page loads
without an error banner, every sheet tab is visible. Sheet tab set
derives from the `l1_app` tree per the no-hardcoded-data rule.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    generate_dashboard_embed_url,
    get_sheet_tab_names,
    screenshot,
    wait_for_dashboard_loaded,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(region, account_id, l1_dashboard_id) -> str:
    """Function-scoped — embed URLs are single-use, fresh per test."""
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=l1_dashboard_id,
    )


class TestL1DashboardLoads:
    def test_embed_url_generated(self, embed_url):
        assert embed_url.startswith("https://"), (
            f"Embed URL does not look valid: {embed_url[:80]}"
        )

    def test_dashboard_page_loads(self, embed_url, page_timeout):
        with webkit_page(headless=True) as page:
            page.goto(embed_url, timeout=page_timeout)
            wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
            screenshot(page, "dashboard_initial_load", subdir="l1_dashboard")
            assert page.title(), "Page has no title — embed likely failed"

    def test_all_sheet_tabs_visible(
        self, embed_url, page_timeout, l1_app,
    ):
        """Tab set comes from the tree — switching L2 instance changes
        the sheet names but the assertion stays valid."""
        expected = {s.name for s in l1_app.analysis.sheets}
        with webkit_page(headless=True) as page:
            page.goto(embed_url, timeout=page_timeout)
            wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
            tab_names = set(get_sheet_tab_names(page))
            missing = expected - tab_names
            assert not missing, (
                f"Missing L1 dashboard sheet tabs: {missing}. "
                f"Found: {sorted(tab_names)}"
            )
