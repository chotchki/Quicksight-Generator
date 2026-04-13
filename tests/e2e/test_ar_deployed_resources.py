"""API tests: verify the Account Recon dashboard/analysis/datasets exist."""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestArDashboardExists:
    def test_dashboard_status(self, qs_client, account_id, ar_dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=ar_dashboard_id,
        )
        status = resp["Dashboard"]["Version"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"AR dashboard status is {status}, expected CREATION_SUCCESSFUL"
        )

    def test_dashboard_has_name(self, qs_client, account_id, ar_dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=ar_dashboard_id,
        )
        assert len(resp["Dashboard"]["Name"]) > 0


class TestArAnalysisExists:
    def test_analysis_status(self, qs_client, account_id, ar_analysis_id):
        resp = qs_client.describe_analysis(
            AwsAccountId=account_id,
            AnalysisId=ar_analysis_id,
        )
        status = resp["Analysis"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"AR analysis status is {status}, expected CREATION_SUCCESSFUL"
        )


class TestArDatasetsExist:
    def test_all_datasets_exist(self, qs_client, account_id, ar_dataset_ids):
        for ds_id in ar_dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200, (
                f"AR dataset {ds_id} not found"
            )

    def test_dataset_count(self, ar_dataset_ids):
        assert len(ar_dataset_ids) == 7
