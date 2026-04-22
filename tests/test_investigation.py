"""Tests for the Investigation app.

K.4.2 shipped the skeleton (4 sheets, no datasets / filters / visuals).
K.4.3 lands the Recipient Fanout sheet — recipient-fanout dataset +
contract, two filter groups (window date-range + threshold on the
analysis-level distinct-sender calc field), an integer parameter +
slider control, three KPIs, and a recipient-grain ranked table. Volume
Anomalies / Money Trail remain stubs until K.4.4 / K.4.5.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from quicksight_gen.apps.investigation.analysis import (
    build_analysis,
    build_investigation_dashboard,
)
from quicksight_gen.apps.investigation.constants import (
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_RECIPIENT_FANOUT,
    FG_INV_FANOUT_THRESHOLD,
    FG_INV_FANOUT_WINDOW,
    P_INV_FANOUT_THRESHOLD,
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    SHEET_INV_MONEY_TRAIL,
    V_INV_FANOUT_KPI_AMOUNT,
    V_INV_FANOUT_KPI_RECIPIENTS,
    V_INV_FANOUT_KPI_SENDERS,
    V_INV_FANOUT_TABLE,
)
from quicksight_gen.apps.investigation.datasets import (
    RECIPIENT_FANOUT_CONTRACT,
    build_all_datasets,
)
from quicksight_gen.apps.investigation.demo_data import generate_demo_sql
from quicksight_gen.apps.investigation.filters import (
    DEFAULT_FANOUT_THRESHOLD,
    SLIDER_MAX,
    SLIDER_MIN,
    build_fanout_filter_controls,
    build_fanout_parameter_controls,
    build_filter_groups,
    build_parameter_declarations,
)
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
# Top-level shape
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


def test_every_sheet_has_a_description():
    """Plain-language description per sheet — enforced across all apps."""
    analysis = build_analysis(_TEST_CFG)
    for sheet in analysis.Definition.Sheets:
        assert sheet.Description, f"{sheet.SheetId} is missing a description"


def test_remaining_stub_sheets_reference_their_future_phase():
    """Volume Anomalies + Money Trail still name K.4.4 / K.4.5 in their
    descriptions so deployed-skeleton viewers know what's next.
    Recipient Fanout no longer needs the cue — it's live as of K.4.3."""
    analysis = build_analysis(_TEST_CFG)
    stubs = {s.SheetId: s for s in analysis.Definition.Sheets}
    assert "K.4.4" in stubs[SHEET_INV_ANOMALIES].Description
    assert "K.4.5" in stubs[SHEET_INV_MONEY_TRAIL].Description


def test_analysis_serializes_to_aws_json():
    """to_aws_json() must succeed end-to-end — no None-strip crashes."""
    j = build_analysis(_TEST_CFG).to_aws_json()
    assert j["AnalysisId"] == _TEST_CFG.prefixed("investigation-analysis")
    assert len(j["Definition"]["Sheets"]) == 4


def test_demo_sql_is_a_string():
    """Skeleton emits a comment-only seed; K.4.6 plants the scenarios."""
    sql = generate_demo_sql()
    assert isinstance(sql, str)
    assert sql.strip()  # non-empty (even if only a comment)


# ---------------------------------------------------------------------------
# K.4.3 — Recipient Fanout dataset
# ---------------------------------------------------------------------------

def test_recipient_fanout_dataset_is_only_dataset():
    datasets = build_all_datasets(_TEST_CFG)
    assert len(datasets) == 1
    assert datasets[0].DataSetId == _TEST_CFG.prefixed("inv-recipient-fanout-dataset")


def test_recipient_fanout_dataset_declared_in_analysis():
    analysis = build_analysis(_TEST_CFG)
    decls = analysis.Definition.DataSetIdentifierDeclarations
    assert [d.Identifier for d in decls] == [DS_INV_RECIPIENT_FANOUT]


def test_recipient_fanout_contract_columns():
    """Contract names every column the SQL projects — required for the
    threshold calc field and the table's group-by to resolve."""
    names = RECIPIENT_FANOUT_CONTRACT.column_names
    assert "recipient_account_id" in names
    assert "sender_account_id" in names
    assert "transfer_id" in names
    assert "posted_at" in names
    assert "amount" in names


def test_recipient_fanout_sql_filters_recipient_to_dda_types():
    """Administrative sweeps land in gl_control / concentration_master
    accounts — those would dominate the fanout ranking. Filter limits
    recipients to dda + merchant_dda so the signal is meaningful."""
    ds = build_all_datasets(_TEST_CFG)[0]
    sql = next(iter(ds.PhysicalTableMap.values())).CustomSql.SqlQuery
    assert "account_type IN ('dda', 'merchant_dda')" in sql


# ---------------------------------------------------------------------------
# K.4.3 — Filter groups + parameter
# ---------------------------------------------------------------------------

def test_filter_groups_window_and_threshold():
    groups = build_filter_groups(_TEST_CFG)
    ids = [g.FilterGroupId for g in groups]
    assert ids == [FG_INV_FANOUT_WINDOW, FG_INV_FANOUT_THRESHOLD]


def test_threshold_filter_is_parameter_bound_on_calc_field():
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    threshold = groups[FG_INV_FANOUT_THRESHOLD]
    nrf = threshold.Filters[0].NumericRangeFilter
    assert nrf is not None
    # Filter applies to the analysis-level calc field, not a physical column.
    assert nrf.Column.ColumnName == CF_INV_FANOUT_DISTINCT_SENDERS
    # Bound to the slider's parameter.
    assert nrf.RangeMinimum is not None
    assert nrf.RangeMinimum.Parameter == P_INV_FANOUT_THRESHOLD
    assert nrf.RangeMaximum is None  # no upper bound
    assert nrf.IncludeMinimum is True


def test_window_filter_is_a_time_range_on_posted_at():
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    window = groups[FG_INV_FANOUT_WINDOW]
    trf = window.Filters[0].TimeRangeFilter
    assert trf is not None
    assert trf.Column.ColumnName == "posted_at"
    assert trf.Column.DataSetIdentifier == DS_INV_RECIPIENT_FANOUT


def test_threshold_parameter_declaration_defaults_to_constant():
    decls = build_parameter_declarations(_TEST_CFG)
    assert len(decls) == 1
    integer = decls[0].IntegerParameterDeclaration
    assert integer is not None
    assert integer.Name == P_INV_FANOUT_THRESHOLD
    assert integer.DefaultValues == {"StaticValues": [DEFAULT_FANOUT_THRESHOLD]}


def test_fanout_sheet_carries_window_filter_and_threshold_slider():
    fc = build_fanout_filter_controls(_TEST_CFG)
    pc = build_fanout_parameter_controls(_TEST_CFG)
    assert len(fc) == 1
    assert fc[0].DateTimePicker is not None  # date range widget
    assert len(pc) == 1
    slider = pc[0].Slider
    assert slider is not None
    assert slider.SourceParameterName == P_INV_FANOUT_THRESHOLD
    assert slider.MinimumValue == SLIDER_MIN
    assert slider.MaximumValue == SLIDER_MAX
    assert slider.StepSize == 1


# ---------------------------------------------------------------------------
# K.4.3 — Calc field
# ---------------------------------------------------------------------------

def test_distinct_sender_calc_field_declared_at_analysis_level():
    analysis = build_analysis(_TEST_CFG)
    cfs = {cf["Name"]: cf for cf in analysis.Definition.CalculatedFields or []}
    cf = cfs.get(CF_INV_FANOUT_DISTINCT_SENDERS)
    assert cf is not None
    assert cf["DataSetIdentifier"] == DS_INV_RECIPIENT_FANOUT
    # Windowed distinct count partitioned by recipient — every row of a
    # recipient gets the same value, which is what the threshold filter
    # narrows on.
    assert "distinct_count" in cf["Expression"]
    assert "{sender_account_id}" in cf["Expression"]
    assert "{recipient_account_id}" in cf["Expression"]


# ---------------------------------------------------------------------------
# K.4.3 — Recipient Fanout sheet visuals + layout
# ---------------------------------------------------------------------------

def test_fanout_sheet_has_three_kpis_and_one_table():
    analysis = build_analysis(_TEST_CFG)
    fanout = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_INV_FANOUT
    )
    assert fanout.Visuals is not None
    visual_ids = [
        (v.KPIVisual.VisualId if v.KPIVisual else
         v.TableVisual.VisualId if v.TableVisual else None)
        for v in fanout.Visuals
    ]
    assert visual_ids == [
        V_INV_FANOUT_KPI_RECIPIENTS,
        V_INV_FANOUT_KPI_SENDERS,
        V_INV_FANOUT_KPI_AMOUNT,
        V_INV_FANOUT_TABLE,
    ]


def test_fanout_table_aggregates_to_recipient_grain():
    analysis = build_analysis(_TEST_CFG)
    fanout = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_INV_FANOUT
    )
    table = next(v.TableVisual for v in fanout.Visuals if v.TableVisual)
    field_wells = table.ChartConfiguration.FieldWells
    # Aggregated, not unaggregated — table groups by recipient identity.
    assert field_wells.TableAggregatedFieldWells is not None
    group_by_cols = [
        d.CategoricalDimensionField.Column.ColumnName
        for d in field_wells.TableAggregatedFieldWells.GroupBy
        if d.CategoricalDimensionField
    ]
    assert group_by_cols == [
        "recipient_account_id",
        "recipient_account_name",
        "recipient_account_type",
    ]


def test_fanout_sheet_serializes_to_aws_json():
    """End-to-end serialization sanity: filters, calc fields, params,
    visuals, and layout all surface without dataclass-shape errors."""
    j = build_analysis(_TEST_CFG).to_aws_json()
    fanout = next(
        s for s in j["Definition"]["Sheets"] if s["SheetId"] == SHEET_INV_FANOUT
    )
    assert len(fanout["Visuals"]) == 4
    assert len(fanout["FilterControls"]) == 1
    assert len(fanout["ParameterControls"]) == 1
    assert len(j["Definition"]["FilterGroups"]) == 2
    assert len(j["Definition"]["CalculatedFields"]) == 1
    assert len(j["Definition"]["ParameterDeclarations"]) == 1


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
    # K.4.3 — recipient-fanout dataset JSON must be written too.
    fanout_ds = out_dir / "datasets" / (
        _TEST_CFG.prefixed("inv-recipient-fanout-dataset") + ".json"
    )
    assert fanout_ds.is_file()


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
