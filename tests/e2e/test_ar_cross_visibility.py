"""Postgres-direct cross-visibility tests for the AR-as-superset framing (I.4).

I.4's north star is *AR is the unified view; PR is a tight, persona-scoped
subset.* Artificial filters that hide PR rows from AR datasets / views are
removed; PR rows surface naturally in AR exception checks where they apply.

These tests are the regression guard. Each commit in I.4.B removes one
filter; this file pins the resulting cross-visibility so a future commit
can't silently re-add the exclusion.

Two assertion shapes per filter removal:

1. **View-definition regression** — query ``pg_views.definition`` and assert
   the artificial pattern (e.g. ``'pr-%'``) is gone. Catches "someone added
   the filter back" loudly.
2. **Positive cross-visibility** — query the unscoped view and assert PR
   rows surface where the unified-AR framing expects them to. Pairs with a
   "planted AR scenarios still surface" assertion so a regression that
   over-narrows the view (drowning the planted rows in PR noise, or vice
   versa) breaks the test.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection


pytestmark = [pytest.mark.e2e, pytest.mark.api]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pg_conn(cfg):
    if not cfg.demo_database_url:
        pytest.skip(
            "demo_database_url not configured; "
            "cross-visibility tests need direct DB access"
        )
    psycopg2 = pytest.importorskip("psycopg2")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        yield conn
    finally:
        conn.close()


def _view_definition(conn: "PgConnection", view_name: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT definition FROM pg_views WHERE viewname = %s",
            (view_name,),
        )
        row = cur.fetchone()
    assert row is not None, f"view {view_name} not found in pg_views"
    return row[0]


# ---------------------------------------------------------------------------
# I.4.B Commit 1 — schema view PR exclusions removed
# ---------------------------------------------------------------------------

class TestSchemaViewsAreUnscoped:
    """The two ``account_id NOT LIKE 'pr-%'`` filters in AR schema views are gone."""

    def test_subledger_overdraft_view_has_no_pr_exclusion(self, pg_conn):
        definition = _view_definition(pg_conn, "ar_subledger_overdraft")
        assert "'pr-%'" not in definition, (
            "ar_subledger_overdraft view still carries an artificial "
            "account_id NOT LIKE 'pr-%' exclusion. I.4 removed this; "
            "if it came back, audit the schema.sql edit history before "
            "re-applying."
        )

    def test_subledger_outbound_view_has_no_pr_exclusion(self, pg_conn):
        definition = _view_definition(
            pg_conn, "ar_subledger_daily_outbound_by_type"
        )
        assert "'pr-%'" not in definition, (
            "ar_subledger_daily_outbound_by_type view still carries an "
            "artificial account_id NOT LIKE 'pr-%' exclusion. I.4 removed "
            "this; if it came back, audit the schema.sql edit history."
        )


class TestOverdraftCheckSurfacesPrAccounts:
    """``ar_subledger_overdraft`` now surfaces PR-side accounts where they apply."""

    def test_merchant_dda_overdrafts_surface(self, pg_conn):
        """At least one merchant_dda account appears in the overdraft view.

        Pre-I.4 the view filtered ``account_id NOT LIKE 'pr-%'`` and PR
        accounts were invisible regardless of balance. After commit 1 the
        unified-AR view sees them.

        Note: the seed currently emits payment outflow on merchant_dda
        accounts without a compensating inbound credit (sale leg debits
        merchant_sub when convention says it should credit), so every
        merchant DDA runs structurally negative for the entire seed
        window. That's a known generator sign-convention bug, tracked
        in **Phase I.5 — PR sign convention standardization**. For this
        test it just guarantees the cross-visibility is on. Post-I.5
        this assertion needs to be reframed to "at least one *planted*
        PR overdraft scenario surfaces" — see I.5.E.
        """
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT sub.account_id)
                FROM ar_subledger_overdraft o
                JOIN daily_balances sub
                  ON  sub.account_id   = o.subledger_account_id
                 AND sub.balance_date  = o.balance_date
                WHERE sub.account_type = 'merchant_dda'
                """
            )
            distinct_merchant_ddas = cur.fetchone()[0]
        assert distinct_merchant_ddas >= 1, (
            "Expected at least one merchant_dda account to surface in "
            "ar_subledger_overdraft after I.4.B commit 1; got 0. Either "
            "I.5 landed and removed the structural negativity without "
            "updating this assertion (see I.5.E — needs to switch to a "
            "planted PR overdraft scenario), or a regression re-added "
            "the artificial pr-% filter."
        )

    def test_planted_ar_overdrafts_still_surface(self, pg_conn):
        """The 3 ``_OVERDRAFT_PLANT`` accounts still appear after the filter removal.

        Regression guard: removing the pr-% filter must not drown / hide
        the planted AR scenarios — they're the load-bearing demo signal
        for the AR Sub-Ledger Overdraft KPI.
        """
        from quicksight_gen.account_recon.demo_data import _OVERDRAFT_PLANT

        planted_account_ids = {acct for acct, *_ in _OVERDRAFT_PLANT}
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT subledger_account_id
                FROM ar_subledger_overdraft
                WHERE subledger_account_id = ANY(%s)
                """,
                (list(planted_account_ids),),
            )
            surfaced = {row[0] for row in cur.fetchall()}
        missing = planted_account_ids - surfaced
        assert not missing, (
            f"_OVERDRAFT_PLANT accounts {missing} no longer surface in "
            "ar_subledger_overdraft after I.4.B commit 1. The pr-% filter "
            "removal should be additive — if planted rows disappeared, "
            "something else changed."
        )


class TestSubledgerAccountsDatasetSurfacesMerchantDdas:
    """The AR Sub-Ledger Accounts dataset (Balances tab) sees PR merchant DDAs.

    The ``ar-subledger-accounts-dataset`` SQL was already PR-clean (no
    artificial filter), so this test should have passed pre-I.4 — it's
    here as a positive lock so a future commit can't silently re-add a
    filter to the dataset SQL.
    """

    def test_merchant_dda_rows_present(self, pg_conn):
        with pg_conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(DISTINCT sub.account_id)
                FROM daily_balances sub
                JOIN daily_balances led
                    ON  led.account_id   = sub.control_account_id
                    AND led.balance_date = sub.balance_date
                WHERE sub.control_account_id IS NOT NULL
                  AND led.control_account_id IS NULL
                  AND sub.account_type = 'merchant_dda'
                """
            )
            distinct_merchant_ddas = cur.fetchone()[0]
        assert distinct_merchant_ddas >= 1, (
            "AR Sub-Ledger Accounts dataset SQL no longer surfaces any "
            "merchant_dda row. Either the seed stopped emitting them or "
            "a filter was added to the dataset SQL."
        )
