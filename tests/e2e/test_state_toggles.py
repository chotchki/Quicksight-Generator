"""Browser test: Show-Only-X toggles are present on the pipeline tabs and
no tab still carries the old days-outstanding slider."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    wait_for_dashboard_loaded,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


# Tabs that carry a Show-Only-X toggle dropdown.
TOGGLE_TABS = (
    ("Sales Overview", "Show Only Unsettled"),
    ("Settlements", "Show Only Unpaid"),
    ("Payments", "Show Only Unmatched Externally"),
)

# Every tab whose sheet-level controls we'll inspect. Exceptions and
# Payment Reconciliation have no toggle and no slider — the date-range
# filter covers that need.
ALL_INSPECTED_TABS = [tab for tab, _title in TOGGLE_TABS] + [
    "Exceptions & Alerts",
    "Payment Reconciliation",
]

SLIDER_TITLE = "Minimum Days Outstanding"


@pytest.fixture
def embed_url(qs_client, account_id, dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=dashboard_id,
    )


def _sheet_control_titles(page) -> list[str]:
    """Return the visible titles of filter controls on the active sheet."""
    els = page.query_selector_all('[data-automation-id="sheet_control_name"]')
    return [e.inner_text().strip() for e in els if e.inner_text().strip()]


def test_toggles_present_and_no_slider(embed_url, page_timeout):
    """Sales/Settlements/Payments each expose their toggle title, and
    no tab should still render the old days-outstanding slider."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)

        for tab, toggle_title in TOGGLE_TABS:
            click_sheet_tab(page, tab, timeout_ms=page_timeout)
            page.wait_for_selector(
                '[data-automation-id="sheet_control_name"]',
                timeout=page_timeout, state="attached",
            )
            titles = _sheet_control_titles(page)
            assert toggle_title in titles, (
                f"Tab '{tab}' missing toggle '{toggle_title}'. "
                f"Got titles: {titles}"
            )

        for tab in ALL_INSPECTED_TABS:
            click_sheet_tab(page, tab, timeout_ms=page_timeout)
            page.wait_for_selector(
                '[data-automation-id="sheet_control_name"]',
                timeout=page_timeout, state="attached",
            )
            titles = _sheet_control_titles(page)
            assert SLIDER_TITLE not in titles, (
                f"Tab '{tab}' still has the days-outstanding slider. "
                f"Got titles: {titles}"
            )
