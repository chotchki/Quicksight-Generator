"""Browser tests: navigate each sheet and verify visuals render."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    get_visual_titles,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


# Visual counts per sheet — these mirror the structural assertions in
# test_dashboard_structure.py but verify the rendered DOM, not the JSON.
EXPECTED_VISUAL_COUNTS = {
    "Sales Overview": 5,
    "Settlements": 4,
    "Payments": 4,
    "Exceptions & Alerts": 7,
    "Payment Reconciliation": 6,
}

# A title we expect on each sheet — light spot-check that the right
# sheet rendered (not just any 4 visuals).
EXPECTED_TITLE_PER_SHEET = {
    "Sales Overview": "Total Sales Count",
    "Settlements": None,  # filled in once we observe the live titles
    "Payments": None,
    "Exceptions & Alerts": None,
    "Payment Reconciliation": None,
}


@pytest.fixture
def embed_url(qs_client, account_id, dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=dashboard_id,
    )


@pytest.mark.parametrize("sheet_name,expected_count", list(EXPECTED_VISUAL_COUNTS.items()))
def test_sheet_renders_expected_visuals(
    embed_url, page_timeout, visual_timeout, sheet_name, expected_count
):
    """Navigate to each sheet and verify the expected number of visuals render."""
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)

        # Navigate to the target sheet (no-op if it's the active sheet)
        click_sheet_tab(page, sheet_name, timeout_ms=page_timeout)

        # Wait for all expected visuals to attach to the DOM
        actual = wait_for_visuals_present(
            page, min_count=expected_count, timeout_ms=page_timeout
        )

        screenshot(page, f"sheet_{sheet_name.replace(' ', '_').replace('&', 'and')}")

        assert actual >= expected_count, (
            f"Sheet '{sheet_name}' rendered {actual} visuals, expected {expected_count}. "
            f"Titles seen: {get_visual_titles(page)}"
        )


def test_sales_overview_has_expected_titles(embed_url, page_timeout):
    """Spot-check that the Sales Overview sheet shows its named visuals."""
    expected_titles = {
        "Total Sales Count",
        "Total Sales Amount",
        "Sales Amount by Merchant",
        "Sales Amount by Location",
        "Sales Detail",
    }
    with webkit_page(headless=True) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Sales Overview", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=5, timeout_ms=page_timeout)
        # Visual containers attach before their title labels hydrate; poll
        # until every expected title is rendered (or the timeout fires).
        page.wait_for_function(
            f"""() => {{
                const want = new Set({sorted(expected_titles)!r});
                const have = new Set(
                    Array.from(document.querySelectorAll(
                        '[data-automation-id="analysis_visual_title_label"]'
                    )).map(el => el.innerText.trim()).filter(Boolean)
                );
                for (const t of want) {{ if (!have.has(t)) return false; }}
                return true;
            }}""",
            timeout=page_timeout,
        )
        titles = set(get_visual_titles(page))
        missing = expected_titles - titles
        assert not missing, f"Missing visual titles on Sales Overview: {missing}"
