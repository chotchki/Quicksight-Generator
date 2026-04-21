"""Postgres-direct semantics tests for the views feeding AR exceptions.

Phase K.1 collapsed the per-check KPI surface into a single unified
exceptions dataset (UNION ALL over the 14 underlying views). The views
themselves still drive the dashboard — Today's Exceptions reads them
through ``ar_unified_exceptions``; Exceptions Trends reads the rollup
views directly. These tests pin the upstream contracts so a regression
in any view immediately breaks here, before it silently drops rows from
the unified surface.

Two contracts per check:

1. View scope: the view's row set matches the semantic scope its name
   promises (e.g., ar_subledger_overdraft has WHERE balance < 0 baked
   in, so as_displayed == expected_scope). Catches a regression that
   widens or narrows the view definition.

2. Planted-row sanity: each ``_*_PLANT`` constant in
   ``account_recon/demo_data.py`` produces at least its planted rows
   in the corresponding view. For "1 plant = 1 row" checks (limit
   breach, sweep-leg-mismatch, plant-keyed transfers) assert exact
   equality. For sticky scenarios (overdraft, sweep-target / suspense
   non-zero EOD, ACH-orig non-zero) assert ``>= planted_count`` since a
   single incident inflates into N daily rows of running negative /
   non-zero balance.

Runs against the deployed Postgres database (Direct Query mode
mirrors what QuickSight executes). Connection string lives in
``cfg.demo_database_url``.
"""

from __future__ import annotations

from datetime import date, timedelta
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
        pytest.skip("demo_database_url not configured; KPI semantics tests need direct DB access")
    psycopg2 = pytest.importorskip("psycopg2")
    conn = psycopg2.connect(cfg.demo_database_url)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_rows(conn: "PgConnection", sql: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM ({sql}) _sub")
        row = cur.fetchone()
    return int(row[0])


def _planted_count(check_name: str) -> int:
    """Return the size of the ``_*_PLANT`` constant driving ``check_name``."""
    from quicksight_gen.account_recon import demo_data as dd

    plants = {
        "ledger_drift": len(dd._LEDGER_DRIFT_PLANT),
        "subledger_drift": len(dd._SUBLEDGER_DRIFT_PLANT),
        "limit_breach": len(dd._LIMIT_BREACH_PLANT),
        "overdraft": len(dd._OVERDRAFT_PLANT),
        "sweep_target": len(dd._ZBA_SWEEP_FAIL_PLANT),
        "sweep_leg_mismatch": len(dd._ZBA_SWEEP_LEG_MISMATCH_PLANT),
        "ach_orig_skip": len(dd._ACH_SWEEP_SKIP_PLANT),
        "ach_fed_missing": len(dd._ACH_FED_CONFIRMATION_MISSING),
        "card_internal_missing": len(dd._CARD_INTERNAL_MISSING_PLANT),
        "internal_stuck": sum(
            1 for *_, kind, _ in dd._INTERNAL_TRANSFER_PLANT if kind == "stuck"
        ),
        "internal_reversed": sum(
            1 for *_, kind, _ in dd._INTERNAL_TRANSFER_PLANT
            if kind == "reversed_not_credited"
        ),
    }
    return plants[check_name]


# ---------------------------------------------------------------------------
# Per-KPI scope SQL — the SQL behind the KPI count, with any sheet-pinned
# filter applied. Each maps a logical check to (kpi_sql, expected_scope_sql).
# Where the dataset view already encodes the scope (e.g.,
# ar_subledger_overdraft has WHERE balance < 0), kpi_sql == expected_sql
# trivially — the test still runs and would catch a regression that loosens
# the view.
#
# AR scope filter (transfer types) mirrors what build_*_dataset() applies.
# ---------------------------------------------------------------------------

_AR_TXN_TYPES = "('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')"


# ---------------------------------------------------------------------------
# Class 1: KPI scope contracts
# ---------------------------------------------------------------------------

class TestKpiScope:
    """Each view's row count must equal its semantic scope row count.

    Drift views (ar_*_drift) emit healthy + unhealthy rows; consumers
    filter to drift_status='drift'. These tests pin both shapes (view
    SQL and the canonical drift filter) so a regression in either shows
    up immediately.
    """

    def test_ledger_drift_kpi_counts_drift_only(self, pg_conn):
        as_displayed = (
            "SELECT 1 FROM ar_ledger_balance_drift "
            "WHERE (CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END) = 'drift'"
        )
        expected_scope = (
            "SELECT 1 FROM ar_ledger_balance_drift WHERE drift <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0, (
            "Ledger Drift KPI must be non-empty — _LEDGER_DRIFT_PLANT should surface"
        )

    def test_subledger_drift_kpi_counts_drift_only(self, pg_conn):
        as_displayed = (
            "SELECT 1 FROM ar_subledger_balance_drift "
            "WHERE (CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END) = 'drift'"
        )
        expected_scope = (
            "SELECT 1 FROM ar_subledger_balance_drift WHERE drift <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_non_zero_transfers_kpi_scope(self, pg_conn):
        # Dataset SQL (I.4.B Commit 3) filters
        #   net_zero_status='not_net_zero' AND expected_net_zero='expected'
        # so single-leg PR types (sale, external_txn) — which have
        # non-zero net by shape, not by exception — don't false-positive
        # into the KPI. Subtitle promises "transfers whose non-failed
        # legs don't balance out" i.e. net_amount <> 0 over the
        # multi-leg-expected scope.
        as_displayed = (
            "SELECT 1 FROM ar_transfer_summary "
            "WHERE net_zero_status = 'not_net_zero' "
            "  AND expected_net_zero = 'expected'"
        )
        expected_scope = (
            "SELECT 1 FROM ar_transfer_summary "
            "WHERE net_amount <> 0 "
            "  AND expected_net_zero = 'expected'"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_limit_breach_kpi_scope(self, pg_conn):
        # ar_subledger_limit_breach view filters outbound_total > daily_limit.
        as_displayed = "SELECT 1 FROM ar_subledger_limit_breach"
        expected_scope = (
            "SELECT 1 FROM ar_subledger_limit_breach WHERE overage > 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_overdraft_kpi_scope(self, pg_conn):
        as_displayed = "SELECT 1 FROM ar_subledger_overdraft"
        expected_scope = (
            "SELECT 1 FROM ar_subledger_overdraft WHERE stored_balance < 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_sweep_target_kpi_scope(self, pg_conn):
        as_displayed = "SELECT 1 FROM ar_sweep_target_nonzero"
        expected_scope = (
            "SELECT 1 FROM ar_sweep_target_nonzero WHERE stored_balance <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_sweep_drift_kpi_scope(self, pg_conn):
        # Semantic scope is drift <> 0. View emits a row per sweep_date
        # including healthy days; drift_status='drift' is the canonical
        # filter applied wherever this view is consumed. Equality here
        # pins the drift_status derivation against drift <> 0.
        as_displayed = (
            "SELECT 1 FROM ar_concentration_master_sweep_drift "
            "WHERE drift_status = 'drift'"
        )
        expected_scope = (
            "SELECT 1 FROM ar_concentration_master_sweep_drift WHERE drift <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_ach_orig_nonzero_kpi_scope(self, pg_conn):
        # View filters balance <> 0 — KPI as-displayed should equal the
        # semantic scope (non-zero EOD days for gl-1810).
        as_displayed = "SELECT 1 FROM ar_ach_orig_settlement_nonzero"
        expected_scope = (
            "SELECT 1 FROM ar_ach_orig_settlement_nonzero WHERE stored_balance <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_ach_sweep_no_fed_kpi_scope(self, pg_conn):
        # View has NOT EXISTS for the Fed confirmation child — every row
        # is a sweep without a Fed leg. No additional scope to apply.
        as_displayed = "SELECT 1 FROM ar_ach_sweep_no_fed_confirmation"
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ar_ach_sweep_no_fed_confirmation s "
                "WHERE NOT EXISTS ("
                " SELECT 1 FROM transactions fed "
                " WHERE fed.parent_transfer_id = s.sweep_transfer_id "
                "   AND fed.transfer_type = 'ach' "
                "   AND fed.origin = 'external_force_posted'"
                ")"
            )
            expected = int(cur.fetchone()[0])
        assert _count_rows(pg_conn, as_displayed) == expected
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_fed_no_catchup_kpi_scope(self, pg_conn):
        as_displayed = "SELECT 1 FROM ar_fed_card_no_internal_catchup"
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ar_fed_card_no_internal_catchup f "
                "WHERE NOT EXISTS ("
                " SELECT 1 FROM transactions ic "
                " WHERE ic.parent_transfer_id = f.fed_transfer_id"
                ")"
            )
            expected = int(cur.fetchone()[0])
        assert _count_rows(pg_conn, as_displayed) == expected
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_gl_fed_drift_kpi_scope(self, pg_conn):
        # Semantic scope is drift <> 0. Same shape as sweep_drift: view
        # returns all movement_dates and drift_status='drift' is the
        # canonical filter wherever this view is consumed. Equality here
        # pins the drift_status derivation against drift <> 0.
        as_displayed = (
            "SELECT 1 FROM ar_gl_vs_fed_master_drift "
            "WHERE drift_status = 'drift'"
        )
        expected_scope = (
            "SELECT 1 FROM ar_gl_vs_fed_master_drift WHERE drift <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_internal_stuck_kpi_scope(self, pg_conn):
        # View has NOT EXISTS for Step-2 child; every row is a stuck originate.
        as_displayed = "SELECT 1 FROM ar_internal_transfer_stuck"
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ar_internal_transfer_stuck s "
                "WHERE NOT EXISTS ("
                " SELECT 1 FROM transactions step2 "
                " WHERE step2.parent_transfer_id = s.originate_transfer_id"
                ")"
            )
            expected = int(cur.fetchone()[0])
        assert _count_rows(pg_conn, as_displayed) == expected
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_internal_suspense_nonzero_kpi_scope(self, pg_conn):
        # View filters balance <> 0 on gl-1830.
        as_displayed = "SELECT 1 FROM ar_internal_transfer_suspense_nonzero"
        expected_scope = (
            "SELECT 1 FROM ar_internal_transfer_suspense_nonzero "
            "WHERE stored_balance <> 0"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_internal_reversal_uncredited_kpi_scope(self, pg_conn):
        # View JOIN already enforces "credit-back leg failed but suspense
        # leg succeeded" — every row qualifies.
        as_displayed = "SELECT 1 FROM ar_internal_reversal_uncredited"
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_expected_zero_rollup_kpi_scope(self, pg_conn):
        # UNION of three views, each of which already filters to non-zero
        # / unswept rows. Total = sum of the three component counts.
        as_displayed = "SELECT 1 FROM ar_expected_zero_eod_rollup"
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT "
                " (SELECT COUNT(*) FROM ar_sweep_target_nonzero) "
                " + (SELECT COUNT(*) FROM ar_ach_orig_settlement_nonzero) "
                " + (SELECT COUNT(*) FROM ar_internal_transfer_suspense_nonzero)"
            )
            expected = int(cur.fetchone()[0])
        assert _count_rows(pg_conn, as_displayed) == expected
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_two_sided_rollup_kpi_scope(self, pg_conn):
        # UNION of ar_ach_sweep_no_fed_confirmation + ar_fed_card_no_internal_catchup.
        as_displayed = "SELECT 1 FROM ar_two_sided_post_mismatch_rollup"
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT "
                " (SELECT COUNT(*) FROM ar_ach_sweep_no_fed_confirmation) "
                " + (SELECT COUNT(*) FROM ar_fed_card_no_internal_catchup)"
            )
            expected = int(cur.fetchone()[0])
        assert _count_rows(pg_conn, as_displayed) == expected
        assert _count_rows(pg_conn, as_displayed) > 0


# ---------------------------------------------------------------------------
# Class 2: planted-row sanity contracts
# ---------------------------------------------------------------------------

class TestPlantedRowsSurface:
    """Each ``_*_PLANT`` constant must materialize through the deployed view."""

    def test_ledger_drift_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import _LEDGER_DRIFT_PLANT

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT ledger_account_id, balance_date "
                "FROM ar_ledger_balance_drift WHERE drift <> 0"
            )
            cells = {(lid, bdate) for lid, bdate in cur.fetchall()}
        for lid, days_ago, _ in _LEDGER_DRIFT_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert (lid, expected_date) in cells, (
                f"Planted ledger drift ({lid}, days_ago={days_ago}) "
                f"missing from ar_ledger_balance_drift drift rows"
            )

    def test_subledger_drift_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import _SUBLEDGER_DRIFT_PLANT

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT subledger_account_id, balance_date "
                "FROM ar_subledger_balance_drift WHERE drift <> 0"
            )
            cells = {(sid, bdate) for sid, bdate in cur.fetchall()}
        for sid, days_ago, _ in _SUBLEDGER_DRIFT_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert (sid, expected_date) in cells, (
                f"Planted sub-ledger drift ({sid}, days_ago={days_ago}) "
                f"missing from ar_subledger_balance_drift drift rows"
            )

    def test_limit_breach_plants_exact_count(self, pg_conn):
        # 1 plant = 1 (sub-ledger, day, transfer_type) breach row. Strict
        # equality: extra rows would mean an unintended breach slipped in.
        actual = _count_rows(pg_conn, "SELECT 1 FROM ar_subledger_limit_breach")
        assert actual == _planted_count("limit_breach"), (
            f"Expected exactly {_planted_count('limit_breach')} limit-breach rows "
            f"(one per _LIMIT_BREACH_PLANT entry), got {actual}"
        )

    def test_overdraft_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import _OVERDRAFT_PLANT

        # Sticky: each plant inflates into N daily rows (sub-ledger stays
        # negative for several days). Assert >= planted_count and confirm
        # every planted (sub-ledger, day) cell appears.
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT subledger_account_id, balance_date "
                "FROM ar_subledger_overdraft"
            )
            cells = {(sid, bdate) for sid, bdate in cur.fetchall()}
        for sid, days_ago, _amt, _memo in _OVERDRAFT_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert (sid, expected_date) in cells, (
                f"Planted overdraft ({sid}, days_ago={days_ago}) "
                f"missing from ar_subledger_overdraft"
            )
        assert len(cells) >= _planted_count("overdraft")

    def test_sweep_target_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import _ZBA_SWEEP_FAIL_PLANT

        # Sticky: a skipped sweep leaves the operating sub-account
        # non-zero from that day forward until the next clean sweep.
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT subledger_account_id, balance_date "
                "FROM ar_sweep_target_nonzero"
            )
            cells = {(sid, bdate) for sid, bdate in cur.fetchall()}
        for sid, days_ago in _ZBA_SWEEP_FAIL_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert (sid, expected_date) in cells, (
                f"Planted sweep-target non-zero ({sid}, days_ago={days_ago}) "
                f"missing from ar_sweep_target_nonzero"
            )
        assert len(cells) >= _planted_count("sweep_target")

    def test_sweep_drift_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import (
            _ZBA_SWEEP_LEG_MISMATCH_PLANT,
        )

        # 1 mismatch plant = 1 drift day. Assert each planted day surfaces
        # and that drift-day count equals plant count.
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT sweep_date FROM ar_concentration_master_sweep_drift "
                "WHERE drift <> 0"
            )
            drift_days = {bdate for (bdate,) in cur.fetchall()}
        for _sid, days_ago, _delta in _ZBA_SWEEP_LEG_MISMATCH_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert expected_date in drift_days, (
                f"Planted sweep-leg-mismatch days_ago={days_ago} "
                f"missing from ar_concentration_master_sweep_drift drift rows"
            )
        assert len(drift_days) == _planted_count("sweep_leg_mismatch"), (
            f"Expected exactly {_planted_count('sweep_leg_mismatch')} sweep-drift "
            f"days, got {len(drift_days)}"
        )

    def test_ach_orig_nonzero_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import _ACH_SWEEP_SKIP_PLANT

        # Sticky: a skipped EOD sweep leaves gl-1810 non-zero from that
        # day forward until the next clean sweep zeroes it.
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT balance_date FROM ar_ach_orig_settlement_nonzero"
            )
            days = {bdate for (bdate,) in cur.fetchall()}
        for days_ago in _ACH_SWEEP_SKIP_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert expected_date in days, (
                f"Planted ACH-orig skip days_ago={days_ago} "
                f"missing from ar_ach_orig_settlement_nonzero"
            )
        assert len(days) >= _planted_count("ach_orig_skip")

    def test_ach_sweep_no_fed_plants_exact_count(self, pg_conn):
        # 1 fed-confirmation-missing plant = 1 sweep transfer with no
        # Fed child. Strict equality: every other ACH sweep day has its
        # Fed confirmation, so the view should only carry plant rows.
        actual = _count_rows(
            pg_conn, "SELECT 1 FROM ar_ach_sweep_no_fed_confirmation",
        )
        assert actual == _planted_count("ach_fed_missing"), (
            f"Expected exactly {_planted_count('ach_fed_missing')} ACH-sweep-no-fed "
            f"rows (one per _ACH_FED_CONFIRMATION_MISSING entry), got {actual}"
        )

    def test_fed_no_catchup_plants_exact_count(self, pg_conn):
        actual = _count_rows(
            pg_conn, "SELECT 1 FROM ar_fed_card_no_internal_catchup",
        )
        assert actual == _planted_count("card_internal_missing"), (
            f"Expected exactly {_planted_count('card_internal_missing')} "
            f"fed-no-catchup rows (one per _CARD_INTERNAL_MISSING_PLANT entry), "
            f"got {actual}"
        )

    def test_gl_fed_drift_plants_surface(self, pg_conn):
        # Drift days = days where Fed posted but SNB didn't catch up.
        # _CARD_INTERNAL_MISSING_PLANT drives those days.
        from quicksight_gen.account_recon.demo_data import (
            _CARD_INTERNAL_MISSING_PLANT,
        )

        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT movement_date FROM ar_gl_vs_fed_master_drift "
                "WHERE drift <> 0"
            )
            drift_days = {bdate for (bdate,) in cur.fetchall()}
        for days_ago in _CARD_INTERNAL_MISSING_PLANT:
            expected_date = date.today() - timedelta(days=days_ago)
            assert expected_date in drift_days, (
                f"Planted gl-vs-fed drift days_ago={days_ago} "
                f"missing from ar_gl_vs_fed_master_drift drift rows"
            )
        assert len(drift_days) == _planted_count("card_internal_missing"), (
            f"Expected exactly {_planted_count('card_internal_missing')} "
            f"gl-vs-fed drift days, got {len(drift_days)}"
        )

    def test_internal_stuck_plants_exact_count(self, pg_conn):
        # 1 stuck-kind plant = 1 originate without a Step-2 child.
        actual = _count_rows(
            pg_conn, "SELECT 1 FROM ar_internal_transfer_stuck",
        )
        assert actual == _planted_count("internal_stuck"), (
            f"Expected exactly {_planted_count('internal_stuck')} stuck "
            f"originates (one per stuck _INTERNAL_TRANSFER_PLANT entry), "
            f"got {actual}"
        )

    def test_internal_suspense_nonzero_plants_surface(self, pg_conn):
        from quicksight_gen.account_recon.demo_data import (
            _INTERNAL_TRANSFER_PLANT,
        )

        # Sticky: each stuck originate keeps gl-1830 non-zero from that
        # day forward until cleared. Plant days must appear in the view.
        with pg_conn.cursor() as cur:
            cur.execute(
                "SELECT balance_date FROM ar_internal_transfer_suspense_nonzero"
            )
            days = {bdate for (bdate,) in cur.fetchall()}
        for _o, _r, days_ago, kind, _amt in _INTERNAL_TRANSFER_PLANT:
            if kind != "stuck":
                continue
            expected_date = date.today() - timedelta(days=days_ago)
            assert expected_date in days, (
                f"Stuck internal transfer days_ago={days_ago} "
                f"missing from ar_internal_transfer_suspense_nonzero"
            )
        assert len(days) >= _planted_count("internal_stuck")

    def test_internal_reversal_uncredited_plants_exact_count(self, pg_conn):
        # 1 reversed_not_credited plant = 1 row.
        actual = _count_rows(
            pg_conn, "SELECT 1 FROM ar_internal_reversal_uncredited",
        )
        assert actual == _planted_count("internal_reversed"), (
            f"Expected exactly {_planted_count('internal_reversed')} "
            f"uncredited reversals (one per reversed_not_credited "
            f"_INTERNAL_TRANSFER_PLANT entry), got {actual}"
        )
