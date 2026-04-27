"""API tests: verify the L1 dashboard / analysis / datasets exist.

M.2c.2. Mirrors `test_inv_deployed_resources.py`. No data assertions —
this layer only checks AWS resources are present + healthy. Resource
counts derive from the `l1_app` tree (no hardcoded 5).
"""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestL1DashboardExists:
    def test_dashboard_status(self, qs_client, account_id, l1_dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=l1_dashboard_id,
        )
        status = resp["Dashboard"]["Version"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"L1 dashboard status is {status}, "
            "expected CREATION_SUCCESSFUL"
        )

    def test_dashboard_has_name(
        self, qs_client, account_id, l1_dashboard_id,
    ):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=l1_dashboard_id,
        )
        assert len(resp["Dashboard"]["Name"]) > 0


class TestL1AnalysisExists:
    def test_analysis_status(self, qs_client, account_id, l1_analysis_id):
        resp = qs_client.describe_analysis(
            AwsAccountId=account_id,
            AnalysisId=l1_analysis_id,
        )
        status = resp["Analysis"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"L1 analysis status is {status}, "
            "expected CREATION_SUCCESSFUL"
        )


class TestL1DatasetsExist:
    def test_all_datasets_exist(
        self, qs_client, account_id, l1_dataset_ids,
    ):
        for ds_id in l1_dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200, (
                f"L1 dataset {ds_id} not found"
            )

    def test_dataset_count_matches_tree(self, l1_app, l1_dataset_ids):
        """Tree-derived count: every dataset registered on the App tree
        has a corresponding fixture entry. No hardcoded 5."""
        assert len(l1_dataset_ids) == len(l1_app.datasets)
