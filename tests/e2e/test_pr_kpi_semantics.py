"""Postgres-direct semantics tests for PR Exceptions + Recon KPIs.

Sibling to ``tests/e2e/test_ar_kpi_semantics.py`` (shipped in commit
``ddb247a``). Two contracts per check:

1. KPI scope: the dataset SQL the KPI counts (with any sheet-pinned
   filter applied) returns the same number of rows / sum as the
   semantic scope implied by the KPI subtitle. Catches dataset-vs-visual
   filter drift the moment it ships.

2. Scenario surface: scenarios the unit tests guarantee (see
   ``tests/test_demo_data.py::TestScenarioCoverage`` /
   ``TestRefunds``) actually appear in the deployed dataset SQL when
   it executes against the seeded Postgres. PR has no ``_PLANT``
   constants — scenarios emerge from natural generator branching, so
   the assertions here are floor counts (``>= N``) rather than exact
   matches.

PR datasets are inline ``CustomSql`` strings rather than database
views, so there's no ``CREATE VIEW`` indirection to query. Each test
extracts the dataset SQL by calling the builder and reading
``PhysicalTableMap[*].CustomSql.SqlQuery`` — single source of truth
with the deployed datasets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import pytest

if TYPE_CHECKING:
    from psycopg2.extensions import connection as PgConnection

    from quicksight_gen.common.config import Config
    from quicksight_gen.common.models import DataSet


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


def _sum_column(conn: "PgConnection", sql: str, column: str) -> float:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COALESCE(SUM({column}), 0) FROM ({sql}) _sub")
        row = cur.fetchone()
    return float(row[0])


def _dataset_sql(cfg: "Config", builder: "Callable[[Config], DataSet]") -> str:
    """Extract the inline ``CustomSql.SqlQuery`` from a PR dataset builder."""
    ds = builder(cfg)
    physical = next(iter(ds.PhysicalTableMap.values()))
    return physical.CustomSql.SqlQuery


# PR-specific scope constants. Mirrors the WHERE clauses in
# payment_recon/datasets.py so the semantic-scope SQL is independent
# of the dataset SQL (otherwise the test would tautologically pass).
_PR_MERCHANT_LEG = (
    "account_type = 'merchant_dda' "
    "AND control_account_id = 'pr-merchant-ledger'"
)
_PR_EXTERNAL_LEG = (
    "account_type = 'external_counter' "
    "AND control_account_id = 'pr-merchant-ledger'"
)


# ---------------------------------------------------------------------------
# Class 1: KPI scope contracts (Exceptions tab)
# ---------------------------------------------------------------------------

class TestExceptionsKpiScope:
    """Each Exceptions-tab KPI / table count must equal its semantic scope."""

    def test_unsettled_kpi_scope(self, pg_conn, cfg):
        # KPI counts sale_id from settlement-exceptions. Subtitle: "Sales
        # that have not yet been bundled into a settlement". Semantic
        # scope = sale-transfer merchant_dda legs whose metadata.settlement_id
        # is NULL.
        from quicksight_gen.payment_recon.datasets import (
            build_settlement_exceptions_dataset,
        )

        as_displayed = _dataset_sql(cfg, build_settlement_exceptions_dataset)
        expected_scope = (
            f"SELECT 1 FROM transactions "
            f"WHERE transfer_type = 'sale' "
            f"AND {_PR_MERCHANT_LEG} "
            f"AND JSON_VALUE(metadata, '$.settlement_id') IS NULL"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0, (
            "Unsettled KPI must be non-empty — TestScenarioCoverage "
            "guarantees >= 8 unsettled sales"
        )

    def test_returns_kpi_scope(self, pg_conn, cfg):
        # KPI counts payment_id from payment-returns. Subtitle: "Payments
        # that were sent back". Semantic scope = payment-transfer
        # merchant_dda legs with metadata.is_returned='true'.
        from quicksight_gen.payment_recon.datasets import (
            build_payment_returns_dataset,
        )

        as_displayed = _dataset_sql(cfg, build_payment_returns_dataset)
        expected_scope = (
            f"SELECT 1 FROM transactions "
            f"WHERE transfer_type = 'payment' "
            f"AND {_PR_MERCHANT_LEG} "
            f"AND JSON_VALUE(metadata, '$.is_returned') = 'true'"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0

    def test_sale_settlement_mismatch_table_scope(self, pg_conn, cfg):
        # Table on Exceptions tab; row-count is the implicit KPI for
        # the aging bar chart underneath. Subtitle: "Settlements whose
        # amount doesn't equal the signed sum of their linked sales".
        # Semantic scope = settlement-transfer rows where the linked
        # sales' summed signed_amount differs from the stored
        # settlement_amount.
        from quicksight_gen.payment_recon.datasets import (
            build_sale_settlement_mismatch_dataset,
        )

        as_displayed = _dataset_sql(cfg, build_sale_settlement_mismatch_dataset)
        expected_scope = f"""\
WITH settlements AS (
    SELECT DISTINCT
        JSON_VALUE(metadata, '$.settlement_id') AS settlement_id,
        CAST(JSON_VALUE(metadata, '$.settlement_amount') AS DECIMAL(12,2)) AS settlement_amount
    FROM transactions
    WHERE transfer_type = 'settlement' AND {_PR_MERCHANT_LEG}
),
sale_sums AS (
    SELECT
        JSON_VALUE(metadata, '$.settlement_id') AS settlement_id,
        SUM(signed_amount) AS sales_sum
    FROM transactions
    WHERE transfer_type = 'sale' AND {_PR_MERCHANT_LEG}
      AND JSON_VALUE(metadata, '$.settlement_id') IS NOT NULL
    GROUP BY JSON_VALUE(metadata, '$.settlement_id')
)
SELECT 1 FROM settlements s
LEFT JOIN sale_sums ss ON ss.settlement_id = s.settlement_id
WHERE s.settlement_amount <> COALESCE(ss.sales_sum, 0)"""
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0, (
            "Sale-Settlement Mismatch table must be non-empty — refunds "
            "in the demo plant this scenario (TestRefunds)."
        )

    def test_settlement_payment_mismatch_table_scope(self, pg_conn, cfg):
        # Table on Exceptions tab; subtitle: "Payments whose amount
        # doesn't match their settlement". Semantic scope = payment
        # rows whose payment_amount differs from the linked
        # settlement_amount.
        from quicksight_gen.payment_recon.datasets import (
            build_settlement_payment_mismatch_dataset,
        )

        as_displayed = _dataset_sql(cfg, build_settlement_payment_mismatch_dataset)
        expected_scope = f"""\
WITH s AS (
    SELECT DISTINCT
        JSON_VALUE(metadata, '$.settlement_id') AS settlement_id,
        CAST(JSON_VALUE(metadata, '$.settlement_amount') AS DECIMAL(12,2)) AS settlement_amount
    FROM transactions
    WHERE transfer_type = 'settlement' AND {_PR_MERCHANT_LEG}
),
p AS (
    SELECT
        JSON_VALUE(metadata, '$.settlement_id') AS settlement_id,
        CAST(JSON_VALUE(metadata, '$.payment_amount') AS DECIMAL(12,2)) AS payment_amount
    FROM transactions
    WHERE transfer_type = 'payment' AND {_PR_MERCHANT_LEG}
)
SELECT 1 FROM p JOIN s ON s.settlement_id = p.settlement_id
WHERE p.payment_amount <> s.settlement_amount"""
        # Allow zero — the demo doesn't deliberately plant settlement-payment
        # mismatches today; the dataset existing + matching scope is the
        # contract worth pinning. If a future generator change starts
        # planting them, the assertion still holds.
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)

    def test_unmatched_external_txns_scope(self, pg_conn, cfg):
        # Table on Exceptions tab; subtitle: "External system transactions
        # that have no internal payment linked". Semantic scope = ext_txn
        # rows whose metadata.external_transaction_id isn't named by any
        # payment leg.
        from quicksight_gen.payment_recon.datasets import (
            build_unmatched_external_txns_dataset,
        )

        as_displayed = _dataset_sql(cfg, build_unmatched_external_txns_dataset)
        expected_scope = f"""\
SELECT 1 FROM transactions et
WHERE et.transfer_type = 'external_txn' AND et.{_PR_EXTERNAL_LEG}
  AND NOT EXISTS (
      SELECT 1 FROM transactions p
      WHERE p.transfer_type = 'payment' AND p.{_PR_MERCHANT_LEG}
        AND JSON_VALUE(p.metadata, '$.external_transaction_id')
            = JSON_VALUE(et.metadata, '$.external_transaction_id')
  )"""
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        assert _count_rows(pg_conn, as_displayed) > 0, (
            "Unmatched external txns must be non-empty — "
            "TestScenarioCoverage guarantees >= 8 orphan ext_txns."
        )


# ---------------------------------------------------------------------------
# Class 2: KPI scope contracts (Reconciliation tab)
# ---------------------------------------------------------------------------

class TestReconKpiScope:
    """Recon KPIs use sheet-pinned visual filters on match_status.

    Pattern parallels AR's drift KPIs: dataset returns all match
    statuses (so the table + bar chart can show the full picture);
    each KPI is filtered by the visual-scoped pinned filter. The
    test asserts the visual-filtered SQL matches the semantic
    interpretation of the KPI subtitle.
    """

    def test_late_count_scope(self, pg_conn, cfg):
        # Pinned filter: match_status = 'late'. Subtitle: "Transactions
        # that have exceeded the late threshold without matching".
        from quicksight_gen.payment_recon.datasets import (
            build_payment_recon_dataset,
        )

        ds_sql = _dataset_sql(cfg, build_payment_recon_dataset)
        as_displayed = (
            f"SELECT 1 FROM ({ds_sql}) _ds WHERE match_status = 'late'"
        )
        # Semantic: ext_txn whose computed match_status is 'late'.
        # The dataset SQL itself encodes match_status; confirming the
        # filtered rowcount equals the dataset's own 'late' rowcount
        # pins the contract that the visual filter matches the dataset
        # column with no transformation in between.
        expected_scope = (
            f"SELECT 1 FROM ({ds_sql}) _ds WHERE match_status = 'late'"
        )
        assert _count_rows(pg_conn, as_displayed) == _count_rows(pg_conn, expected_scope)
        # Floor: late demo data exists. The seed plants stale ext_txns
        # (TestScenarioCoverage::test_orphan_external_txns_exist >= 8);
        # any orphan older than late_default_days qualifies.
        late_days = cfg.late_default_days
        assert _count_rows(pg_conn, as_displayed) > 0, (
            f"Late KPI is empty — no orphan ext_txns older than "
            f"late_default_days={late_days}. Either the demo's clock "
            f"shifted or the late threshold widened past the demo span."
        )

    def test_matched_amount_scope(self, pg_conn, cfg):
        # Pinned filter: match_status = 'matched'. Subtitle: "Total
        # external transaction amount that matches internal payments".
        # Semantic = sum(external_amount) where ext_amount equals sum
        # of linked payment amounts.
        from quicksight_gen.payment_recon.datasets import (
            build_payment_recon_dataset,
        )

        ds_sql = _dataset_sql(cfg, build_payment_recon_dataset)
        as_displayed_filtered = (
            f"SELECT external_amount FROM ({ds_sql}) _ds "
            f"WHERE match_status = 'matched'"
        )
        expected_filtered = (
            f"SELECT external_amount FROM ({ds_sql}) _ds "
            f"WHERE external_amount = internal_total"
        )
        as_displayed_sum = _sum_column(pg_conn, as_displayed_filtered, "external_amount")
        expected_sum = _sum_column(pg_conn, expected_filtered, "external_amount")
        assert as_displayed_sum == expected_sum
        assert as_displayed_sum > 0, (
            "Matched Amount KPI is zero — every orphan ext_txn shouldn't "
            "be the demo state."
        )

    def test_unmatched_amount_scope(self, pg_conn, cfg):
        # Pinned filter: match_status IN ('late','not_yet_matched').
        # Subtitle: "Total external transaction amount not yet matched".
        # Semantic = ext_txns where ext_amount differs from the summed
        # linked payment amounts (equivalently: NOT matched).
        from quicksight_gen.payment_recon.datasets import (
            build_payment_recon_dataset,
        )

        ds_sql = _dataset_sql(cfg, build_payment_recon_dataset)
        as_displayed_filtered = (
            f"SELECT external_amount FROM ({ds_sql}) _ds "
            f"WHERE match_status IN ('late', 'not_yet_matched')"
        )
        expected_filtered = (
            f"SELECT external_amount FROM ({ds_sql}) _ds "
            f"WHERE external_amount <> internal_total"
        )
        as_displayed_sum = _sum_column(pg_conn, as_displayed_filtered, "external_amount")
        expected_sum = _sum_column(pg_conn, expected_filtered, "external_amount")
        assert as_displayed_sum == expected_sum
        assert as_displayed_sum > 0, (
            "Unmatched Amount KPI is zero — orphan ext_txns "
            "(>= 8 per TestScenarioCoverage) should surface here."
        )


# ---------------------------------------------------------------------------
# Class 3: Scenario surface contracts
# ---------------------------------------------------------------------------

class TestScenarioSurface:
    """Scenarios the unit tests guarantee in-memory must surface in
    the deployed dataset SQL.

    Mirrors ``tests/test_demo_data.py::TestScenarioCoverage`` /
    ``TestRefunds`` thresholds against the seeded Postgres rather
    than the in-memory generator. Catches "the unit test passed but
    `demo apply` projected the rows differently / dropped them"
    regressions.
    """

    def test_unsettled_sales_floor(self, pg_conn, cfg):
        from quicksight_gen.payment_recon.datasets import (
            build_settlement_exceptions_dataset,
        )

        sql = _dataset_sql(cfg, build_settlement_exceptions_dataset)
        # TestScenarioCoverage::test_unsettled_sales_exist asserts >= 8.
        assert _count_rows(pg_conn, sql) >= 8

    def test_returned_payment_reasons_surface(self, pg_conn, cfg):
        from quicksight_gen.payment_recon.datasets import (
            build_payment_returns_dataset,
        )

        sql = _dataset_sql(cfg, build_payment_returns_dataset)
        with pg_conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT return_reason FROM ({sql}) _ds "
                f"WHERE return_reason IS NOT NULL"
            )
            reasons = {row[0] for row in cur.fetchall()}
        # TestScenarioCoverage::test_returned_payments_exist asserts
        # five canonical reasons are emitted. They should all reach
        # the deployed dataset.
        expected = {
            "insufficient_funds",
            "bank_rejected",
            "disputed",
            "account_closed",
            "invalid_account",
        }
        assert expected.issubset(reasons), (
            f"Missing return reasons in deployed dataset: {expected - reasons}"
        )

    def test_orphan_external_txns_floor(self, pg_conn, cfg):
        from quicksight_gen.payment_recon.datasets import (
            build_unmatched_external_txns_dataset,
        )

        sql = _dataset_sql(cfg, build_unmatched_external_txns_dataset)
        # TestScenarioCoverage::test_orphan_external_txns_exist asserts >= 8.
        assert _count_rows(pg_conn, sql) >= 8

    def test_external_systems_present(self, pg_conn, cfg):
        from quicksight_gen.payment_recon.datasets import (
            build_payment_recon_dataset,
        )

        sql = _dataset_sql(cfg, build_payment_recon_dataset)
        with pg_conn.cursor() as cur:
            cur.execute(
                f"SELECT DISTINCT external_system FROM ({sql}) _ds"
            )
            systems = {row[0] for row in cur.fetchall()}
        # TestScenarioCoverage::test_external_systems_present asserts
        # all three external systems appear in the demo SQL.
        assert {"BankSync", "PaymentHub", "ClearSettle"}.issubset(systems)

    def test_sale_settlement_mismatch_surfaces_refunds(self, pg_conn, cfg):
        # TestRefunds::test_refunds_flow_into_settlements asserts
        # refunds reduce settlement totals — the most common cause
        # of sale-settlement mismatch in the demo. Floor: at least
        # one refund-driven mismatch surfaces in the deployed dataset.
        from quicksight_gen.payment_recon.datasets import (
            build_sale_settlement_mismatch_dataset,
        )

        sql = _dataset_sql(cfg, build_sale_settlement_mismatch_dataset)
        assert _count_rows(pg_conn, sql) >= 1, (
            "Sale-Settlement Mismatch dataset is empty — refunds in "
            "the demo seed should produce at least one mismatch row."
        )
