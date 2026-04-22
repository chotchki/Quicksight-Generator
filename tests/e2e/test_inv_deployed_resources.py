"""API tests: verify the Investigation dashboard/analysis/datasets exist."""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestInvDashboardExists:
    def test_dashboard_status(self, qs_client, account_id, inv_dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=inv_dashboard_id,
        )
        status = resp["Dashboard"]["Version"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Investigation dashboard status is {status}, "
            "expected CREATION_SUCCESSFUL"
        )

    def test_dashboard_has_name(self, qs_client, account_id, inv_dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=inv_dashboard_id,
        )
        assert len(resp["Dashboard"]["Name"]) > 0


class TestInvAnalysisExists:
    def test_analysis_status(self, qs_client, account_id, inv_analysis_id):
        resp = qs_client.describe_analysis(
            AwsAccountId=account_id,
            AnalysisId=inv_analysis_id,
        )
        status = resp["Analysis"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Investigation analysis status is {status}, "
            "expected CREATION_SUCCESSFUL"
        )


class TestInvDatasetsExist:
    def test_all_datasets_exist(self, qs_client, account_id, inv_dataset_ids):
        for ds_id in inv_dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200, (
                f"Investigation dataset {ds_id} not found"
            )

    def test_dataset_count(self, inv_dataset_ids):
        # K.4.3 recipient-fanout + K.4.4 volume-anomalies + K.4.5
        # money-trail + K.4.8 account-network + K.4.8k narrow accounts
        # dataset = 5.
        assert len(inv_dataset_ids) == 5
