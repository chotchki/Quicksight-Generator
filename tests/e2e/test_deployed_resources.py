"""API tests: verify all QuickSight resources exist and are healthy."""

from __future__ import annotations

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.api]


class TestDashboardExists:
    def test_dashboard_status(self, qs_client, account_id, dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=dashboard_id,
        )
        status = resp["Dashboard"]["Version"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Dashboard status is {status}, expected CREATION_SUCCESSFUL"
        )

    def test_dashboard_has_name(self, qs_client, account_id, dashboard_id):
        resp = qs_client.describe_dashboard(
            AwsAccountId=account_id,
            DashboardId=dashboard_id,
        )
        name = resp["Dashboard"]["Name"]
        assert len(name) > 0


class TestAnalysisExists:
    def test_analysis_status(self, qs_client, account_id, analysis_id):
        resp = qs_client.describe_analysis(
            AwsAccountId=account_id,
            AnalysisId=analysis_id,
        )
        status = resp["Analysis"]["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Analysis status is {status}, expected CREATION_SUCCESSFUL"
        )


class TestThemeExists:
    def test_theme_status(self, qs_client, account_id, theme_id):
        resp = qs_client.describe_theme(
            AwsAccountId=account_id,
            ThemeId=theme_id,
        )
        version = resp["Theme"]["Version"]
        status = version["Status"]
        assert status == "CREATION_SUCCESSFUL", (
            f"Theme status is {status}, expected CREATION_SUCCESSFUL"
        )


class TestDatasetsExist:
    def test_all_datasets_exist(self, qs_client, account_id, dataset_ids):
        for ds_id in dataset_ids:
            resp = qs_client.describe_data_set(
                AwsAccountId=account_id,
                DataSetId=ds_id,
            )
            assert resp["ResponseMetadata"]["HTTPStatusCode"] == 200, (
                f"Dataset {ds_id} not found"
            )

    def test_dataset_count(self, qs_client, account_id, dataset_ids):
        assert len(dataset_ids) == 8
