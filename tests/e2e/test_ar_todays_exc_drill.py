"""Browser tests: the unified Today's Exceptions table's two drill actions
narrow the Transactions sheet to the right scope.

The bug this guards against: Phase K.1.6.x found that the legacy
single-drill (transfer_id only) silently no-op'd for nine check types,
leaving Transactions un-filtered after the navigation. The fix wires a
second DATA_POINT_MENU action that sets ``pArAccountId`` (+ activity
date) for the seven account-shaped checks, and adds the matching filter
group on the Transactions sheet.

Rather than fight the click trigger in headless WebKit (the data-point
context menu doesn't reliably open and QS's multi-select picker mis-
clicks), we exercise the **filter wiring** directly via QuickSight's
URL-fragment parameter syntax: appending ``#p.<paramName>=<value>`` to
the embed URL sets that parameter on dashboard load. If the filter
group is correctly bound, Transactions narrows; if not, it stays at
baseline. The drill actions themselves are verified by reading the
deployed analysis JSON in unit tests / structural e2e.

The test picks real identifier values from the deterministic demo seed
via a direct SQL query against the same dataset the dashboard feeds
from, so failures can't be blamed on stale / client-side scraping.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from .browser_helpers import (
    click_sheet_tab,
    count_table_total_rows,
    generate_dashboard_embed_url,
    screenshot,
    wait_for_dashboard_loaded,
    wait_for_visuals_present,
    webkit_page,
)


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


@pytest.fixture(scope="module")
def drill_values(cfg) -> dict:
    """Query the deployed DB for a valid transfer_id and (account_id,
    activity_date) pair from the unified-exceptions dataset.

    Uses the same SQL the QuickSight dataset runs so we're testing the
    filter wiring against values the dashboard actually renders.
    """
    if not cfg.demo_database_url:
        pytest.skip("demo_database_url required to look up drill values")
    import psycopg2
    from quicksight_gen.account_recon.datasets import (
        build_ar_unified_exceptions_dataset,
    )

    ds = build_ar_unified_exceptions_dataset(cfg)
    sql = ds.PhysicalTableMap["ar-unified-exceptions"].CustomSql.SqlQuery
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT transfer_id FROM ({sql}) u "
                f"WHERE transfer_id IS NOT NULL LIMIT 1"
            )
            row = cur.fetchone()
            transfer_id = row[0] if row else None
            cur.execute(
                f"SELECT account_id, exception_date FROM ({sql}) u "
                f"WHERE account_id IS NOT NULL LIMIT 1"
            )
            row = cur.fetchone()
            account_id = row[0] if row else None
            activity_date = row[1].isoformat() if row and row[1] else None
    finally:
        conn.close()

    if not transfer_id or not account_id or not activity_date:
        pytest.skip(
            "Demo DB lacks a populated transfer_id and/or "
            "(account_id, exception_date) — cannot validate drill wiring"
        )
    return {
        "transfer_id": transfer_id,
        "account_id": account_id,
        "activity_date": activity_date,
    }


def _fresh_embed_url(qs_client, account_id, ar_dashboard_id) -> str:
    return generate_dashboard_embed_url(
        qs_identity_client=qs_client,
        account_id=account_id,
        dashboard_id=ar_dashboard_id,
    )


def _transactions_count(page, page_timeout: int) -> int:
    click_sheet_tab(page, "Transactions", timeout_ms=page_timeout)
    wait_for_visuals_present(page, min_count=1, timeout_ms=page_timeout)
    return count_table_total_rows(
        page, "Transaction Detail", timeout_ms=page_timeout,
    )


def _baseline(qs_client, account_id, ar_dashboard_id, page_timeout) -> int:
    url = _fresh_embed_url(qs_client, account_id, ar_dashboard_id)
    with webkit_page(headless=True) as page:
        page.goto(url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        return _transactions_count(page, page_timeout)


def test_drill_param_pArTransferId_narrows_transactions(
    qs_client, account_id, ar_dashboard_id, page_timeout, drill_values,
):
    """Setting pArTransferId via URL fragment filters Transactions to that
    transfer's legs. Guards the original (left-click) drill path."""
    baseline = _baseline(qs_client, account_id, ar_dashboard_id, page_timeout)
    assert baseline > 0, "Transactions baseline must be > 0"

    url = (
        _fresh_embed_url(qs_client, account_id, ar_dashboard_id)
        + f"#p.pArTransferId={quote(drill_values['transfer_id'])}"
    )
    with webkit_page(headless=True) as page:
        page.goto(url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        narrowed = _transactions_count(page, page_timeout)
        screenshot(
            page, "todays_exc_drill_url_pArTransferId", subdir="account_recon",
        )

    assert narrowed < baseline, (
        f"pArTransferId={drill_values['transfer_id']!r} did not narrow "
        f"Transactions ({narrowed} >= baseline {baseline}). The "
        f"transfer-id filter group on the Transactions sheet may be "
        f"mis-wired."
    )


def test_drill_params_pArAccountId_and_date_narrow_transactions(
    qs_client, account_id, ar_dashboard_id, page_timeout, drill_values,
):
    """Setting pArAccountId + pArActivityDate via URL fragment filters
    Transactions to that account-day. Guards the Phase K.1.6.x fix — the
    new DATA_POINT_MENU drill action that covers seven account-shaped
    check types the legacy single-drill silently no-op'd for."""
    baseline = _baseline(qs_client, account_id, ar_dashboard_id, page_timeout)
    assert baseline > 0, "Transactions baseline must be > 0"

    url = (
        _fresh_embed_url(qs_client, account_id, ar_dashboard_id)
        + f"#p.pArAccountId={quote(drill_values['account_id'])}"
        + f"&p.pArActivityDate={quote(drill_values['activity_date'])}"
    )
    with webkit_page(headless=True) as page:
        page.goto(url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        narrowed = _transactions_count(page, page_timeout)
        screenshot(
            page, "todays_exc_drill_url_pArAccountId", subdir="account_recon",
        )

    assert narrowed < baseline, (
        f"pArAccountId={drill_values['account_id']!r} + "
        f"pArActivityDate={drill_values['activity_date']!r} did not narrow "
        f"Transactions ({narrowed} >= baseline {baseline}). The new "
        f"account-id filter group on the Transactions sheet (Phase "
        f"K.1.6.x) may be mis-wired."
    )
