"""Browser tests: navigate each Investigation sheet and verify visuals render.

The Account Network sheet's two side-by-side directional Sankeys are
the load-bearing K.4.8 invariant — both must hydrate, with their
distinct directional titles, so an analyst can tell inbound from
outbound by geometry. A regression that drops one or merges them back
into one omnidirectional Sankey would be invisible to the structural
tests if the analysis happens to keep both visual IDs but render the
same data; this test verifies the rendered titles.
"""

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


# Mirrors the structural assertions in test_inv_dashboard_structure.py
# but checks the rendered DOM rather than the dashboard definition JSON.
EXPECTED_VISUAL_COUNTS = {
    "Recipient Fanout": 4,
    "Volume Anomalies": 3,
    "Money Trail": 2,
    "Account Network": 3,
}


# Spot-check titles per sheet to make sure the right sheet rendered —
# not just that some sheet has the expected number of visuals.
EXPECTED_TITLES_PER_SHEET = {
    "Recipient Fanout": {
        "Qualifying Recipients",
        "Distinct Senders",
        "Total Inbound",
        "Recipient Fanout — Ranked",
    },
    "Volume Anomalies": {
        "Flagged Pair-Windows",
        "Pair-Window σ Distribution",
        "Flagged Pair-Windows — Ranked",
    },
    "Money Trail": {
        "Money Trail — Chain Sankey",
        "Money Trail — Hop-by-Hop",
    },
    "Account Network": {
        "Inbound — counterparties → anchor",
        "Outbound — anchor → counterparties",
        "Account Network — Touching Edges",
    },
}


@pytest.fixture
def embed_url(qs_client, account_id, inv_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=inv_dashboard_id,
    )


# Account Network's two Sankeys + table render side-by-side / stacked at
# the default 1000px viewport but the touching-edges table can sit below
# the fold; mirror AR's tall-viewport pattern so the DOM holds every
# visual at once and the counting assertions don't have to scroll.
TALL_VIEWPORT = (1600, 4000)


@pytest.mark.parametrize(
    "sheet_name,expected_count", list(EXPECTED_VISUAL_COUNTS.items()),
)
def test_sheet_renders_expected_visuals(
    embed_url, page_timeout, sheet_name, expected_count,
):
    """Navigate to each Investigation sheet and verify visual count matches."""
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
            subdir="investigation",
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
    """Spot-check per-sheet titles. Strongest signal that K.4.8's two
    distinct directional Sankeys are both rendering — a regression that
    silently merged them would drop one of the inbound/outbound titles."""
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
