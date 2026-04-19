"""Browser tests: navigate each AR sheet and verify visuals render."""

from __future__ import annotations

import pytest

from .browser_helpers import (
    click_sheet_tab,
    generate_dashboard_embed_url,
    get_visual_titles,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_visual_titles_present,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


# Mirrors the structural assertions in test_ar_dashboard_structure.py but
# checks the rendered DOM rather than the dashboard definition JSON.
EXPECTED_VISUAL_COUNTS = {
    "Balances": 4,
    "Transfers": 4,
    "Transactions": 5,
    "Exceptions": 47,
}


# Spot-check titles per sheet to make sure the right sheet rendered — not
# just that some sheet has the expected number of visuals.
EXPECTED_TITLES_PER_SHEET = {
    "Balances": {
        "Ledger Accounts",
        "Sub-Ledger Accounts",
        "Ledger Account Balances",
        "Sub-Ledger Account Balances",
    },
    "Transfers": {
        "Total Transfers",
        "Non-Zero Transfers",
        "Transfer Status",
        "Transfer Summary",
    },
    "Transactions": {
        "Total Transactions",
        "Failed Transactions",
        "Transactions by Status",
        "Transactions by Day",
        "Transaction Detail",
    },
    "Exceptions": {
        # Cross-check rollups (top of tab)
        "Two-Sided Post Mismatch",
        "Accounts Expected Zero at EOD",
        "Balance Drift Timelines",
        # Baseline check tables
        "Ledger Balance Drift",
        "Sub-Ledger Balance Drift",
        "Sub-Ledger Limit Breach",
        "Sub-Ledger Overdraft",
        "Non-Zero Transfers",
        # CMS-specific check tables
        "Sweep Target Non-Zero EOD",
        "ACH Origination Settlement Non-Zero EOD",
        "ACH Sweep Without Fed Confirmation",
        "Fed Activity Without Internal Post",
        "Stuck in Internal Transfer Suspense",
        "Internal Transfer Suspense Non-Zero EOD",
        "Reversed Transfers Without Credit-Back",
    },
}


@pytest.fixture
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


# Exceptions packs 47 visuals (3 rollup KPIs + 1 rollup chart + 14 KPIs +
# 14 detail tables + 4 drift timelines + 11 aging-bar charts) — at the
# default 1000px viewport QuickSight virtualizes below-the-fold visuals
# and only a handful show up in the DOM. A very tall viewport fits them
# all so the counting assertions below can just wait for the container
# count.
TALL_VIEWPORT = (1600, 12000)


@pytest.mark.parametrize(
    "sheet_name,expected_count", list(EXPECTED_VISUAL_COUNTS.items()),
)
def test_sheet_renders_expected_visuals(
    embed_url, page_timeout, sheet_name, expected_count,
):
    """Navigate to each AR sheet and verify visual count matches."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, sheet_name, timeout_ms=page_timeout)
        actual = wait_for_visuals_present(
            page, min_count=expected_count, timeout_ms=page_timeout,
        )
        screenshot(
            page,
            f"sheet_{sheet_name.replace(' ', '_')}",
            subdir="account_recon",
        )
        assert actual >= expected_count, (
            f"Sheet '{sheet_name}' rendered {actual} visuals, "
            f"expected {expected_count}. Titles seen: {get_visual_titles(page)}"
        )


@pytest.mark.parametrize(
    "sheet_name,expected_titles", list(EXPECTED_TITLES_PER_SHEET.items()),
)
def test_sheet_has_expected_titles(
    embed_url, page_timeout, sheet_name, expected_titles,
):
    """Spot-check per-sheet titles — a stronger signal than visual count
    that each AR sheet wired the right visuals."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, sheet_name, timeout_ms=page_timeout)
        wait_for_visuals_present(
            page,
            min_count=len(expected_titles),
            timeout_ms=page_timeout,
        )
        wait_for_visual_titles_present(
            page, expected_titles, timeout_ms=page_timeout,
        )
        titles = set(get_visual_titles(page))
        missing = expected_titles - titles
        assert not missing, (
            f"Sheet '{sheet_name}' missing visuals: {missing}"
        )
