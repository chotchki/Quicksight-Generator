"""API tests: verify datasets imported successfully with data."""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestDatasetImportStatus:
    def test_all_datasets_importable(self, qs_client, account_id, dataset_ids):
        """Every dataset should have a successful SPICE import or direct query mode."""
        for ds_id in dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            ds = resp["DataSet"]
            mode = ds.get("ImportMode", "UNKNOWN")
            assert mode in ("SPICE", "DIRECT_QUERY"), (
                f"Dataset {ds_id} has unexpected import mode: {mode}"
            )


class TestDatasetColumns:
    """Spot-check key columns exist in deployed datasets."""

    EXPECTED_COLUMNS = {
        "merchants-dataset": {"merchant_id", "merchant_name", "merchant_type"},
        "sales-dataset": {
            "sale_id", "merchant_id", "amount", "sale_type",
            "payment_method", "taxes", "tips", "discount_percentage", "cashier",
        },
        "settlements-dataset": {"settlement_id", "merchant_id", "settlement_status"},
        "payments-dataset": {
            "payment_id", "settlement_id", "payment_amount",
            "external_transaction_id", "payment_method",
        },
        "payment-recon-dataset": {
            "transaction_id", "external_system", "match_status", "days_outstanding",
        },
        "sale-settlement-mismatch-dataset": {
            "settlement_id", "settlement_amount", "sales_sum", "difference",
        },
        "settlement-payment-mismatch-dataset": {
            "payment_id", "settlement_id", "payment_amount",
            "settlement_amount", "difference",
        },
        "unmatched-external-txns-dataset": {
            "transaction_id", "external_system", "external_amount",
        },
    }

    def test_key_columns_present(self, qs_client, account_id, resource_prefix):
        for suffix, expected_cols in self.EXPECTED_COLUMNS.items():
            ds_id = f"{resource_prefix}-{suffix}"
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            ds = resp["DataSet"]
            # Columns come from OutputColumns on the dataset
            output_cols = {
                c["Name"]
                for c in ds.get("OutputColumns", [])
            }
            for col in expected_cols:
                assert col in output_cols, (
                    f"Dataset {ds_id} missing column '{col}'. "
                    f"Has: {sorted(output_cols)}"
                )
