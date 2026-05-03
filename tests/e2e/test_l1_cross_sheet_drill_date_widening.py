"""Browser e2e: cross-sheet drill into Transactions widens the date
range so the target transfer's row is visible.

v8.5.7 — bug class regression. Pre-v8.5.7 a drill from a current-state
sheet (Pending Aging — not in the universal date filter scope) into
the Transactions sheet (which IS scoped to a default 7-day window)
lost the target transfer's legs whenever the source row's posting
was older than 7 days. The drill wrote ``pL1TxTransfer`` but did
NOT write the date range params, leaving the Transactions sheet's
universal filter narrow.

Fix: the drill now also writes ``pL1DateStart=1990-01-01`` and
``pL1DateEnd=2099-12-31`` via ``DrillStaticDateTime`` — wide-window
"all time" so the target row is always in scope.

This test exercises the live-dashboard path:

1. Open the L1 dashboard and navigate to Pending Aging (always has
   stuck-pending plants, regardless of how old they are relative to
   the universal filter's default window).
2. Read the first row's transfer_id from the detail table.
3. Right-click that row → "View Transactions for this transfer".
4. After navigation, count the Transactions table's total rows.
5. Assert the table has ≥1 row — pre-fix the count was 0 when the
   stuck-pending leg was older than the default 7-day window.

Browser-tier — gated behind ``QS_GEN_E2E=1``; needs an L1 dashboard
deployed via the e2e harness (``l1_dashboard_id`` fixture).
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.browser.helpers import (
    click_context_menu_item,
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    read_visual_column_values,
    right_click_first_row_of_visual,
    scroll_visual_into_view,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_table_cells_present,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


# Tall viewport so the Pending Aging detail table renders above the
# fold and the right-click target is clickable without scrolling.
TALL_VIEWPORT = (1600, 4000)


@pytest.fixture
def embed_url(region, account_id, l1_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        aws_account_id=account_id,
        aws_region=region,
        dashboard_id=l1_dashboard_id,
    )


def test_pending_aging_drill_to_transactions_shows_target(
    embed_url, page_timeout,
):
    """Right-clicking a Pending Aging row → View Transactions must land
    on a Transactions sheet that actually shows the target transfer.

    The pre-v8.5.7 failure mode rendered an empty Transactions table
    because the drill didn't widen the universal date range — any
    stuck-pending leg older than the default 7-day window dropped out
    of view at the destination.

    Data-agnostic: doesn't assert any specific transfer_id value;
    only that ≥1 row survives the drill. The harness's broken-rail
    plants (``add_broken_rail_plants(broken_count=15)``) guarantee
    Pending Aging always has stuck rows older than 7 days.
    """
    with webkit_page(headless=True, viewport=TALL_VIEWPORT) as page:
        page.goto(embed_url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        click_sheet_tab(page, "Pending Aging", timeout_ms=page_timeout)
        wait_for_visuals_present(
            page, min_count=3, timeout_ms=page_timeout,
        )
        wait_for_table_cells_present(page, timeout_ms=page_timeout)

        # Sanity check: Pending Aging has rows. Without this, the drill
        # has nothing to click and the test would fail for the wrong
        # reason.
        scroll_visual_into_view(
            page, "Stuck Pending Detail", timeout_ms=page_timeout,
        )
        pre_drill_rows = count_table_total_rows(
            page, "Stuck Pending Detail", timeout_ms=page_timeout,
        )
        assert pre_drill_rows > 0, (
            f"Pending Aging detail table must have ≥1 stuck row before "
            f"the drill — harness broken-rail plants were expected to "
            f"keep this populated. Got {pre_drill_rows} rows."
        )

        # Read the first row's transfer_id (column index 2 — see
        # _populate_pending_aging_sheet's columns list:
        # [account_id, account_name, transfer_id, ...]). Used in the
        # post-drill assertion message so a failure points at the
        # specific transfer that didn't surface.
        try:
            transfer_ids = read_visual_column_values(
                page, "Stuck Pending Detail", col_index=2,
            )
            target_transfer_id = transfer_ids[0] if transfer_ids else "<unread>"
        except Exception:
            target_transfer_id = "<unread>"

        # Right-click the first row → context menu → drill action.
        right_click_first_row_of_visual(
            page, "Stuck Pending Detail", timeout_ms=page_timeout,
        )
        click_context_menu_item(
            page, "View Transactions for this transfer",
            timeout_ms=page_timeout,
        )

        # Wait for Transactions sheet to render.
        wait_for_visuals_present(
            page, min_count=1, timeout_ms=page_timeout,
        )
        wait_for_table_cells_present(page, timeout_ms=page_timeout)
        scroll_visual_into_view(
            page, "Posting Ledger", timeout_ms=page_timeout,
        )

        post_drill_rows = count_table_total_rows(
            page, "Posting Ledger", timeout_ms=page_timeout,
        )
        if post_drill_rows == 0:
            screenshot(
                page, "drill_to_transactions_empty",
                subdir="l1_dashboard",
            )
        assert post_drill_rows > 0, (
            f"Drill from Pending Aging → Transactions for transfer "
            f"{target_transfer_id!r} landed on an empty Posting Ledger. "
            f"This is the v8.5.7 bug class — the drill must widen the "
            f"universal date range so the target transfer's legs survive "
            f"the destination's filter. Check that "
            f"``_populate_pending_aging_sheet``'s drill includes "
            f"``*_wide_date_writes()`` in its writes list."
        )
