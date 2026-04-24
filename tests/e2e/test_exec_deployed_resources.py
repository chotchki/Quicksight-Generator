"""API tests: verify the Executives dashboard/analysis/datasets exist."""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestExecDashboardExists:
    def test_dashboard_status(self, qs_client, account_id, exec_dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=exec_dashboard_id,
        )
        status = resp["Dashboard"]["Version"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Executives dashboard status is {status}, "
            "expected CREATION_SUCCESSFUL"
        )

    def test_dashboard_has_name(
        self, qs_client, account_id, exec_dashboard_id,
    ):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=exec_dashboard_id,
        )
        assert len(resp["Dashboard"]["Name"]) > 0


class TestExecAnalysisExists:
    def test_analysis_status(self, qs_client, account_id, exec_analysis_id):
        resp = qs_client.describe_analysis(
            AwsAccountId=account_id,
            AnalysisId=exec_analysis_id,
        )
        status = resp["Analysis"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Executives analysis status is {status}, "
            "expected CREATION_SUCCESSFUL"
        )


class TestExecDatasetsExist:
    def test_all_datasets_exist(
        self, qs_client, account_id, exec_dataset_ids,
    ):
        for ds_id in exec_dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200, (
                f"Executives dataset {ds_id} not found"
            )

    def test_dataset_count(self, exec_dataset_ids):
        # L.6.3 — exec_transaction_summary + exec_account_summary = 2.
        assert len(exec_dataset_ids) == 2
