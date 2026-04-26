"""Browser tests: navigate each PR sheet and verify visuals render.

L.11.2 — `TreeValidator(pr_app, page).validate_structure()` does the
full per-sheet structural walk in one call: navigate to each sheet,
assert every expected visual title is in the DOM, assert the visual
count matches `len(sheet.visuals)`. Replaces the prior hand-curated
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

# QuickSight virtualizes below-the-fold visuals. A tall viewport ensures
# all visuals render in the DOM at once so the count assertion works
# (Exceptions & Alerts has 12 visuals stacked, the largest sheet).
TALL_VIEWPORT = (1600, 5000)


@pytest.fixture
def embed_url(qs_client, account_id, dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=dashboard_id,
    )


def test_pr_dashboard_structure_matches_tree(embed_url, page_timeout, pr_app):
    """The deployed PR dashboard's sheets / visuals match what the tree
    declares. TreeValidator walks every sheet, asserts visual titles
    are present, and asserts the visual count matches `len(sheet.visuals)`
    — failures across sheets accumulate into a single AssertionError
    listing every mismatch."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        TreeValidator(pr_app, page, timeout_ms=page_timeout).validate_structure()
        screenshot(page, "dashboard_full_walk", subdir="payment_recon")
