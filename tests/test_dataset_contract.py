"""Tests for dataset column contracts.

Validates that every dataset builder produces a DataSet whose InputColumn
list matches its declared DatasetContract.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import ColumnSpec, DatasetContract
from quicksight_gen.apps.account_recon import datasets as ar_datasets
from quicksight_gen.apps.investigation import datasets as inv_datasets
from quicksight_gen.apps.payment_recon import datasets as pr_datasets


@pytest.fixture()
def cfg() -> Config:
    return Config(
        aws_account_id="111122223333",
        aws_region="us-east-2",
        datasource_arn="arn:aws:quicksight:us-east-2:111122223333:datasource/ds",
    )


def _extract_column_names(dataset) -> list[str]:
    """Pull the InputColumn names out of a built DataSet."""
    for physical in dataset.PhysicalTableMap.values():
        return [c.Name for c in physical.CustomSql.Columns]
    raise AssertionError("No PhysicalTable found")


# ---------------------------------------------------------------------------
# AR contracts
# ---------------------------------------------------------------------------

AR_BUILDERS_AND_CONTRACTS = [
    (ar_datasets.build_ledger_accounts_dataset, ar_datasets.LEDGER_ACCOUNTS_CONTRACT),
    (ar_datasets.build_subledger_accounts_dataset, ar_datasets.SUBLEDGER_ACCOUNTS_CONTRACT),
    (ar_datasets.build_transactions_dataset, ar_datasets.TRANSACTIONS_CONTRACT),
    (ar_datasets.build_ledger_balance_drift_dataset, ar_datasets.LEDGER_BALANCE_DRIFT_CONTRACT),
    (ar_datasets.build_subledger_balance_drift_dataset, ar_datasets.SUBLEDGER_BALANCE_DRIFT_CONTRACT),
    (ar_datasets.build_transfer_summary_dataset, ar_datasets.TRANSFER_SUMMARY_CONTRACT),
    (ar_datasets.build_non_zero_transfers_dataset, ar_datasets.NON_ZERO_TRANSFERS_CONTRACT),
    (ar_datasets.build_expected_zero_eod_rollup_dataset, ar_datasets.EXPECTED_ZERO_EOD_ROLLUP_CONTRACT),
    (ar_datasets.build_two_sided_post_mismatch_rollup_dataset, ar_datasets.TWO_SIDED_POST_MISMATCH_ROLLUP_CONTRACT),
    (ar_datasets.build_balance_drift_timelines_rollup_dataset, ar_datasets.BALANCE_DRIFT_TIMELINES_ROLLUP_CONTRACT),
    (ar_datasets.build_daily_statement_summary_dataset, ar_datasets.DAILY_STATEMENT_SUMMARY_CONTRACT),
    (ar_datasets.build_daily_statement_transactions_dataset, ar_datasets.DAILY_STATEMENT_TRANSACTIONS_CONTRACT),
    (ar_datasets.build_ar_unified_exceptions_dataset, ar_datasets.UNIFIED_EXCEPTIONS_CONTRACT),
]


class TestArContracts:
    @pytest.mark.parametrize(
        "builder,contract",
        AR_BUILDERS_AND_CONTRACTS,
        ids=[c.columns[0].name for _, c in AR_BUILDERS_AND_CONTRACTS],
    )
    def test_columns_match_contract(self, cfg, builder, contract):
        ds = builder(cfg)
        actual = _extract_column_names(ds)
        assert actual == contract.column_names


# ---------------------------------------------------------------------------
# PR contracts
# ---------------------------------------------------------------------------

PR_BUILDERS_AND_CONTRACTS = [
    (pr_datasets.build_merchants_dataset, pr_datasets.MERCHANTS_CONTRACT),
    (pr_datasets.build_sales_dataset, pr_datasets.SALES_CONTRACT),
    (pr_datasets.build_settlements_dataset, pr_datasets.SETTLEMENTS_CONTRACT),
    (pr_datasets.build_payments_dataset, pr_datasets.PAYMENTS_CONTRACT),
    (pr_datasets.build_settlement_exceptions_dataset, pr_datasets.SETTLEMENT_EXCEPTIONS_CONTRACT),
    (pr_datasets.build_payment_returns_dataset, pr_datasets.PAYMENT_RETURNS_CONTRACT),
    (pr_datasets.build_sale_settlement_mismatch_dataset, pr_datasets.SALE_SETTLEMENT_MISMATCH_CONTRACT),
    (pr_datasets.build_settlement_payment_mismatch_dataset, pr_datasets.SETTLEMENT_PAYMENT_MISMATCH_CONTRACT),
    (pr_datasets.build_unmatched_external_txns_dataset, pr_datasets.UNMATCHED_EXTERNAL_TXNS_CONTRACT),
    (pr_datasets.build_external_transactions_dataset, pr_datasets.EXTERNAL_TRANSACTIONS_CONTRACT),
    (pr_datasets.build_payment_recon_dataset, pr_datasets.PAYMENT_RECON_CONTRACT),
]


class TestPrContracts:
    @pytest.mark.parametrize(
        "builder,contract",
        PR_BUILDERS_AND_CONTRACTS,
        ids=[c.columns[0].name for _, c in PR_BUILDERS_AND_CONTRACTS],
    )
    def test_columns_match_contract(self, cfg, builder, contract):
        ds = builder(cfg)
        actual = _extract_column_names(ds)
        assert actual == contract.column_names


# ---------------------------------------------------------------------------
# Investigation contracts
# ---------------------------------------------------------------------------

INV_BUILDERS_AND_CONTRACTS = [
    (inv_datasets.build_recipient_fanout_dataset,
     inv_datasets.RECIPIENT_FANOUT_CONTRACT),
]


class TestInvContracts:
    @pytest.mark.parametrize(
        "builder,contract",
        INV_BUILDERS_AND_CONTRACTS,
        ids=[c.columns[0].name for _, c in INV_BUILDERS_AND_CONTRACTS],
    )
    def test_columns_match_contract(self, cfg, builder, contract):
        ds = builder(cfg)
        actual = _extract_column_names(ds)
        assert actual == contract.column_names


# ---------------------------------------------------------------------------
# Contract basics
# ---------------------------------------------------------------------------

class TestDatasetContract:
    def test_column_names_property(self):
        c = DatasetContract(columns=[
            ColumnSpec("a", "STRING"),
            ColumnSpec("b", "DECIMAL"),
        ])
        assert c.column_names == ["a", "b"]

    def test_to_input_columns_types(self):
        c = DatasetContract(columns=[
            ColumnSpec("x", "INTEGER"),
        ])
        cols = c.to_input_columns()
        assert len(cols) == 1
        assert cols[0].Name == "x"
        assert cols[0].Type == "INTEGER"


# ---------------------------------------------------------------------------
# K.3.2 — is_late + expected_complete_at on every aging-bearing contract
# ---------------------------------------------------------------------------

PR_LATENESS_CONTRACTS = [
    ("SETTLEMENT_EXCEPTIONS", pr_datasets.SETTLEMENT_EXCEPTIONS_CONTRACT),
    ("PAYMENT_RETURNS", pr_datasets.PAYMENT_RETURNS_CONTRACT),
    ("SALE_SETTLEMENT_MISMATCH", pr_datasets.SALE_SETTLEMENT_MISMATCH_CONTRACT),
    ("SETTLEMENT_PAYMENT_MISMATCH", pr_datasets.SETTLEMENT_PAYMENT_MISMATCH_CONTRACT),
    ("UNMATCHED_EXTERNAL_TXNS", pr_datasets.UNMATCHED_EXTERNAL_TXNS_CONTRACT),
    ("PAYMENT_RECON", pr_datasets.PAYMENT_RECON_CONTRACT),
]

AR_LATENESS_CONTRACTS = [
    ("LEDGER_BALANCE_DRIFT", ar_datasets.LEDGER_BALANCE_DRIFT_CONTRACT),
    ("SUBLEDGER_BALANCE_DRIFT", ar_datasets.SUBLEDGER_BALANCE_DRIFT_CONTRACT),
    ("NON_ZERO_TRANSFERS", ar_datasets.NON_ZERO_TRANSFERS_CONTRACT),
    ("EXPECTED_ZERO_EOD_ROLLUP", ar_datasets.EXPECTED_ZERO_EOD_ROLLUP_CONTRACT),
    ("TWO_SIDED_POST_MISMATCH_ROLLUP", ar_datasets.TWO_SIDED_POST_MISMATCH_ROLLUP_CONTRACT),
    ("UNIFIED_EXCEPTIONS", ar_datasets.UNIFIED_EXCEPTIONS_CONTRACT),
]


class TestLatenessColumns:
    """K.3.2: every aging-bearing contract surfaces is_late + expected_complete_at."""

    @pytest.mark.parametrize(
        "label,contract",
        PR_LATENESS_CONTRACTS + AR_LATENESS_CONTRACTS,
        ids=[label for label, _ in PR_LATENESS_CONTRACTS + AR_LATENESS_CONTRACTS],
    )
    def test_contract_has_lateness_columns(self, label, contract):
        names = contract.column_names
        assert "is_late" in names, (
            f"{label} contract is missing is_late column (K.3.2)"
        )
        assert "expected_complete_at" in names, (
            f"{label} contract is missing expected_complete_at column (K.3.2)"
        )

    @pytest.mark.parametrize(
        "label,contract",
        PR_LATENESS_CONTRACTS + AR_LATENESS_CONTRACTS,
        ids=[label for label, _ in PR_LATENESS_CONTRACTS + AR_LATENESS_CONTRACTS],
    )
    def test_lateness_column_types(self, label, contract):
        is_late = contract.column("is_late")
        expected = contract.column("expected_complete_at")
        assert is_late.type == "STRING", (
            f"{label}.is_late should be STRING (Late/On Time labels), "
            f"got {is_late.type}"
        )
        assert expected.type == "DATETIME", (
            f"{label}.expected_complete_at should be DATETIME, "
            f"got {expected.type}"
        )


class TestPaymentReconLateness:
    """K.3.2: PAYMENT_RECON match_status switches from operator threshold
    to the data-driven is_late predicate."""

    def test_match_status_uses_is_late_predicate(self, cfg):
        ds = pr_datasets.build_payment_recon_dataset(cfg)
        sql = next(iter(ds.PhysicalTableMap.values())).CustomSql.SqlQuery
        # The CASE should compare CURRENT_TIMESTAMP against COALESCE(...)
        # rather than `(CURRENT_DATE - posted_at::date) > N`.
        assert "CURRENT_TIMESTAMP > COALESCE(" in sql, (
            "match_status CASE should use the is_late predicate "
            "(CURRENT_TIMESTAMP > COALESCE(expected_complete_at, ...))"
        )

    def test_match_status_does_not_reference_retired_late_default_days(self, cfg):
        # K.3.3 retired cfg.late_default_days entirely. The SQL must not
        # mention the old config field name as a stale reference.
        ds = pr_datasets.build_payment_recon_dataset(cfg)
        sql = next(iter(ds.PhysicalTableMap.values())).CustomSql.SqlQuery
        assert "late_default_days" not in sql, (
            "match_status CASE should no longer reference late_default_days"
        )


class TestUnifiedExceptionsLateness:
    """K.3.2: ar_unified_exceptions matview surfaces is_late + expected_complete_at."""

    def test_matview_select_passes_through_lateness(self, cfg):
        # The dataset SQL is `SELECT *, TO_CHAR(...) FROM ar_unified_exceptions`,
        # so adding the columns to the matview makes them available to the
        # contract automatically. We assert the contract has the columns
        # in TestLatenessColumns; here we verify the dataset SQL doesn't
        # accidentally restrict the column set.
        ds = ar_datasets.build_ar_unified_exceptions_dataset(cfg)
        sql = next(iter(ds.PhysicalTableMap.values())).CustomSql.SqlQuery
        assert "SELECT *" in sql, (
            "Unified exceptions dataset should pass through all matview "
            "columns via SELECT *"
        )
