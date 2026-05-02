"""Unit tests for src/quicksight_gen/common/deploy.py — focuses on the
dataset-scoping logic that keeps `deploy <single-app>` from clobbering
the *other* app's datasets and leaving its analysis with stale refs.
"""

from __future__ import annotations

import json
from pathlib import Path

from quicksight_gen.common.deploy import AppFiles, _dataset_ids_for_apps


def _write_analysis(path: Path, dataset_ids: list[str]) -> None:
    payload = {
        "AnalysisId": path.stem,
        "Definition": {
            "DataSetIdentifierDeclarations": [
                {
                    "Identifier": ds_id,
                    "DataSetArn": f"arn:aws:quicksight:us-east-1:111111111111:dataset/{ds_id}",
                }
                for ds_id in dataset_ids
            ],
        },
    }
    path.write_text(json.dumps(payload))


class TestDatasetIdsForApps:
    def test_single_app_returns_only_its_datasets(self, tmp_path: Path) -> None:
        inv_analysis = tmp_path / "investigation-analysis.json"
        _write_analysis(inv_analysis, ["qs-gen-inv-foo", "qs-gen-inv-bar"])
        apps = [AppFiles(name="investigation", analysis_path=inv_analysis,
                         dashboard_path=tmp_path / "investigation-dashboard.json")]

        assert _dataset_ids_for_apps(apps) == {"qs-gen-inv-foo", "qs-gen-inv-bar"}

    def test_two_apps_returns_union(self, tmp_path: Path) -> None:
        inv_analysis = tmp_path / "investigation-analysis.json"
        exec_analysis = tmp_path / "executives-analysis.json"
        _write_analysis(inv_analysis, ["qs-gen-inv-foo"])
        _write_analysis(exec_analysis, ["qs-gen-exec-foo", "qs-gen-exec-bar"])
        apps = [
            AppFiles(name="investigation", analysis_path=inv_analysis,
                     dashboard_path=tmp_path / "investigation-dashboard.json"),
            AppFiles(name="executives", analysis_path=exec_analysis,
                     dashboard_path=tmp_path / "executives-dashboard.json"),
        ]

        assert _dataset_ids_for_apps(apps) == {
            "qs-gen-inv-foo", "qs-gen-exec-foo", "qs-gen-exec-bar",
        }

    def test_missing_analysis_file_is_skipped(self, tmp_path: Path) -> None:
        apps = [AppFiles(name="ghost", analysis_path=tmp_path / "missing.json",
                         dashboard_path=tmp_path / "missing-dashboard.json")]
        assert _dataset_ids_for_apps(apps) == set()
