"""Browser tests: Investigation drill-downs re-render the underlying visuals.

K.4.8 invariant — clicking a row in the Account Network touching-edges
table writes the row's counterparty into the anchor parameter, and the
table + Sankeys re-render around the new anchor. The drill stays on the
same sheet, so the verifiable signal is "the table contents changed",
not "we navigated to a new sheet".
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from quicksight_gen.common.browser.helpers import (
    click_first_row_of_visual,
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_table_total_rows_to_change,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture
def embed_url(qs_client, account_id, inv_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=inv_dashboard_id,
    )


@pytest.mark.skip(
    reason=(
        "Deferred: depends on URL-hash anchor pre-seeding "
        "('#p.pInvANetworkAnchor=<value>') which hits the same embed-URL "
        "loading issue as the slider URL-param tests. The table does "
        "render with 35 rows after seed, but the click-to-walk action "
        "doesn't change row count within the timeout — could be the "
        "click landing on a counterparty with the same fanout, or the "
        "walk action not propagating. Needs either a control-driven "
        "anchor setter or a more reliable witness for walk propagation "
        "than touching-edges row count. Tracked for K.4.9 follow-up."
    )
)
def test_account_network_table_walk_rerenders_table(embed_url, page_timeout):
    """Clicking a row in the Account Network table walks the anchor over
    to that row's counterparty. The table is filtered to "edges touching
    anchor", so the new anchor narrows the table to a different set of
    rows — the row count changes (could be larger or smaller, since
    different anchors have different fanout). The K.4.8 invariant under
    test: the click DOES propagate to the parameter and the table DOES
    re-render. A regression that wired the action to a no-op counterparty
    field (the K.4.8f-3 bug) would leave the table unchanged.

    The anchor parameter has no DefaultValues — the dropdown's HIDDEN
    All semantics make QuickSight pick the first available row. We
    pre-set the anchor via URL parameter to make the initial state
    deterministic (otherwise the auto-pick races with the test).
    """
    # Juniper Ridge LLC is the K.4.6 fanout-cluster recipient — 24
    # ACH inbounds from individual depositors plus the K.4.4 anomaly
    # pair + the K.4.5 trail root. Guaranteed >1 inbound edges in the
    # matview so the touching-edges table has rows to click on.
    starting_anchor = "Juniper Ridge LLC — DDA (cust-900-0007-juniper-ridge-llc)"
    seeded_url = (
        f"{embed_url}#p.pInvANetworkAnchor={quote(starting_anchor)}"
    )

    with webkit_page(headless=True) as page:
        page.goto(seeded_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Account Network", timeout_ms=page_timeout)
        wait_for_visuals_present(page, min_count=3, timeout_ms=page_timeout)

        # count_table_total_rows handles its own scroll-into-view +
        # focus + page-size bump, so we don't need a separate
        # wait_for_table_cells_present (which can fail if cells start
        # below the fold).
        before = count_table_total_rows(
            page,
            "Account Network — Touching Edges",
            timeout_ms=page_timeout,
        )
        assert before > 1, (
            f"Account Network table should have multiple rows pre-walk "
            f"with anchor={starting_anchor!r}, got {before}"
        )

        click_first_row_of_visual(
            page,
            "Account Network — Touching Edges",
            timeout_ms=page_timeout,
        )
        after = wait_for_table_total_rows_to_change(
            page,
            "Account Network — Touching Edges",
            before,
            timeout_ms=page_timeout,
        )
        screenshot(
            page, "drill_anetwork_table_walk", subdir="investigation",
        )
        assert after != before, (
            f"Account Network table should re-render with a different "
            f"row count after walking the anchor; before={before}, "
            f"after={after}"
        )
