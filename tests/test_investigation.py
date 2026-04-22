"""Tests for the Investigation app (K.4.2 skeleton)."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from quicksight_gen.apps.investigation.analysis import (
    build_analysis,
    build_investigation_dashboard,
)
from quicksight_gen.apps.investigation.constants import (
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    SHEET_INV_MONEY_TRAIL,
)
from quicksight_gen.apps.investigation.datasets import build_all_datasets
from quicksight_gen.apps.investigation.demo_data import generate_demo_sql
from quicksight_gen.apps.investigation.filters import build_filter_groups
from quicksight_gen.cli import main
from quicksight_gen.common.config import Config
from quicksight_gen.common.theme import PRESETS, get_preset


_TEST_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="sasquatch-bank-investigation",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


# ---------------------------------------------------------------------------
# Theme preset
# ---------------------------------------------------------------------------

def test_investigation_theme_preset_registered():
    assert "sasquatch-bank-investigation" in PRESETS
    preset = get_preset("sasquatch-bank-investigation")
    assert preset.analysis_name_prefix == "Demo"
    # Distinct accent from PR / AR (slate vs forest vs valley green)
    assert preset.accent != get_preset("sasquatch-bank").accent
    assert preset.accent != get_preset("sasquatch-bank-ar").accent


# ---------------------------------------------------------------------------
# Skeleton shape
# ---------------------------------------------------------------------------

def test_analysis_has_four_sheets_in_expected_order():
    analysis = build_analysis(_TEST_CFG)
    sheet_ids = [s.SheetId for s in analysis.Definition.Sheets]
    assert sheet_ids == [
        SHEET_INV_GETTING_STARTED,
        SHEET_INV_FANOUT,
        SHEET_INV_ANOMALIES,
        SHEET_INV_MONEY_TRAIL,
    ]


def test_analysis_name_uses_demo_prefix():
    analysis = build_analysis(_TEST_CFG)
    assert analysis.Name == "Demo — Investigation"


def test_dashboard_mirrors_analysis_definition():
    analysis = build_analysis(_TEST_CFG)
    dashboard = build_investigation_dashboard(_TEST_CFG)
    # Both wrap the same definition builder, so sheet counts align.
    assert len(dashboard.Definition.Sheets) == len(analysis.Definition.Sheets)
    assert dashboard.DashboardId == _TEST_CFG.prefixed("investigation-dashboard")


def test_skeleton_carries_no_datasets_or_filters():
    assert build_all_datasets(_TEST_CFG) == []
    assert build_filter_groups(_TEST_CFG) == []
    analysis = build_analysis(_TEST_CFG)
    assert analysis.Definition.DataSetIdentifierDeclarations == []
    assert analysis.Definition.FilterGroups == []


def test_every_sheet_has_a_description():
    """Plain-language description per sheet — enforced across all apps."""
    analysis = build_analysis(_TEST_CFG)
    for sheet in analysis.Definition.Sheets:
        assert sheet.Description, f"{sheet.SheetId} is missing a description"


def test_stub_sheets_reference_their_future_phase():
    """Each stub sheet's description names K.4.3 / K.4.4 / K.4.5 so readers
    viewing a deployed skeleton know what's coming."""
    analysis = build_analysis(_TEST_CFG)
    stubs = {s.SheetId: s for s in analysis.Definition.Sheets}
    assert "K.4.3" in stubs[SHEET_INV_FANOUT].Description
    assert "K.4.4" in stubs[SHEET_INV_ANOMALIES].Description
    assert "K.4.5" in stubs[SHEET_INV_MONEY_TRAIL].Description


def test_analysis_serializes_to_aws_json():
    """to_aws_json() must succeed on the skeleton — no None-strip crashes."""
    j = build_analysis(_TEST_CFG).to_aws_json()
    assert j["AnalysisId"] == _TEST_CFG.prefixed("investigation-analysis")
    assert len(j["Definition"]["Sheets"]) == 4


def test_demo_sql_is_a_string():
    """Skeleton emits a comment-only seed; K.4.6 plants the scenarios."""
    sql = generate_demo_sql()
    assert isinstance(sql, str)
    assert sql.strip()  # non-empty (even if only a comment)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def _write_min_config(tmp_path: Path) -> Path:
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "aws_account_id: '111122223333'\n"
        "aws_region: us-west-2\n"
        "theme_preset: sasquatch-bank-investigation\n"
        "datasource_arn: 'arn:aws:quicksight:us-west-2:111122223333:datasource/x'\n",
        encoding="utf-8",
    )
    return cfg_path


def test_generate_investigation_subcommand_writes_files(tmp_path: Path):
    cfg_path = _write_min_config(tmp_path)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["generate", "-c", str(cfg_path), "-o", str(out_dir), "investigation"],
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "theme.json").is_file()
    assert (out_dir / "investigation-analysis.json").is_file()
    assert (out_dir / "investigation-dashboard.json").is_file()


def test_generate_all_writes_all_three_app_jsons(tmp_path: Path):
    cfg_path = _write_min_config(tmp_path)
    out_dir = tmp_path / "out-all"
    runner = CliRunner()
    result = runner.invoke(
        main, ["generate", "-c", str(cfg_path), "-o", str(out_dir), "--all"],
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "payment-recon-analysis.json").is_file()
    assert (out_dir / "account-recon-analysis.json").is_file()
    assert (out_dir / "investigation-analysis.json").is_file()
