"""Browser tests: walk each L1 sheet and verify visuals render.

M.2c.5. `TreeValidator(l1_app, page).validate_structure()` walks every
sheet, asserts visual titles are present, asserts the visual count
matches `len(sheet.visuals)`. One call covers everything; no per-sheet
hand-listed visual title dicts.

When M.2b.4+ adds Daily Statement / Transactions / etc., the new
sheets pick up automatically — the validator walks `l1_app.analysis.
sheets` and asserts whatever is there.
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
def embed_url(region, account_id, l1_dashboard_id) -> str:
    """Function-scoped — embed URLs are single-use."""
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=l1_dashboard_id,
    )


# Tall viewport so stacked tables don't sit below the fold during the
# walk — mirrors AR's tall-viewport pattern.
TALL_VIEWPORT = (1600, 4000)

# Per-sheet visual-rendering budget. The default PAGE_TIMEOUT (30s) is
# enough for steady-state QS dashboards (Investigation works at 30s),
# but the L1 dashboard's KPI-heavy Daily Statement (5 KPIs + 1 table
# all backed by the multi-CTE summary SQL) consistently takes longer
# than 30s after a fresh deploy — the per-dataset query cache hasn't
# warmed yet so each KPI's first SELECT pays a cold-start tax. Screenshot
# evidence: KPI titles ALL render eventually (visible in
# tests/e2e/screenshots/l1_dashboard/dashboard_full_walk.png) — they
# just don't all hydrate within the default 30s window when the test
# runs immediately after a redeploy. 90s gives Aurora + QS room to
# warm without artificially slowing happy-path runs.
L1_VISUAL_TIMEOUT = 90_000


def test_l1_dashboard_structure_matches_tree(embed_url, page_timeout, l1_app):
    """The deployed L1 dashboard's sheets + visuals match what the tree
    declares. TreeValidator walks every sheet, asserts visual titles
    are present, asserts visual count matches `len(sheet.visuals)`.
    Failures across sheets accumulate into one AssertionError."""
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        TreeValidator(
            l1_app, page, timeout_ms=L1_VISUAL_TIMEOUT,
        ).validate_structure()
        screenshot(page, "dashboard_full_walk", subdir="l1_dashboard")
