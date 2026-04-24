"""Browser tests: navigate each Investigation sheet and verify visuals render.

L.11.2 — `TreeValidator(inv_app, page).validate_structure()` walks
every sheet, asserts visual titles are present, asserts the visual
count matches `len(sheet.visuals)`. Replaces the hand-curated
`EXPECTED_VISUAL_COUNTS` + `EXPECTED_TITLES_PER_SHEET` dicts.

The Account Network sheet's two side-by-side directional Sankeys
remain the load-bearing K.4.8 invariant — both must hydrate, with
their distinct directional titles, so an analyst can tell inbound
from outbound by geometry. The tree declares both
("Inbound — counterparties → anchor", "Outbound — anchor →
counterparties") and TreeValidator asserts both render — a
regression that silently merged them would surface as a missing
title.
"""

from __future__ import annotations

import pytest

from .browser_helpers import (
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    webkit_page,
)
from .tree_validator import TreeValidator


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, inv_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=inv_dashboard_id,
    )


# Account Network's two Sankeys + table render side-by-side / stacked
# at the default 1000px viewport but the touching-edges table can sit
# below the fold; mirror AR's tall-viewport pattern.
TALL_VIEWPORT = (1600, 4000)


def test_inv_dashboard_structure_matches_tree(embed_url, page_timeout, inv_app):
    """The deployed Investigation dashboard's sheets / visuals match
    what the tree declares. TreeValidator walks every sheet, asserts
    visual titles are present, asserts the visual count matches
    `len(sheet.visuals)`. Failures across sheets accumulate into a
    single AssertionError."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        TreeValidator(inv_app, page, timeout_ms=page_timeout).validate_structure()
        screenshot(page, "dashboard_full_walk", subdir="investigation")
