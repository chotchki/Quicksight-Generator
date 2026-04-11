"""Smoke test for the full generate pipeline + cross-reference validation."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.cli import main


@pytest.fixture()
def output_dir(tmp_path: Path) -> Path:
    """Run the generate command and return the output directory."""
    config = tmp_path / "config.yaml"
    config.write_text(
        "aws_account_id: '111122223333'\n"
        "aws_region: us-west-2\n"
        "datasource_arn: arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds\n"
        "principal_arn: arn:aws:quicksight:us-west-2:111122223333:user/default/admin\n"
    )
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(main, ["generate", "-c", str(config), "-o", str(out)])
    assert result.exit_code == 0, result.output
    return out


class TestGenerateOutput:
    def test_theme_file_exists(self, output_dir: Path):
        assert (output_dir / "theme.json").exists()

    def test_analysis_file_exists(self, output_dir: Path):
        assert (output_dir / "analysis.json").exists()

    def test_dataset_files_exist(self, output_dir: Path):
        ds_dir = output_dir / "datasets"
        assert ds_dir.exists()
        ds_files = list(ds_dir.glob("*.json"))
        assert len(ds_files) == 6

    def test_all_files_valid_json(self, output_dir: Path):
        for path in output_dir.rglob("*.json"):
            data = json.loads(path.read_text())
            assert isinstance(data, dict), f"{path} is not a JSON object"

    def test_theme_has_account_id(self, output_dir: Path):
        theme = json.loads((output_dir / "theme.json").read_text())
        assert theme["AwsAccountId"] == "111122223333"

    def test_datasets_reference_datasource(self, output_dir: Path):
        for path in (output_dir / "datasets").glob("*.json"):
            ds = json.loads(path.read_text())
            for table in ds["PhysicalTableMap"].values():
                arn = table["CustomSql"]["DataSourceArn"]
                assert "test-ds" in arn

    def test_permissions_set_when_principal_provided(self, output_dir: Path):
        theme = json.loads((output_dir / "theme.json").read_text())
        assert "Permissions" in theme
        assert len(theme["Permissions"]) == 1
        assert "admin" in theme["Permissions"][0]["Principal"]

        analysis = json.loads((output_dir / "analysis.json").read_text())
        assert "Permissions" in analysis

    def test_all_resources_have_common_tag(self, output_dir: Path):
        """Every generated resource must have the ManagedBy tag."""
        for path in output_dir.rglob("*.json"):
            data = json.loads(path.read_text())
            assert "Tags" in data, f"{path.name} missing Tags"
            tag_keys = {t["Key"] for t in data["Tags"]}
            assert "ManagedBy" in tag_keys, f"{path.name} missing ManagedBy tag"
            managed = next(t for t in data["Tags"] if t["Key"] == "ManagedBy")
            assert managed["Value"] == "quicksight-gen"


class TestCrossReferences:
    """Validate that all internal references are consistent."""

    def test_analysis_dataset_arns_match_datasets(self, output_dir: Path):
        """Every DataSetIdentifierDeclaration ARN should match a generated dataset."""
        analysis = json.loads((output_dir / "analysis.json").read_text())
        decls = analysis["Definition"]["DataSetIdentifierDeclarations"]
        declared_arns = {d["DataSetArn"] for d in decls}

        ds_dir = output_dir / "datasets"
        generated_ids = set()
        for path in ds_dir.glob("*.json"):
            ds = json.loads(path.read_text())
            generated_ids.add(ds["DataSetId"])

        # Each declared ARN should end with a generated dataset ID
        for arn in declared_arns:
            ds_id = arn.split("/")[-1]
            assert ds_id in generated_ids, f"ARN {arn} references unknown dataset {ds_id}"

    def test_visual_dataset_refs_are_declared(self, output_dir: Path):
        """Every DataSetIdentifier used in a visual must be declared."""
        analysis = json.loads((output_dir / "analysis.json").read_text())
        decls = analysis["Definition"]["DataSetIdentifierDeclarations"]
        declared_ids = {d["Identifier"] for d in decls}

        # Walk the full JSON tree looking for DataSetIdentifier keys
        found_refs = set()
        _collect_dataset_refs(analysis, found_refs)

        for ref in found_refs:
            assert ref in declared_ids, (
                f"DataSetIdentifier '{ref}' used in visual/filter "
                f"but not declared. Declared: {declared_ids}"
            )

    def test_theme_arn_matches_theme(self, output_dir: Path):
        analysis = json.loads((output_dir / "analysis.json").read_text())
        theme = json.loads((output_dir / "theme.json").read_text())
        theme_arn = analysis["ThemeArn"]
        assert theme["ThemeId"] in theme_arn

    def test_filter_source_ids_match(self, output_dir: Path):
        """Every FilterControl's SourceFilterId must match a filter in FilterGroups."""
        analysis = json.loads((output_dir / "analysis.json").read_text())
        defn = analysis["Definition"]

        # Collect all filter IDs from filter groups
        all_filter_ids = set()
        for fg in defn.get("FilterGroups", []):
            for f in fg["Filters"]:
                for filter_obj in f.values():
                    if isinstance(filter_obj, dict) and "FilterId" in filter_obj:
                        all_filter_ids.add(filter_obj["FilterId"])

        # Collect all SourceFilterIds from controls on every sheet
        for sheet in defn["Sheets"]:
            for ctrl in sheet.get("FilterControls", []):
                for ctrl_obj in ctrl.values():
                    if isinstance(ctrl_obj, dict) and "SourceFilterId" in ctrl_obj:
                        src = ctrl_obj["SourceFilterId"]
                        assert src in all_filter_ids, (
                            f"Control references filter '{src}' "
                            f"but it's not in FilterGroups. Known: {all_filter_ids}"
                        )

    def test_filter_scope_sheet_ids_exist(self, output_dir: Path):
        """Every SheetId in filter scopes must match a real sheet."""
        analysis = json.loads((output_dir / "analysis.json").read_text())
        defn = analysis["Definition"]

        real_sheet_ids = {s["SheetId"] for s in defn["Sheets"]}

        for fg in defn.get("FilterGroups", []):
            scope = fg["ScopeConfiguration"]
            if "SelectedSheets" in scope:
                for svc in scope["SelectedSheets"]["SheetVisualScopingConfigurations"]:
                    sid = svc["SheetId"]
                    assert sid in real_sheet_ids, (
                        f"Filter group '{fg['FilterGroupId']}' scopes to "
                        f"sheet '{sid}' which doesn't exist. Sheets: {real_sheet_ids}"
                    )

    def test_visual_ids_unique_across_analysis(self, output_dir: Path):
        analysis = json.loads((output_dir / "analysis.json").read_text())
        all_ids = []
        for sheet in analysis["Definition"]["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype in v.values():
                    if isinstance(vtype, dict) and "VisualId" in vtype:
                        all_ids.append(vtype["VisualId"])
        assert len(all_ids) == len(set(all_ids)), (
            f"Duplicate visual IDs: "
            f"{[vid for vid in all_ids if all_ids.count(vid) > 1]}"
        )


def _collect_dataset_refs(obj: object, refs: set[str]) -> None:
    """Recursively find all DataSetIdentifier values in a nested dict/list."""
    if isinstance(obj, dict):
        if "DataSetIdentifier" in obj:
            refs.add(obj["DataSetIdentifier"])
        for v in obj.values():
            _collect_dataset_refs(v, refs)
    elif isinstance(obj, list):
        for item in obj:
            _collect_dataset_refs(item, refs)
