"""Tests for dataset column contracts.

Validates that every dataset builder produces a DataSet whose InputColumn
list matches its declared DatasetContract.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import ColumnSpec, DatasetContract
from quicksight_gen.account_recon import datasets as ar_datasets
from quicksight_gen.payment_recon import datasets as pr_datasets


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
    (ar_datasets.build_limit_breach_dataset, ar_datasets.LIMIT_BREACH_CONTRACT),
    (ar_datasets.build_overdraft_dataset, ar_datasets.OVERDRAFT_CONTRACT),
    (ar_datasets.build_sweep_target_nonzero_dataset, ar_datasets.SWEEP_TARGET_NONZERO_CONTRACT),
    (ar_datasets.build_concentration_master_sweep_drift_dataset, ar_datasets.CONCENTRATION_MASTER_SWEEP_DRIFT_CONTRACT),
    (ar_datasets.build_ach_orig_settlement_nonzero_dataset, ar_datasets.ACH_ORIG_SETTLEMENT_NONZERO_CONTRACT),
    (ar_datasets.build_ach_sweep_no_fed_confirmation_dataset, ar_datasets.ACH_SWEEP_NO_FED_CONFIRMATION_CONTRACT),
    (ar_datasets.build_fed_card_no_internal_catchup_dataset, ar_datasets.FED_CARD_NO_INTERNAL_CATCHUP_CONTRACT),
    (ar_datasets.build_gl_vs_fed_master_drift_dataset, ar_datasets.GL_VS_FED_MASTER_DRIFT_CONTRACT),
    (ar_datasets.build_internal_transfer_stuck_dataset, ar_datasets.INTERNAL_TRANSFER_STUCK_CONTRACT),
    (ar_datasets.build_internal_transfer_suspense_nonzero_dataset, ar_datasets.INTERNAL_TRANSFER_SUSPENSE_NONZERO_CONTRACT),
    (ar_datasets.build_internal_reversal_uncredited_dataset, ar_datasets.INTERNAL_REVERSAL_UNCREDITED_CONTRACT),
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
