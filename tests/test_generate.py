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
        "principal_arns:\n"
        "  - arn:aws:quicksight:us-west-2:111122223333:user/default/admin\n"
    )
    out = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main, ["generate", "-c", str(config), "-o", str(out), "payment-recon"],
    )
    assert result.exit_code == 0, result.output
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load(output_dir: Path, name: str) -> dict:
    return json.loads((output_dir / name).read_text())


def _validate_analysis_cross_refs(analysis: dict, output_dir: Path) -> None:
    """Shared cross-reference checks for any analysis."""
    defn = analysis["Definition"]

    # Dataset ARNs match generated datasets
    decls = defn["DataSetIdentifierDeclarations"]
    declared_arns = {d["DataSetArn"] for d in decls}
    ds_dir = output_dir / "datasets"
    generated_ids = set()
    for path in ds_dir.glob("*.json"):
        ds = json.loads(path.read_text())
        generated_ids.add(ds["DataSetId"])
    for arn in declared_arns:
        ds_id = arn.split("/")[-1]
        assert ds_id in generated_ids, f"ARN {arn} references unknown dataset {ds_id}"

    # Visual dataset refs are declared
    declared_ids = {d["Identifier"] for d in decls}
    found_refs: set[str] = set()
    _collect_dataset_refs(analysis, found_refs)
    for ref in found_refs:
        assert ref in declared_ids, (
            f"DataSetIdentifier '{ref}' used but not declared. Declared: {declared_ids}"
        )

    # Filter source IDs match
    all_filter_ids: set[str] = set()
    for fg in defn.get("FilterGroups", []):
        for f in fg["Filters"]:
            for filter_obj in f.values():
                if isinstance(filter_obj, dict) and "FilterId" in filter_obj:
                    all_filter_ids.add(filter_obj["FilterId"])
    for sheet in defn["Sheets"]:
        for ctrl in sheet.get("FilterControls", []):
            for ctrl_obj in ctrl.values():
                if isinstance(ctrl_obj, dict) and "SourceFilterId" in ctrl_obj:
                    src = ctrl_obj["SourceFilterId"]
                    assert src in all_filter_ids, (
                        f"Control references filter '{src}' not in FilterGroups"
                    )

    # Filter scope sheet IDs exist
    real_sheet_ids = {s["SheetId"] for s in defn["Sheets"]}
    for fg in defn.get("FilterGroups", []):
        scope = fg["ScopeConfiguration"]
        if "SelectedSheets" in scope:
            for svc in scope["SelectedSheets"]["SheetVisualScopingConfigurations"]:
                sid = svc["SheetId"]
                assert sid in real_sheet_ids, (
                    f"Filter group '{fg['FilterGroupId']}' scopes to "
                    f"unknown sheet '{sid}'"
                )

    # Visual IDs unique
    all_ids = []
    for sheet in defn["Sheets"]:
        for v in sheet.get("Visuals", []):
            for vtype in v.values():
                if isinstance(vtype, dict) and "VisualId" in vtype:
                    all_ids.append(vtype["VisualId"])
    assert len(all_ids) == len(set(all_ids)), (
        f"Duplicate visual IDs: {[vid for vid in all_ids if all_ids.count(vid) > 1]}"
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


# ---------------------------------------------------------------------------
# Output file tests
# ---------------------------------------------------------------------------

class TestGenerateOutput:
    def test_theme_file_exists(self, output_dir: Path):
        assert (output_dir / "theme.json").exists()

    def test_payment_recon_analysis_file_exists(self, output_dir: Path):
        assert (output_dir / "payment-recon-analysis.json").exists()

    def test_payment_recon_dashboard_file_exists(self, output_dir: Path):
        assert (output_dir / "payment-recon-dashboard.json").exists()

    def test_dataset_files_exist(self, output_dir: Path):
        ds_dir = output_dir / "datasets"
        assert ds_dir.exists()
        ds_files = list(ds_dir.glob("*.json"))
        assert len(ds_files) == 8

    def test_all_files_valid_json(self, output_dir: Path):
        for path in output_dir.rglob("*.json"):
            data = json.loads(path.read_text())
            assert isinstance(data, dict), f"{path} is not a JSON object"

    def test_theme_has_account_id(self, output_dir: Path):
        theme = _load(output_dir, "theme.json")
        assert theme["AwsAccountId"] == "111122223333"

    def test_datasets_reference_datasource(self, output_dir: Path):
        for path in (output_dir / "datasets").glob("*.json"):
            ds = json.loads(path.read_text())
            for table in ds["PhysicalTableMap"].values():
                arn = table["CustomSql"]["DataSourceArn"]
                assert "test-ds" in arn

    def test_permissions_set_when_principal_provided(self, output_dir: Path):
        theme = _load(output_dir, "theme.json")
        assert "Permissions" in theme
        assert len(theme["Permissions"]) == 1
        assert "admin" in theme["Permissions"][0]["Principal"]

        analysis = _load(output_dir, "payment-recon-analysis.json")
        assert "Permissions" in analysis, "payment-recon-analysis.json missing Permissions"

    def test_all_resources_have_common_tag(self, output_dir: Path):
        """Every generated resource must have the ManagedBy tag."""
        for path in output_dir.rglob("*.json"):
            data = json.loads(path.read_text())
            assert "Tags" in data, f"{path.name} missing Tags"
            tag_keys = {t["Key"] for t in data["Tags"]}
            assert "ManagedBy" in tag_keys, f"{path.name} missing ManagedBy tag"
            managed = next(t for t in data["Tags"] if t["Key"] == "ManagedBy")
            assert managed["Value"] == "quicksight-gen"


# ---------------------------------------------------------------------------
# Cross-reference tests — payment recon analysis
# ---------------------------------------------------------------------------

class TestPaymentReconCrossReferences:
    def test_cross_refs(self, output_dir: Path):
        analysis = _load(output_dir, "payment-recon-analysis.json")
        _validate_analysis_cross_refs(analysis, output_dir)

    def test_theme_arn_matches_theme(self, output_dir: Path):
        analysis = _load(output_dir, "payment-recon-analysis.json")
        theme = _load(output_dir, "theme.json")
        assert theme["ThemeId"] in analysis["ThemeArn"]


# ---------------------------------------------------------------------------
# Explanation coverage tests
# ---------------------------------------------------------------------------

class TestExplanations:
    def test_every_sheet_has_description(self, output_dir: Path):
        analysis = _load(output_dir, "payment-recon-analysis.json")
        for sheet in analysis["Definition"]["Sheets"]:
            desc = sheet.get("Description", "")
            assert len(desc) > 20, (
                f"Sheet '{sheet.get('Name', sheet['SheetId'])}' "
                f"has no meaningful description"
            )

    def test_every_visual_has_subtitle(self, output_dir: Path):
        analysis = _load(output_dir, "payment-recon-analysis.json")
        for sheet in analysis["Definition"]["Sheets"]:
            for v in sheet.get("Visuals", []):
                for vtype_name, vtype in v.items():
                    if isinstance(vtype, dict) and "VisualId" in vtype:
                        subtitle = vtype.get("Subtitle", {})
                        fmt = subtitle.get("FormatText", {})
                        text = fmt.get("PlainText", "")
                        assert len(text) > 10, (
                            f"Visual '{vtype['VisualId']}' on sheet "
                            f"'{sheet.get('Name', sheet['SheetId'])}' "
                            f"has no meaningful subtitle"
                        )
