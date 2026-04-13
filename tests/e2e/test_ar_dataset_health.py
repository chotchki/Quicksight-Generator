"""API tests: verify AR datasets imported successfully with data."""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestArDatasetImportStatus:
    def test_all_datasets_importable(
        self, qs_client, account_id, ar_dataset_ids,
    ):
        for ds_id in ar_dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            ds = resp["DataSet"]
            mode = ds.get("ImportMode", "UNKNOWN")
            assert mode in ("SPICE", "DIRECT_QUERY"), (
                f"AR dataset {ds_id} has unexpected import mode: {mode}"
            )


class TestArDatasetColumns:
    """Spot-check drill-down source columns exist on the deployed datasets.

    Drill-downs rely on specific columns being present: if a view were
    reshaped and dropped one of these, browser drill-downs would silently
    filter to nothing.
    """

    EXPECTED_COLUMNS = {
        "ar-parent-accounts-dataset": {
            "parent_account_id", "name", "scope",
        },
        "ar-accounts-dataset": {
            "account_id", "name", "parent_account_id", "scope",
        },
        "ar-transactions-dataset": {
            "transaction_id", "account_id", "transfer_id", "transfer_type",
            "status", "posted_at", "posted_date", "amount", "is_failed",
            "scope",
        },
        "ar-parent-balance-drift-dataset": {
            "parent_account_id", "balance_date",
            "stored_balance", "computed_balance", "drift", "drift_status",
        },
        "ar-account-balance-drift-dataset": {
            "account_id", "parent_account_id", "balance_date",
            "stored_balance", "computed_balance", "drift", "drift_status",
            "overdraft_status",
        },
        "ar-transfer-summary-dataset": {
            "transfer_id", "net_amount", "net_zero_status", "scope_type",
            "transfer_type",
        },
        "ar-non-zero-transfers-dataset": {
            "transfer_id", "net_amount", "failed_leg_count",
        },
        "ar-limit-breach-dataset": {
            "account_id", "parent_account_id", "activity_date",
            "activity_date_str", "transfer_type", "outbound_total",
            "daily_limit", "overage",
        },
        "ar-overdraft-dataset": {
            "account_id", "parent_account_id", "balance_date",
            "balance_date_str", "stored_balance",
        },
    }

    def test_key_columns_present(
        self, qs_client, account_id, resource_prefix,
    ):
        for suffix, expected_cols in self.EXPECTED_COLUMNS.items():
            ds_id = f"{resource_prefix}-{suffix}"
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            output_cols = {
                c["Name"] for c in resp["DataSet"].get("OutputColumns", [])
            }
            missing = expected_cols - output_cols
            assert not missing, (
                f"Dataset {ds_id} missing columns {sorted(missing)}. "
                f"Has: {sorted(output_cols)}"
            )
