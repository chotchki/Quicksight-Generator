"""Browser tests: AA.B (Daily Statement Role cascade) + AA.E (account
search-by-name-AND-id) — parametrized over ``[qs, app2]`` via
``l1_dashboard_driver``.

Pairs naturally with ``test_l1_filters.py`` (which covers the universal
date filter + the Today's Exceptions Check Type dropdown). This file
exists separately so the Daily Statement / Account-display contracts
can be triaged independently — the Daily Statement Account dropdown
silently broke between AA.E.2 and AA.E.3 because the AA.E.2 sweep
missed the direct ``add_parameter_dropdown`` callsite (the JSON pin
``test_aa_e_2_daily_statement_account_dropdown_binds_display_column``
catches the wiring; this file catches the runtime symptom — picked
account → table renders rows).

Test shapes follow the X.2.q DashboardDriver protocol; both renderers
exercise the same SQL pushdown (``DS_L1_ACCOUNTS`` cascade for the
Role dropdown; ``_account_display_clause`` for the display-format
WHERE), so a parity gap = a real wiring divergence, not a flavour
choice.
"""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.browser]


# AA.B — Daily Statement Role cascade --------------------------------------


def test_daily_statement_role_narrows_posted_money_records_table(
    l1_dashboard_driver,
):
    """AA.B.1 — picking a Role narrows the Posted Money Records table to
    only accounts matching that role, via the ``pL1DsRole`` dataset
    param bridged into the per-account-day matview.

    First-revision-of-this-test bug (caught on chain @ 3cc704c): the
    original assertion was "Role narrows the *Account dropdown's*
    options". That doesn't work in either renderer — QS bakes dropdown
    option lists at dashboard load (snapshot, not live re-query;
    standing quirk ``project_qs_url_parameter_no_control_sync``-adjacent)
    and App2 emits `filter_specs` once per sheet GET. The cascade
    *does* fire — but it narrows the *data* in visuals that bind both
    params (Posted Money Records), not the dropdown itself. Test
    re-shaped to assert the data narrowing, which is what AA.B.1
    actually delivers.

    Shape: open Daily Statement, pick the show-all default Account and
    no Role (table shows everything), snapshot the table row count,
    pick a Role with ≥1 matching account, assert the table narrowed.

    Data-agnostic: we read the actual Role dropdown options and try
    each until one narrows the table.
    """
    driver, dashboard_arg = l1_dashboard_driver
    driver.open(dashboard_arg, sheet="Daily Statement")
    # "Posted Money Records" is the per-account-day detail table on
    # Daily Statement (5 KPIs + this table; see L1 app
    # `apps/l1_dashboard/app.py::populate_daily_statement_sheet`).
    target_visual = "Posted Money Records"
    driver.wait_loaded(target_visual)

    role_options = driver.filter_options("Role")
    assert len(role_options) >= 2, (
        f"Daily Statement Role dropdown should expose ≥2 roles "
        f"(otherwise the cascade is degenerate); got {role_options}"
    )

    # Pick an Account first to make the table non-empty (the sentinel
    # default leaves it empty on first load — Daily Statement requires
    # an Account to be picked before any data shows).
    account_options = driver.filter_options("Account")
    assert account_options, "Account dropdown returned no options"
    driver.pick_filter("Account", [account_options[0]])
    driver.wait_loaded(target_visual)
    before = driver.table_row_count(target_visual)
    if before == 0:
        pytest.skip(
            "Posted Money Records empty after picking the first Account "
            f"({account_options[0]!r}) — the deployed L2's seed plants "
            "no posted rows for this account-day. Cascade narrowing has "
            "nothing to shrink. (Pre-condition failure, not an AA.B.1 "
            "regression — covered by per-role-coverage seed tests.)"
        )

    # Try each Role until one narrows the table (different count OR
    # different first-row content vs the unfiltered pick).
    narrowed = False
    for role in role_options:
        driver.pick_filter("Role", [role])
        driver.wait_loaded(target_visual)
        after = driver.table_row_count(target_visual)
        if after != before:
            narrowed = True
            break

    driver.screenshot()
    assert narrowed, (
        f"No Role changed the Posted Money Records row count — the "
        f"AA.B.1 Role→DS_L1_ACCOUNTS data cascade is broken. "
        f"Pre-Role rows: {before}. Tried roles: {role_options}."
    )


# AA.E — Account dropdown shows "name (id)" form ---------------------------


@pytest.mark.parametrize("sheet_name", [
    "Drift",
    "Overdraft",
    "Limit Breach",
    "Today's Exceptions",
    "Daily Statement",
    "Transactions",
])
def test_account_dropdown_shows_display_form(
    l1_dashboard_driver, sheet_name: str,
):
    """AA.E.2 — every L1 Account dropdown advertises options in the
    ``"<name> (<id>)"`` display form (substring-searchable by either
    name or id), not the bare-id form.

    Detect the shape by reading the options and asserting ≥1 option
    matches the ``"... (...)"`` pattern — a parenthesized suffix that
    the bare-id form ('account-001', 'merchant-12') doesn't carry.

    Mirrors AA.E.1's hybrid decision (concat in dropdowns, two-column
    in tables). The 6 sheets parametrized here are the 6 L1 sheets
    that carry an Account picker (Pending Aging + Unbundled Aging are
    structurally identical to the others and excluded for runtime
    parsimony — the same ``options_column="account_display"`` flip
    applies, pinned at JSON level by AA.E.2's unit tests).
    """
    driver, dashboard_arg = l1_dashboard_driver
    driver.open(dashboard_arg, sheet=sheet_name)

    options = driver.filter_options("Account")
    assert options, (
        f"{sheet_name!r}: Account dropdown returned no options. "
        f"Companion dataset (DS_L1_ACCOUNTS) is empty? Sentinel "
        f"semantics broken?"
    )
    # Match the "Name (id)" shape: at least one option must contain
    # " (" followed by ")" at the end. Bare-id options ("external-001",
    # "merchant-12") have no parens.
    display_form = [o for o in options if " (" in o and o.endswith(")")]
    assert display_form, (
        f"{sheet_name!r}: Account dropdown options don't carry the "
        f"display form '<name> (<id>)' — AA.E.2 regression. "
        f"First 3 options: {options[:3]}"
    )


def test_daily_statement_picked_account_narrows_table(l1_dashboard_driver):
    """AA.E.2 fix + AA.B.4 — after picking an Account from the Daily
    Statement dropdown, the per-account-day Daily Statement table
    surfaces rows for that account.

    This was the silent symptom of the AA.E.2 miss: the dropdown
    bound bare ``account_id`` but the WHERE clause expected
    ``(account_name || ' (' || account_id || ')')`` — every pick
    resulted in an empty table. Test pins the fix end-to-end through
    both renderers.

    Data-agnostic: we pick the *first* Account option (whatever the
    seed produced) and assert the table has ≥1 row after pick. The
    sentinel default leaves the table empty on first load, so the
    delta (pre=0 → post≥1) is the cascade signal.
    """
    driver, dashboard_arg = l1_dashboard_driver
    driver.open(dashboard_arg, sheet="Daily Statement")

    options = driver.filter_options("Account")
    assert options, (
        "Daily Statement Account dropdown returned no options — "
        "DS_L1_ACCOUNTS companion empty?"
    )
    picked = options[0]
    driver.pick_filter("Account", [picked])

    # "Posted Money Records" is the canonical per-account-day detail
    # table on Daily Statement (see `apps/l1_dashboard/app.py::
    # populate_daily_statement_sheet`). The sheet's 5 KPIs surface
    # the day's walk; this table is the row-by-row support. Original
    # version of this test looked for a visual literally titled
    # "Daily Statement" (the sheet name, NOT a visual title) and
    # fell back to `visual_titles()[0]` (an Opening Balance KPI) —
    # both wrong.
    target_visual = "Posted Money Records"
    driver.wait_loaded(target_visual)

    rows = driver.table_rows(target_visual)
    driver.screenshot()
    assert len(rows) > 0, (
        f"After picking Account={picked!r}, the Posted Money Records "
        f"table should render ≥1 row. Got {len(rows)}. This is "
        f"the AA.E.2 silent-empty regression — Daily Statement's "
        f"Account dropdown must bind to 'account_display' for the "
        f"WHERE clause to match (JSON pin: "
        f"test_aa_e_2_daily_statement_account_dropdown_binds_display_column)."
    )
