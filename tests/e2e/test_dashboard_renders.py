"""Browser test: verify the deployed dashboard loads via embed URL.

L.11.1 — sheet-tab assertion derives the expected set from the tree
(`pr_app.analysis.sheets`) instead of a hardcoded list. Catches sheet
adds/renames automatically.
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
def embed_url(region, account_id, dashboard_id) -> str:
    # Embed URL must be generated against the dashboard's region,
    # not the QuickSight identity region.
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=dashboard_id,
    )


class TestDashboardLoads:
    def test_embed_url_generated(self, embed_url):
        assert embed_url.startswith("https://"), (
            f"Embed URL does not look valid: {embed_url[:80]}"
        )

    def test_dashboard_page_loads(self, embed_url, page_timeout):
        with webkit_page(headless=True) as page:
            page.goto(embed_url, timeout=page_timeout)
            wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
            screenshot(page, "dashboard_initial_load", subdir="payment_recon")
            assert page.title(), "Page has no title — embed likely failed"

    def test_all_sheet_tabs_visible(self, embed_url, page_timeout, pr_app):
        expected = {s.name for s in pr_app.analysis.sheets}
        with webkit_page(headless=True) as page:
            page.goto(embed_url, timeout=page_timeout)
            wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
            tab_names = set(get_sheet_tab_names(page))
            missing = expected - tab_names
            assert not missing, (
                f"Missing sheet tabs: {missing}. Found: {sorted(tab_names)}"
            )
