"""Postgres-direct scenario coverage for the Daily Statement sheet (Phase I.2.C).

The Daily Statement sheet (Phase I.2.A) takes ``(account_id, balance_date)``
parameters and renders a one-account-day reconciliation view: opening balance,
debits, credits, closing balance (stored vs recomputed), drift, and the
underlying legs. The Data Integration Handbook companion walkthrough
(Phase I.2.E) will use *three worked examples* an analyst can paste straight
into the dashboard:

1. **Clean reconciling day** — drift is zero, account is in good standing.
2. **Drift day** — stored balance disagrees with recomputed balance.
3. **Overdraft day** — closing balance is negative.

The walkthrough quotes specific dollar amounts; if the generator changes the
planted deltas, both the doc and the assertions below need to update in lockstep.
These tests run against the deployed Postgres so a stale seed (or a generator
change that shifts byte-output but not these assertions) surfaces immediately
when the API e2e suite runs.

The (account, days_ago) pairs are anchored to the existing ``_*_PLANT``
constants in ``account_recon/demo_data.py`` so a generator edit that drops a
plant breaks these tests loudly.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection


pytestmark = [pytest.mark.e2e, pytest.mark.api]


# ---------------------------------------------------------------------------
# Worked examples for the Phase I.2.E handbook walkthrough.
#
# Anchored to existing _*_PLANT constants where possible so a generator change
# (drop a plant, rename an account) breaks these tests rather than silently
# rotting the doc. The "clean" example picks a GL account on a day when no
# plant fires — gl-1010 (Cash & Due From FRB) has a ledger-drift plant at
# days_ago=14, so days_ago=1 is plant-free and the daily ACH sweep gives it
# real activity to reconcile against. (Customer DDAs were tried first but the
# ACH-only customers carry continuously-negative balances from outflow with
# no compensating deposits — see I.4 audit notes.)
# ---------------------------------------------------------------------------

CLEAN_ACCOUNT_ID = "gl-1010-cash-due-frb"
CLEAN_DAYS_AGO = 1  # yesterday — gl-1010's drift plant fires at days_ago=14

DRIFT_ACCOUNT_ID = "cust-900-0001-bigfoot-brews"
# Days_ago + planted delta come from _SUBLEDGER_DRIFT_PLANT (kept in sync
# below via _drift_plant_for).

OVERDRAFT_ACCOUNT_ID = "cust-900-0002-sasquatch-sips"
# Days_ago comes from _OVERDRAFT_PLANT.


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_conn(cfg):
    if not cfg.demo_database_url:
        pytest.skip(
            "demo_database_url not configured; "
            "Daily Statement scenario tests need direct DB access"
        )
    psycopg2 = pytest.importorskip("psycopg2")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Mirror of the SQL inside build_daily_statement_summary_dataset, narrowed to
# a single (account_id, balance_date). Kept inline (rather than imported from
# the dataset builder) so the test stays self-contained and a future SQL
# divergence surfaces here as a maintenance signal.
_DAILY_STATEMENT_SUMMARY_SQL = """\
WITH account_days AS (
    SELECT
        db.account_id,
        db.balance_date,
        db.balance                                                 AS closing_balance_stored,
        LAG(db.balance) OVER (
            PARTITION BY db.account_id ORDER BY db.balance_date
        )                                                          AS opening_balance
    FROM daily_balances db
    WHERE db.account_id = %(account_id)s
),
today_flows AS (
    SELECT
        t.account_id,
        t.balance_date,
        SUM(CASE WHEN t.signed_amount > 0 THEN t.signed_amount ELSE 0 END)
                                                                   AS total_debits,
        SUM(CASE WHEN t.signed_amount < 0 THEN -t.signed_amount ELSE 0 END)
                                                                   AS total_credits,
        SUM(t.signed_amount)                                        AS net_flow,
        COUNT(*)                                                    AS leg_count
    FROM transactions t
    WHERE t.status <> 'failed'
      AND t.account_id   = %(account_id)s
      AND t.balance_date = %(balance_date)s
    GROUP BY t.account_id, t.balance_date
)
SELECT
    COALESCE(ad.opening_balance, 0)                                AS opening_balance,
    COALESCE(f.total_debits, 0)                                    AS total_debits,
    COALESCE(f.total_credits, 0)                                   AS total_credits,
    ad.closing_balance_stored,
    COALESCE(ad.opening_balance, 0) + COALESCE(f.net_flow, 0)      AS closing_balance_recomputed,
    ad.closing_balance_stored
        - (COALESCE(ad.opening_balance, 0) + COALESCE(f.net_flow, 0)) AS drift,
    COALESCE(f.leg_count, 0)                                        AS leg_count
FROM account_days ad
LEFT JOIN today_flows f
    ON  f.account_id   = ad.account_id
    AND f.balance_date = ad.balance_date
WHERE ad.balance_date = %(balance_date)s
"""


def _summary_row(conn: "PgConnection", account_id: str, balance_date: date):
    """Return the Daily Statement summary row for one (account, date), or None."""
    with conn.cursor() as cur:
        cur.execute(
            _DAILY_STATEMENT_SUMMARY_SQL,
            {"account_id": account_id, "balance_date": balance_date},
        )
        return cur.fetchone()


def _drift_plant_for(account_id: str) -> tuple[int, Decimal]:
    """Return ``(days_ago, planted_delta)`` for ``account_id`` from
    ``_SUBLEDGER_DRIFT_PLANT``. Raises if the account isn't planted."""
    from quicksight_gen.apps.account_recon.demo_data import _SUBLEDGER_DRIFT_PLANT

    for sid, days_ago, delta_str in _SUBLEDGER_DRIFT_PLANT:
        if sid == account_id:
            return days_ago, Decimal(delta_str)
    raise AssertionError(
        f"{account_id} is not in _SUBLEDGER_DRIFT_PLANT — drift example "
        f"needs an anchor plant"
    )


def _overdraft_plant_for(account_id: str) -> int:
    """Return ``days_ago`` for ``account_id`` from ``_OVERDRAFT_PLANT``."""
    from quicksight_gen.apps.account_recon.demo_data import _OVERDRAFT_PLANT

    for sid, days_ago, _amt, _memo in _OVERDRAFT_PLANT:
        if sid == account_id:
            return days_ago
    raise AssertionError(
        f"{account_id} is not in _OVERDRAFT_PLANT — overdraft example "
        f"needs an anchor plant"
    )


# ---------------------------------------------------------------------------
# Scenario coverage
# ---------------------------------------------------------------------------

class TestDailyStatementScenarioCoverage:
    """Three worked examples must surface in the deployed Daily Statement view.

    These anchor the Phase I.2.E handbook walkthrough — if any test fails the
    walkthrough's screenshots or pasted parameter values won't reconcile.
    """

    def test_clean_reconciling_day_cash_due_frb(self, pg_conn):
        """Cash & Due From FRB, yesterday: drift=0, ≥1 leg, closing not overdrawn."""
        balance_date = date.today() - timedelta(days=CLEAN_DAYS_AGO)
        row = _summary_row(pg_conn, CLEAN_ACCOUNT_ID, balance_date)
        assert row is not None, (
            f"No daily_balances row for {CLEAN_ACCOUNT_ID} on {balance_date} — "
            "reseed (`quicksight-gen demo apply --all`) and retry"
        )
        opening, debits, credits, closing_stored, closing_recomputed, drift, legs = row
        assert legs >= 1, (
            f"Clean walkthrough day needs ≥1 transaction leg; got {legs}. "
            "If the daily ACH sweep no longer touches gl-1010 on day -1, "
            "pick a different CLEAN_DAYS_AGO."
        )
        assert drift == Decimal("0"), (
            f"gl-1010's ledger-drift plant fires at days_ago=14, not "
            f"days_ago={CLEAN_DAYS_AGO}; expected drift=0, got {drift}"
        )
        assert closing_stored >= Decimal("0"), (
            f"Clean example shouldn't be overdrawn; got closing={closing_stored}. "
            "Pick a different account or day."
        )

    def test_drift_day_bigfoot_brews(self, pg_conn):
        """Bigfoot Brews drift plant materializes as drift = planted delta."""
        days_ago, planted_delta = _drift_plant_for(DRIFT_ACCOUNT_ID)
        balance_date = date.today() - timedelta(days=days_ago)
        row = _summary_row(pg_conn, DRIFT_ACCOUNT_ID, balance_date)
        assert row is not None, (
            f"No daily_balances row for {DRIFT_ACCOUNT_ID} on {balance_date} — "
            "reseed and retry"
        )
        _opening, _debits, _credits, _closing_stored, _closing_recomp, drift, _legs = row
        assert drift == planted_delta, (
            f"Expected planted drift {planted_delta} for "
            f"{DRIFT_ACCOUNT_ID} on {balance_date}; got {drift}. "
            "If the plant amount changed, update the handbook walkthrough too."
        )

    def test_overdraft_day_sasquatch_sips(self, pg_conn):
        """Sasquatch Sips overdraft plant: closing<0, drift=0 (real txn drove it)."""
        days_ago = _overdraft_plant_for(OVERDRAFT_ACCOUNT_ID)
        balance_date = date.today() - timedelta(days=days_ago)
        row = _summary_row(pg_conn, OVERDRAFT_ACCOUNT_ID, balance_date)
        assert row is not None, (
            f"No daily_balances row for {OVERDRAFT_ACCOUNT_ID} on {balance_date} — "
            "reseed and retry"
        )
        _opening, _debits, _credits, closing_stored, _closing_recomp, drift, _legs = row
        assert closing_stored < Decimal("0"), (
            f"Expected overdraft (closing<0) for {OVERDRAFT_ACCOUNT_ID} on "
            f"{balance_date}; got closing={closing_stored}"
        )
        assert drift == Decimal("0"), (
            f"Overdraft is a balance condition, not a drift — expected drift=0, "
            f"got {drift}. The overdraft plant emits a real outbound txn so the "
            "stored and recomputed balances should still agree."
        )
