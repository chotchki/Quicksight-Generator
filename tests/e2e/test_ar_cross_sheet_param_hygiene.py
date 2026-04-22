"""Browser tests: cross-sheet drill-down parameter hygiene.

Premise of K.2 cross-sheet refactor: when a drill action only writes the
params it cares about, the destination sheet inherits stale values from
its other params (left over from a prior visit). The Today's Exceptions
right-click "View Transactions for Account-Day" sets ``pArAccountId`` +
``pArActivityDate``; if a prior left-click set ``pArTransferId`` to some
unrelated value, that value silently filters Transactions on top of the
account-day intent, narrowing it past what the user expected.

These tests don't click anything — they exercise the **filter wiring**
directly via QuickSight's URL-fragment parameter syntax (``#p.<name>=<v>``).
URL fragments and ``SetParametersOperation`` write to the same param
store, so URL-fragment results predict the drill-action's behavior for
the same value shape.

What we validate here:

1. **Premise** — with a deterministically chosen unrelated ``transfer_id``
   set alongside ``pArAccountId`` + ``pArActivityDate``, Transactions
   narrows below the account-day baseline. (If this fails, stale params
   don't actually suppress rows in our seed and there's no bug to fix.)
2. **Empty-fragment reset** — setting ``#p.pArTransferId=`` (empty value)
   alongside the account-day pair restores the baseline. Tells us
   whether a bare empty value resets a SINGLE_VALUED string param to its
   declared default ``[]`` — the K.2.0 spike's central question for the
   URL-fragment code path.
"""

from __future__ import annotations

from urllib.parse import quote

import pytest

from quicksight_gen.account_recon.constants import (
    P_AR_ACCOUNT,
    P_AR_ACTIVITY_DATE,
    P_AR_TRANSFER,
)

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
def hygiene_values(cfg) -> dict:
    """Pick deterministic data for the hygiene scenario.

    Requirements:
      - ``account_day``: an (account_id, exception_date) from
        ``ar_unified_exceptions`` whose Transactions detail has at
        least 2 rows on that date — gives the baseline assertion
        room to demonstrate narrowing without going to 0.
      - ``unrelated_transfer_id``: a transfer_id that is **not** any
        of the legs on that account-day. Setting it as a stale param
        should drive the Transactions count to 0 (or at least below
        the baseline), because the AND of (account=Y, date=Z,
        transfer=X) is empty.
    """
    if not cfg.demo_database_url:
        pytest.skip("demo_database_url required to look up hygiene values")
    import psycopg2

    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        with conn.cursor() as cur:
            # Find an (account_id, exception_date) from the unified
            # exceptions matview that has ≥ 2 transactions on that
            # date. Order by leg count desc so the assertion has the
            # most slack.
            cur.execute(
                """
                SELECT
                    u.account_id,
                    u.exception_date,
                    COUNT(*) AS leg_count
                FROM ar_unified_exceptions u
                JOIN transactions t
                  ON t.account_id = u.account_id
                 AND t.posted_at::date = u.exception_date::date
                WHERE u.account_id IS NOT NULL
                  AND u.exception_date IS NOT NULL
                GROUP BY u.account_id, u.exception_date
                HAVING COUNT(*) >= 2
                ORDER BY COUNT(*) DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if not row:
                pytest.skip(
                    "No (account_id, exception_date) in ar_unified_exceptions "
                    "has >= 2 transactions on that date — cannot establish "
                    "a baseline that demonstrates narrowing."
                )
            account_id, exception_date, leg_count = row
            # Transactions filters pArActivityDate against `posted_date`,
            # which is `TO_CHAR(posted_at, 'YYYY-MM-DD')`. Match that
            # exact format — full ISO timestamps may not coerce
            # correctly across all checks/dates.
            activity_date_str = (
                exception_date.date().isoformat()
                if hasattr(exception_date, "date") else exception_date.isoformat()
            )

            # Find a transfer_id from a *different* account-day so it
            # is guaranteed not to overlap. The AND of (this account,
            # this date, that unrelated transfer) is empty by
            # construction.
            cur.execute(
                """
                SELECT transfer_id
                FROM transactions
                WHERE transfer_id IS NOT NULL
                  AND NOT (account_id = %s AND posted_at::date = %s::date)
                LIMIT 1
                """,
                (account_id, exception_date),
            )
            row = cur.fetchone()
            if not row:
                pytest.skip(
                    "No unrelated transfer_id found — cannot demonstrate "
                    "stale-param leak."
                )
            unrelated_transfer_id = row[0]
    finally:
        conn.close()

    return {
        "account_id": account_id,
        "activity_date": activity_date_str,
        "leg_count": leg_count,
        "unrelated_transfer_id": unrelated_transfer_id,
    }


def _embed(qs_client, account_id, ar_dashboard_id) -> str:
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


def _count_with_params(
    qs_client, account_id, ar_dashboard_id, page_timeout, params: dict,
    screenshot_name: str,
) -> int:
    """Generate a fresh embed URL with the given param fragment, load
    it, and return the Transactions row count."""
    fragment = "&".join(
        f"p.{k}={quote(v)}" for k, v in params.items()
    )
    url = _embed(qs_client, account_id, ar_dashboard_id) + "#" + fragment
    with webkit_page(headless=True) as page:
        page.goto(url, timeout=page_timeout)
        wait_for_dashboard_loaded(page, timeout_ms=page_timeout)
        count = _transactions_count(page, page_timeout)
        screenshot(page, screenshot_name, subdir="account_recon")
    return count


def test_account_day_baseline(
    qs_client, account_id, ar_dashboard_id, page_timeout, hygiene_values,
):
    """Baseline: setting only pArAccountId + pArActivityDate scopes
    Transactions to the account-day. This is the row count the spike's
    reset semantics aim to preserve even when an earlier click left
    pArTransferId set to an unrelated value."""
    count = _count_with_params(
        qs_client, account_id, ar_dashboard_id, page_timeout,
        params={
            P_AR_ACCOUNT.name: hygiene_values["account_id"],
            P_AR_ACTIVITY_DATE.name: hygiene_values["activity_date"],
        },
        screenshot_name="cross_sheet_hygiene_baseline_account_day",
    )
    assert count >= 2, (
        f"Account-day baseline ({hygiene_values['account_id']!r}, "
        f"{hygiene_values['activity_date']!r}) returned {count} rows; "
        f"the fixture queried for >= 2. The seed may have shifted, or "
        f"the Transactions filter on (account, date) may be mis-wired."
    )


def test_stale_pArTransferId_suppresses_account_day(
    qs_client, account_id, ar_dashboard_id, page_timeout, hygiene_values,
):
    """Premise check: a stale pArTransferId set alongside the account-day
    pair narrows Transactions to (effectively) zero, because the AND of
    (account, date, unrelated transfer) is empty by construction.

    If this fails, stale params don't actually suppress rows in our seed
    — meaning the K.2 cross-sheet refactor doesn't have a real bug to
    fix and we can pause that work. If it passes (the expected
    outcome), it both validates the bug and gives us the paired-baseline
    that ``test_empty_pArTransferId_fragment_resets`` compares against.
    """
    baseline = _count_with_params(
        qs_client, account_id, ar_dashboard_id, page_timeout,
        params={
            P_AR_ACCOUNT.name: hygiene_values["account_id"],
            P_AR_ACTIVITY_DATE.name: hygiene_values["activity_date"],
        },
        screenshot_name="cross_sheet_hygiene_paired_baseline",
    )
    leaked = _count_with_params(
        qs_client, account_id, ar_dashboard_id, page_timeout,
        params={
            P_AR_ACCOUNT.name: hygiene_values["account_id"],
            P_AR_ACTIVITY_DATE.name: hygiene_values["activity_date"],
            P_AR_TRANSFER.name: hygiene_values["unrelated_transfer_id"],
        },
        screenshot_name="cross_sheet_hygiene_stale_param_leak",
    )
    assert leaked < baseline, (
        f"Stale pArTransferId={hygiene_values['unrelated_transfer_id']!r} "
        f"did not narrow Transactions ({leaked} >= baseline {baseline}). "
        f"Either the seed gave us a transfer_id that happens to overlap "
        f"the account-day, or the transfer-id filter on Transactions "
        f"isn't actually being applied. Check the fixture query."
    )


def test_sentinel_pArTransferId_fragment_resets_via_calc_field(
    qs_client, account_id, ar_dashboard_id, page_timeout, hygiene_values,
):
    """Phase K.2 spike outcome: with ``fg-ar-drill-transfer-on-txn``
    rewired to a calc-field-based ``PASS`` filter (see
    ``_build_drill_helper_calculated_fields`` in analysis.py) and the
    parameter declaring ``__ALL__`` as its default, a URL-fragment
    write of the sentinel ``#p.pArTransferId=__ALL__`` behaves as ALL
    — the Transactions table returns the account-day baseline.

    Why a sentinel and not empty/null:
      - Parameter-bound CategoryFilters
        (``CustomFilterConfiguration { EQUALS, ParameterName,
        NullOption: ALL_VALUES }``) match the literal empty string
        rather than treating empty as "no filter". (Original K.2.0
        finding.)
      - Calc-field expressions that test
        ``coalesce(${param}, '') = ''`` work correctly for the URL-
        fragment empty-write code path but FAIL for the
        ``SetParametersOperation`` code path, even when the operation
        sends ``StringValues:[""]``. (K.2 spike (a) — manually
        verified.) The drill-action path apparently delivers the
        parameter value to the calc field in a form coalesce can't
        simplify to '' — possibly NULL in a way calc fields don't
        recognize, possibly something else.
      - A real-string sentinel (``__ALL__``) sidesteps both
        questions: every code path can write a real string with
        confidence, and the calc field test is a plain string
        comparison.

    The sentinel must also be the parameter's declared default so the
    never-touched fresh-load state behaves as ALL.
    """
    baseline = _count_with_params(
        qs_client, account_id, ar_dashboard_id, page_timeout,
        params={
            P_AR_ACCOUNT.name: hygiene_values["account_id"],
            P_AR_ACTIVITY_DATE.name: hygiene_values["activity_date"],
        },
        screenshot_name="cross_sheet_hygiene_reset_baseline",
    )
    reset_attempt = _count_with_params(
        qs_client, account_id, ar_dashboard_id, page_timeout,
        params={
            P_AR_ACCOUNT.name: hygiene_values["account_id"],
            P_AR_ACTIVITY_DATE.name: hygiene_values["activity_date"],
            P_AR_TRANSFER.name: "__ALL__",
        },
        screenshot_name="cross_sheet_hygiene_sentinel_fragment_resets",
    )
    assert reset_attempt == baseline, (
        f"Sentinel pArTransferId=__ALL__ URL fragment produced "
        f"{reset_attempt} rows; expected to match the account-day "
        f"baseline of {baseline}. Either the calc-field expression "
        f"no longer treats __ALL__ as PASS, the parameter default "
        f"wasn't __ALL__ either (so the calc field thinks the param "
        f"is something else), or the filter is no longer reading the "
        f"calc field column."
    )
