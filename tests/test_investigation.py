"""Tests for the Investigation app.

K.4.2 shipped the skeleton (4 sheets, no datasets / filters / visuals).
K.4.3 lands the Recipient Fanout sheet — recipient-fanout dataset +
contract, two filter groups (window date-range + threshold on the
analysis-level distinct-sender calc field), an integer parameter +
slider control, three KPIs, and a recipient-grain ranked table.
K.4.4 lands the Volume Anomalies sheet — pair-grain matview-backed
dataset, two filter groups (window date-range + σ threshold on z_score,
the latter scoped SELECTED_VISUALS to exclude the distribution chart),
an integer σ parameter + slider, and three visuals (KPI + distribution
bar + flagged table). Money Trail remains a stub until K.4.5.
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
    DS_INV_VOLUME_ANOMALIES,
    FG_INV_ANOMALIES_SIGMA,
    FG_INV_ANOMALIES_WINDOW,
    FG_INV_FANOUT_THRESHOLD,
    FG_INV_FANOUT_WINDOW,
    P_INV_ANOMALIES_SIGMA,
    P_INV_FANOUT_THRESHOLD,
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    SHEET_INV_MONEY_TRAIL,
    V_INV_ANOMALIES_DISTRIBUTION,
    V_INV_ANOMALIES_KPI_FLAGGED,
    V_INV_ANOMALIES_TABLE,
    V_INV_FANOUT_KPI_AMOUNT,
    V_INV_FANOUT_KPI_RECIPIENTS,
    V_INV_FANOUT_KPI_SENDERS,
    V_INV_FANOUT_TABLE,
)
from quicksight_gen.apps.investigation.datasets import (
    RECIPIENT_FANOUT_CONTRACT,
    VOLUME_ANOMALIES_CONTRACT,
    build_all_datasets,
)
from quicksight_gen.apps.investigation.demo_data import generate_demo_sql
from quicksight_gen.apps.investigation.filters import (
    DEFAULT_ANOMALIES_SIGMA,
    DEFAULT_FANOUT_THRESHOLD,
    SIGMA_SLIDER_MAX,
    SIGMA_SLIDER_MIN,
    SLIDER_MAX,
    SLIDER_MIN,
    build_anomalies_filter_controls,
    build_anomalies_parameter_controls,
    build_fanout_filter_controls,
    build_fanout_parameter_controls,
    build_filter_groups,
    build_parameter_declarations,
)
from quicksight_gen.cli import main
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import SheetVisualScopingConfiguration
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
    """Money Trail still names K.4.5 in its description so deployed-
    skeleton viewers know what's next. Recipient Fanout (K.4.3) and
    Volume Anomalies (K.4.4) are live and no longer need the cue."""
    analysis = build_analysis(_TEST_CFG)
    stubs = {s.SheetId: s for s in analysis.Definition.Sheets}
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

def test_investigation_datasets_in_expected_order():
    """K.4.3 dataset first, K.4.4 matview-backed dataset second. Order
    matters — analysis.py's DataSetIdentifierDeclarations zip relies on
    it."""
    datasets = build_all_datasets(_TEST_CFG)
    assert len(datasets) == 2
    assert datasets[0].DataSetId == _TEST_CFG.prefixed("inv-recipient-fanout-dataset")
    assert datasets[1].DataSetId == _TEST_CFG.prefixed("inv-volume-anomalies-dataset")


def test_investigation_datasets_declared_in_analysis():
    analysis = build_analysis(_TEST_CFG)
    decls = analysis.Definition.DataSetIdentifierDeclarations
    assert [d.Identifier for d in decls] == [
        DS_INV_RECIPIENT_FANOUT,
        DS_INV_VOLUME_ANOMALIES,
    ]


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

def test_filter_groups_in_expected_order():
    """Two K.4.3 fanout filter groups, then two K.4.4 anomalies filter
    groups. Order is stable so the deployed Definition diff is readable."""
    groups = build_filter_groups(_TEST_CFG)
    ids = [g.FilterGroupId for g in groups]
    assert ids == [
        FG_INV_FANOUT_WINDOW,
        FG_INV_FANOUT_THRESHOLD,
        FG_INV_ANOMALIES_WINDOW,
        FG_INV_ANOMALIES_SIGMA,
    ]


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


def test_parameter_declarations_carry_both_thresholds():
    decls = build_parameter_declarations(_TEST_CFG)
    assert len(decls) == 2
    by_name = {
        d.IntegerParameterDeclaration.Name: d.IntegerParameterDeclaration
        for d in decls if d.IntegerParameterDeclaration
    }
    assert by_name[P_INV_FANOUT_THRESHOLD].DefaultValues == {
        "StaticValues": [DEFAULT_FANOUT_THRESHOLD],
    }
    assert by_name[P_INV_ANOMALIES_SIGMA].DefaultValues == {
        "StaticValues": [DEFAULT_ANOMALIES_SIGMA],
    }


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
    # Top-level: 4 filter groups (2 fanout + 2 anomalies), 1 calc field
    # (fanout distinct count), 2 parameters (fanout threshold + sigma).
    assert len(j["Definition"]["FilterGroups"]) == 4
    assert len(j["Definition"]["CalculatedFields"]) == 1
    assert len(j["Definition"]["ParameterDeclarations"]) == 2


# ---------------------------------------------------------------------------
# K.4.4 — Volume Anomalies dataset + matview wiring
# ---------------------------------------------------------------------------

def test_volume_anomalies_contract_exposes_z_score_and_bucket():
    names = VOLUME_ANOMALIES_CONTRACT.column_names
    # Pair identity
    assert "sender_account_id" in names
    assert "recipient_account_id" in names
    # Window bounds
    assert "window_start" in names
    assert "window_end" in names
    # Aggregates + population stats
    assert "window_sum" in names
    assert "transfer_count" in names
    assert "pop_mean" in names
    assert "pop_stddev" in names
    # Anomaly scoring
    assert "z_score" in names
    assert "z_bucket" in names


def test_volume_anomalies_dataset_reads_from_matview():
    """Dataset is a thin SELECT over the matview — no inline windowing
    or population-stat math at dataset time. The whole point of the
    matview is to keep that work out of QuickSight Direct Query."""
    datasets = build_all_datasets(_TEST_CFG)
    anomalies = datasets[1]
    sql = next(iter(anomalies.PhysicalTableMap.values())).CustomSql.SqlQuery
    assert "FROM inv_pair_rolling_anomalies" in sql
    # Don't reach back into transactions / daily_balances at dataset load.
    assert "transactions" not in sql
    assert "OVER" not in sql
    assert "STDDEV" not in sql.upper()


# ---------------------------------------------------------------------------
# K.4.4 — Anomalies filter groups + parameter
# ---------------------------------------------------------------------------

def test_anomalies_window_filter_is_a_time_range_on_window_end():
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    window = groups[FG_INV_ANOMALIES_WINDOW]
    trf = window.Filters[0].TimeRangeFilter
    assert trf is not None
    assert trf.Column.ColumnName == "window_end"
    assert trf.Column.DataSetIdentifier == DS_INV_VOLUME_ANOMALIES


def test_sigma_filter_is_parameter_bound_on_z_score():
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    sigma = groups[FG_INV_ANOMALIES_SIGMA]
    nrf = sigma.Filters[0].NumericRangeFilter
    assert nrf is not None
    assert nrf.Column.ColumnName == "z_score"
    assert nrf.RangeMinimum is not None
    assert nrf.RangeMinimum.Parameter == P_INV_ANOMALIES_SIGMA
    assert nrf.RangeMaximum is None
    assert nrf.IncludeMinimum is True


def test_sigma_filter_is_scoped_to_kpi_and_table_only():
    """Distribution chart MUST see the full population — its scope
    deliberately excludes the chart visual id. Otherwise the analyst
    loses the reference frame for where the slider cutoff lies."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    sigma = groups[FG_INV_ANOMALIES_SIGMA]
    sheet_scopes = (
        sigma.ScopeConfiguration.SelectedSheets.SheetVisualScopingConfigurations
    )
    assert len(sheet_scopes) == 1
    scope = sheet_scopes[0]
    assert scope.SheetId == SHEET_INV_ANOMALIES
    assert scope.Scope == SheetVisualScopingConfiguration.SELECTED_VISUALS
    assert set(scope.VisualIds) == {
        V_INV_ANOMALIES_KPI_FLAGGED, V_INV_ANOMALIES_TABLE,
    }
    assert V_INV_ANOMALIES_DISTRIBUTION not in scope.VisualIds


def test_anomalies_window_filter_is_all_visuals_scope():
    """Window filter applies to every visual on the sheet — both the
    KPI/table and the distribution chart should respect the date range."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    window = groups[FG_INV_ANOMALIES_WINDOW]
    sheet_scopes = (
        window.ScopeConfiguration.SelectedSheets.SheetVisualScopingConfigurations
    )
    assert len(sheet_scopes) == 1
    assert sheet_scopes[0].Scope == SheetVisualScopingConfiguration.ALL_VISUALS


def test_anomalies_sheet_carries_window_filter_and_sigma_slider():
    fc = build_anomalies_filter_controls(_TEST_CFG)
    pc = build_anomalies_parameter_controls(_TEST_CFG)
    assert len(fc) == 1
    assert fc[0].DateTimePicker is not None
    assert len(pc) == 1
    slider = pc[0].Slider
    assert slider is not None
    assert slider.SourceParameterName == P_INV_ANOMALIES_SIGMA
    assert slider.MinimumValue == SIGMA_SLIDER_MIN
    assert slider.MaximumValue == SIGMA_SLIDER_MAX
    assert slider.StepSize == 1


# ---------------------------------------------------------------------------
# K.4.4 — Volume Anomalies sheet visuals + layout
# ---------------------------------------------------------------------------

def test_anomalies_sheet_has_kpi_distribution_and_table():
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ANOMALIES
    )
    assert sheet.Visuals is not None
    visual_ids = []
    for v in sheet.Visuals:
        if v.KPIVisual:
            visual_ids.append(v.KPIVisual.VisualId)
        elif v.BarChartVisual:
            visual_ids.append(v.BarChartVisual.VisualId)
        elif v.TableVisual:
            visual_ids.append(v.TableVisual.VisualId)
        else:
            visual_ids.append(None)
    assert visual_ids == [
        V_INV_ANOMALIES_KPI_FLAGGED,
        V_INV_ANOMALIES_DISTRIBUTION,
        V_INV_ANOMALIES_TABLE,
    ]


def test_distribution_chart_categorises_by_z_bucket():
    """Distribution chart's X-axis is the z-bucket dimension (e.g.
    '0-1 sigma', '1-2 sigma', ...). The Y-axis counts pair-window rows."""
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ANOMALIES
    )
    chart = next(v.BarChartVisual for v in sheet.Visuals if v.BarChartVisual)
    fields = chart.ChartConfiguration.FieldWells.BarChartAggregatedFieldWells
    cat_cols = [
        d.CategoricalDimensionField.Column.ColumnName
        for d in fields.Category if d.CategoricalDimensionField
    ]
    assert cat_cols == ["z_bucket"]
    assert len(fields.Values) == 1


def test_anomalies_table_sorted_by_z_score_desc():
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ANOMALIES
    )
    table = next(v.TableVisual for v in sheet.Visuals if v.TableVisual)
    sort = table.ChartConfiguration.SortConfiguration["RowSort"][0]["FieldSort"]
    assert sort["FieldId"] == "inv-anomalies-tbl-z-score"
    assert sort["Direction"] == "DESC"


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
