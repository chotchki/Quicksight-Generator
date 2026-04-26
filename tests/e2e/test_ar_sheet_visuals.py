"""Browser tests: navigate each AR sheet and verify visuals render.

L.11.2 — `TreeValidator(ar_app, page).validate_structure()` walks
every sheet, asserts visual titles are present, asserts the visual
count matches `len(sheet.visuals)`. Replaces the hand-curated
`EXPECTED_VISUAL_COUNTS` + `EXPECTED_TITLES_PER_SHEET` dicts.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    webkit_page,
)
from .tree_validator import TreeValidator


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


# Exceptions Trends stacks 7 visuals full-width — at the default 1000px
# viewport QuickSight virtualizes below-the-fold visuals and only a few
# show up in the DOM. A taller viewport fits them all so the counting
# assertions don't have to scroll.
TALL_VIEWPORT = (1600, 4000)


def test_ar_dashboard_structure_matches_tree(embed_url, page_timeout, ar_app):
    """The deployed AR dashboard's sheets / visuals match what the tree
    declares. TreeValidator walks every sheet, asserts visual titles
    are present, asserts the visual count matches `len(sheet.visuals)`
    — failures across sheets accumulate into a single AssertionError."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        TreeValidator(ar_app, page, timeout_ms=page_timeout).validate_structure()
        screenshot(page, "dashboard_full_walk", subdir="account_recon")
