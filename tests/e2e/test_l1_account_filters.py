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


def test_daily_statement_role_dropdown_narrows_account_options(
    l1_dashboard_driver,
):
    """AA.B.1 — the Daily Statement Role dropdown narrows the Account
    dropdown's options via the ``pL1DsRole`` dataset param bridged
    into ``DS_L1_ACCOUNTS``.

    Shape: open Daily Statement, snapshot the unfiltered Account
    options, pick a Role with a known-narrowable account universe,
    snapshot again. The narrowed set must be a strict subset of the
    full set AND the full set must be larger than the narrowed set
    (otherwise the cascade is a no-op and the test silently passes).

    Data-agnostic: we don't hardcode role names — we read the actual
    Role dropdown options and iterate the role list looking for one
    that produces a narrowable cascade. The L2 instance plants several
    account_roles per AA.B.1's seed contract, so at least one role
    must narrow.
    """
    driver, dashboard_arg = l1_dashboard_driver
    driver.open(dashboard_arg, sheet="Daily Statement")

    full_account_options = driver.filter_options("Account")
    full_count = len(full_account_options)
    assert full_count >= 2, (
        f"Daily Statement should have ≥2 Account options on first "
        f"load (show-all sentinel default); got {full_count}: "
        f"{full_account_options[:5]}..."
    )

    role_options = driver.filter_options("Role")
    assert len(role_options) >= 2, (
        f"Daily Statement Role dropdown should expose ≥2 roles "
        f"(otherwise the cascade is degenerate); got {role_options}"
    )

    # Try each role until we find one that narrows. At least one must
    # — the seed plants multiple roles each with ≥1 account.
    narrowed_to = None
    for role in role_options:
        driver.pick_filter("Role", [role])
        candidates = driver.filter_options("Account")
        if len(candidates) < full_count:
            narrowed_to = (role, candidates)
            break

    assert narrowed_to is not None, (
        f"No Role narrowed the Account dropdown — the AA.B.1 cascade "
        f"is broken. Full Account count: {full_count}. Tried roles: "
        f"{role_options}."
    )
    role, narrowed_options = narrowed_to
    driver.screenshot()
    # Subset check — every narrowed option must be in the full set.
    full_set = set(full_account_options)
    extras = [o for o in narrowed_options if o not in full_set]
    assert not extras, (
        f"Role={role!r} narrowed Account to options not in the full "
        f"universe (impossible under correct cascade): {extras}"
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

    # The Daily Statement table's title may vary by L2; the per-account
    # Daily Statement summary table is the canonical visual carrying
    # the post-pick rows. Wait then count.
    target_visual = "Daily Statement"
    try:
        driver.wait_loaded(target_visual)
    except Exception:
        # Some L2 instances may title the visual differently. Use
        # whichever visual on the sheet has rows post-pick.
        target_visual = driver.visual_titles()[0]
        driver.wait_loaded(target_visual)

    rows = driver.table_rows(target_visual)
    driver.screenshot()
    assert len(rows) > 0, (
        f"After picking Account={picked!r}, the Daily Statement "
        f"table should render ≥1 row. Got {len(rows)}. This is "
        f"the AA.E.2 silent-empty regression — Daily Statement's "
        f"Account dropdown must bind to 'account_display' for the "
        f"WHERE clause to match (JSON pin: "
        f"test_aa_e_2_daily_statement_account_dropdown_binds_display_column)."
    )
