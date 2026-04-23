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
bar + flagged table).
K.4.5 lands the Money Trail sheet — matview-backed money-trail dataset
sourced from the recursive-CTE walk over ``parent_transfer_id``, three
filter groups (chain-root EQUALS via parameter-bound CategoryFilter,
max-hops on ``depth``, min-hop-amount on ``hop_amount`` — all scoped
ALL_VISUALS), three new parameters + controls (string root, integer
max-hops slider, integer min-amount slider), and a Sankey diagram +
hop-by-hop detail table side-by-side.
"""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from quicksight_gen.apps.investigation.app import (
    build_analysis,
    build_investigation_dashboard,
)
from quicksight_gen.apps.investigation.constants import (
    CF_INV_ANETWORK_COUNTERPARTY_DISPLAY,
    CF_INV_ANETWORK_IS_ANCHOR_EDGE,
    CF_INV_ANETWORK_IS_INBOUND_EDGE,
    CF_INV_ANETWORK_IS_OUTBOUND_EDGE,
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_ACCOUNT_NETWORK,
    DS_INV_ANETWORK_ACCOUNTS,
    DS_INV_MONEY_TRAIL,
    DS_INV_RECIPIENT_FANOUT,
    DS_INV_VOLUME_ANOMALIES,
    FG_INV_ANETWORK_AMOUNT,
    FG_INV_ANETWORK_ANCHOR,
    FG_INV_ANETWORK_INBOUND,
    FG_INV_ANETWORK_OUTBOUND,
    FG_INV_ANOMALIES_SIGMA,
    FG_INV_ANOMALIES_WINDOW,
    FG_INV_FANOUT_THRESHOLD,
    FG_INV_FANOUT_WINDOW,
    FG_INV_MONEY_TRAIL_AMOUNT,
    FG_INV_MONEY_TRAIL_HOPS,
    FG_INV_MONEY_TRAIL_ROOT,
    P_INV_ANETWORK_ANCHOR,
    P_INV_ANETWORK_MIN_AMOUNT,
    P_INV_ANOMALIES_SIGMA,
    P_INV_FANOUT_THRESHOLD,
    P_INV_MONEY_TRAIL_MAX_HOPS,
    P_INV_MONEY_TRAIL_MIN_AMOUNT,
    P_INV_MONEY_TRAIL_ROOT,
    SHEET_INV_ACCOUNT_NETWORK,
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    SHEET_INV_MONEY_TRAIL,
)
from quicksight_gen.apps.investigation.datasets import (
    MONEY_TRAIL_CONTRACT,
    RECIPIENT_FANOUT_CONTRACT,
    VOLUME_ANOMALIES_CONTRACT,
    build_all_datasets,
)
from quicksight_gen.apps.investigation.demo_data import generate_demo_sql
from quicksight_gen.apps.investigation.filters import (
    AMOUNT_SLIDER_MAX,
    AMOUNT_SLIDER_MIN,
    DEFAULT_ANOMALIES_SIGMA,
    DEFAULT_FANOUT_THRESHOLD,
    DEFAULT_MONEY_TRAIL_MAX_HOPS,
    DEFAULT_MONEY_TRAIL_MIN_AMOUNT,
    HOPS_SLIDER_MAX,
    HOPS_SLIDER_MIN,
    SIGMA_SLIDER_MAX,
    SIGMA_SLIDER_MIN,
    SLIDER_MAX,
    SLIDER_MIN,
    build_account_network_filter_controls,
    build_account_network_parameter_controls,
    build_anomalies_filter_controls,
    build_anomalies_parameter_controls,
    build_fanout_filter_controls,
    build_fanout_parameter_controls,
    build_filter_groups,
    build_money_trail_filter_controls,
    build_money_trail_parameter_controls,
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


def _visual_id_by_title(sheet, title: str) -> str:
    """Find a visual's auto-generated ID by walking the sheet's emitted
    Visuals list and matching on title. Visual_ids are auto-derived
    post-L.1.21; titles are the stable identifier for tests that pin
    individual visuals.
    """
    for v in sheet.Visuals:
        for inner_name in (
            "KPIVisual", "TableVisual", "BarChartVisual",
            "SankeyDiagramVisual", "PieChartVisual",
        ):
            inner = getattr(v, inner_name, None)
            if inner is None:
                continue
            inner_title = inner.Title.FormatText.get("PlainText")
            if inner_title == title:
                return inner.VisualId
    raise AssertionError(f"No visual on sheet matches title={title!r}")


def _visual_kinds(sheet) -> list[str]:
    """Return the kind ('KPIVisual', 'TableVisual', ...) of each visual
    on the sheet in order. Used in lieu of explicit visual_ids for
    "this sheet has [KPI, BarChart, Table] in this order" structure
    checks (visual_ids are auto-generated post-L.1.21)."""
    kinds: list[str] = []
    for v in sheet.Visuals:
        for inner_name in (
            "KPIVisual", "TableVisual", "BarChartVisual",
            "SankeyDiagramVisual", "PieChartVisual",
        ):
            if getattr(v, inner_name, None) is not None:
                kinds.append(inner_name)
                break
    return kinds


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

def test_analysis_has_five_sheets_in_expected_order():
    analysis = build_analysis(_TEST_CFG)
    sheet_ids = [s.SheetId for s in analysis.Definition.Sheets]
    assert sheet_ids == [
        SHEET_INV_GETTING_STARTED,
        SHEET_INV_FANOUT,
        SHEET_INV_ANOMALIES,
        SHEET_INV_MONEY_TRAIL,
        SHEET_INV_ACCOUNT_NETWORK,
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


def test_analysis_serializes_to_aws_json():
    """to_aws_json() must succeed end-to-end — no None-strip crashes."""
    j = build_analysis(_TEST_CFG).to_aws_json()
    assert j["AnalysisId"] == _TEST_CFG.prefixed("investigation-analysis")
    assert len(j["Definition"]["Sheets"]) == 5


def test_demo_sql_is_a_string():
    """Skeleton emits a comment-only seed; K.4.6 plants the scenarios."""
    sql = generate_demo_sql()
    assert isinstance(sql, str)
    assert sql.strip()  # non-empty (even if only a comment)


# ---------------------------------------------------------------------------
# K.4.3 — Recipient Fanout dataset
# ---------------------------------------------------------------------------

def test_investigation_datasets_in_expected_order():
    """K.4.3 dataset first, K.4.4 matview-backed dataset second, K.4.5
    money-trail matview dataset third, K.4.8 account-network wrapper
    fourth, K.4.8k narrow accounts dataset fifth. Order matters —
    analysis.py's DataSetIdentifierDeclarations zip relies on it."""
    datasets = build_all_datasets(_TEST_CFG)
    assert len(datasets) == 5
    assert datasets[0].DataSetId == _TEST_CFG.prefixed("inv-recipient-fanout-dataset")
    assert datasets[1].DataSetId == _TEST_CFG.prefixed("inv-volume-anomalies-dataset")
    assert datasets[2].DataSetId == _TEST_CFG.prefixed("inv-money-trail-dataset")
    assert datasets[3].DataSetId == _TEST_CFG.prefixed("inv-account-network-dataset")
    assert datasets[4].DataSetId == _TEST_CFG.prefixed("inv-anetwork-accounts-dataset")


def test_investigation_datasets_declared_in_analysis():
    analysis = build_analysis(_TEST_CFG)
    decls = analysis.Definition.DataSetIdentifierDeclarations
    assert [d.Identifier for d in decls] == [
        DS_INV_RECIPIENT_FANOUT,
        DS_INV_VOLUME_ANOMALIES,
        DS_INV_MONEY_TRAIL,
        DS_INV_ACCOUNT_NETWORK,
        DS_INV_ANETWORK_ACCOUNTS,
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
    groups, then three K.4.5 money-trail filter groups (root / hops /
    amount), then four K.4.8 account-network filter groups (anchor /
    inbound / outbound / amount). Order is stable so the deployed
    Definition diff is readable."""
    groups = build_filter_groups(_TEST_CFG)
    ids = [g.FilterGroupId for g in groups]
    assert ids == [
        FG_INV_FANOUT_WINDOW,
        FG_INV_FANOUT_THRESHOLD,
        FG_INV_ANOMALIES_WINDOW,
        FG_INV_ANOMALIES_SIGMA,
        FG_INV_MONEY_TRAIL_ROOT,
        FG_INV_MONEY_TRAIL_HOPS,
        FG_INV_MONEY_TRAIL_AMOUNT,
        FG_INV_ANETWORK_ANCHOR,
        FG_INV_ANETWORK_INBOUND,
        FG_INV_ANETWORK_OUTBOUND,
        FG_INV_ANETWORK_AMOUNT,
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
    """Seven parameters: K.4.3 fanout threshold, K.4.4 sigma threshold,
    K.4.5 money-trail root (string) + max-hops + min-amount (integers),
    K.4.8 account-network anchor (string) + min-amount (integer)."""
    decls = build_parameter_declarations(_TEST_CFG)
    assert len(decls) == 7
    int_by_name = {
        d.IntegerParameterDeclaration.Name: d.IntegerParameterDeclaration
        for d in decls if d.IntegerParameterDeclaration
    }
    assert int_by_name[P_INV_FANOUT_THRESHOLD].DefaultValues == {
        "StaticValues": [DEFAULT_FANOUT_THRESHOLD],
    }
    assert int_by_name[P_INV_ANOMALIES_SIGMA].DefaultValues == {
        "StaticValues": [DEFAULT_ANOMALIES_SIGMA],
    }
    assert int_by_name[P_INV_MONEY_TRAIL_MAX_HOPS].DefaultValues == {
        "StaticValues": [DEFAULT_MONEY_TRAIL_MAX_HOPS],
    }
    assert int_by_name[P_INV_MONEY_TRAIL_MIN_AMOUNT].DefaultValues == {
        "StaticValues": [DEFAULT_MONEY_TRAIL_MIN_AMOUNT],
    }
    # K.4.8 anchor amount slider reuses Money Trail's default of 0.
    assert int_by_name[P_INV_ANETWORK_MIN_AMOUNT].DefaultValues == {
        "StaticValues": [DEFAULT_MONEY_TRAIL_MIN_AMOUNT],
    }
    str_by_name = {
        d.StringParameterDeclaration.Name: d.StringParameterDeclaration
        for d in decls if d.StringParameterDeclaration
    }
    # No default — the dropdown auto-populates from the matview's
    # distinct root_transfer_id values.
    assert str_by_name[P_INV_MONEY_TRAIL_ROOT].DefaultValues == {
        "StaticValues": [],
    }
    # No default — analyst picks the anchor on first render.
    assert str_by_name[P_INV_ANETWORK_ANCHOR].DefaultValues == {
        "StaticValues": [],
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
    # Three KPIs followed by one Table (visual_ids are auto-generated
    # post-L.1.21; titles are the stable identifier for asserting order).
    titles = [
        (v.KPIVisual.Title.FormatText["PlainText"] if v.KPIVisual else
         v.TableVisual.Title.FormatText["PlainText"] if v.TableVisual else None)
        for v in fanout.Visuals
    ]
    assert titles == [
        "Qualifying Recipients",
        "Distinct Senders",
        "Total Inbound",
        "Recipient Fanout — Ranked",
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
    # Top-level: 11 filter groups (2 fanout + 2 anomalies + 3 money trail
    # + 4 account network: anchor/inbound/outbound/amount), 5 calc fields
    # (fanout distinct count + account-network is_anchor_edge +
    # is_inbound_edge + is_outbound_edge + counterparty_display), 7
    # parameters (fanout threshold + sigma + money-trail root/hops/amount
    # + account-network anchor/min-amount).
    assert len(j["Definition"]["FilterGroups"]) == 11
    assert len(j["Definition"]["CalculatedFields"]) == 5
    assert len(j["Definition"]["ParameterDeclarations"]) == 7


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
    analysis = build_analysis(_TEST_CFG)
    groups = {g.FilterGroupId: g for g in analysis.Definition.FilterGroups}
    sigma = groups[FG_INV_ANOMALIES_SIGMA]
    sheet_scopes = (
        sigma.ScopeConfiguration.SelectedSheets.SheetVisualScopingConfigurations
    )
    assert len(sheet_scopes) == 1
    scope = sheet_scopes[0]
    assert scope.SheetId == SHEET_INV_ANOMALIES
    assert scope.Scope == SheetVisualScopingConfiguration.SELECTED_VISUALS
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ANOMALIES
    )
    kpi_id = _visual_id_by_title(sheet, "Flagged Pair-Windows")
    table_id = _visual_id_by_title(sheet, "Flagged Pair-Windows — Ranked")
    dist_id = _visual_id_by_title(sheet, "Pair-Window σ Distribution")
    assert set(scope.VisualIds) == {kpi_id, table_id}
    assert dist_id not in scope.VisualIds


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
    # KPI flagged-count, σ distribution bar chart, ranked table — in
    # that order. Visual_ids are auto-derived (L.1.21); kind ordering
    # is the stable structural assertion.
    assert _visual_kinds(sheet) == ["KPIVisual", "BarChartVisual", "TableVisual"]


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
    # Field-ids are auto-derived (L.1.16). Look up the z_score field's
    # auto-id by walking the table's Values list and matching column name.
    z_score_field_id = next(
        v.NumericalMeasureField.FieldId
        for v in table.ChartConfiguration.FieldWells.TableAggregatedFieldWells.Values
        if v.NumericalMeasureField
        and v.NumericalMeasureField.Column.ColumnName == "z_score"
    )
    assert sort["FieldId"] == z_score_field_id
    assert sort["Direction"] == "DESC"


# ---------------------------------------------------------------------------
# K.4.5 — Money Trail dataset + matview wiring
# ---------------------------------------------------------------------------

def test_money_trail_contract_exposes_chain_columns():
    """Contract names every column the matview projects — root /
    transfer / depth + denormalized source + target account fields,
    hop_amount, posted_at, transfer_type."""
    names = MONEY_TRAIL_CONTRACT.column_names
    # Chain identity
    assert "root_transfer_id" in names
    assert "transfer_id" in names
    assert "depth" in names
    # Source leg
    assert "source_account_id" in names
    assert "source_account_name" in names
    assert "source_account_type" in names
    # Target leg
    assert "target_account_id" in names
    assert "target_account_name" in names
    assert "target_account_type" in names
    # Edge measures + hop metadata
    assert "hop_amount" in names
    assert "posted_at" in names
    assert "transfer_type" in names
    # K.4.8f walking-friendly display labels: name (id) — both human-
    # readable AND uniquely keyed.
    assert "source_display" in names
    assert "target_display" in names


def test_money_trail_dataset_reads_from_matview():
    """Dataset is a thin SELECT over the matview — recursive walk + leg
    join happens at refresh time, not dataset load. The whole point of
    the matview is to keep the WITH RECURSIVE out of QuickSight Direct
    Query."""
    datasets = build_all_datasets(_TEST_CFG)
    money_trail = datasets[2]
    sql = next(iter(money_trail.PhysicalTableMap.values())).CustomSql.SqlQuery
    assert "FROM inv_money_trail_edges" in sql
    # Don't reach back into transactions at dataset load.
    assert "transactions" not in sql
    assert "RECURSIVE" not in sql.upper()


# ---------------------------------------------------------------------------
# K.4.5 — Money Trail filter groups + parameters
# ---------------------------------------------------------------------------

def test_money_trail_root_filter_is_parameter_bound_category_filter():
    """The chain root filter is a CategoryFilter with EQUALS match
    operator bound to ``pInvMoneyTrailRoot`` — the dropdown writes a
    single root_transfer_id and the filter narrows to that one chain."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    root = groups[FG_INV_MONEY_TRAIL_ROOT]
    cat = root.Filters[0].CategoryFilter
    assert cat is not None
    assert cat.Column.ColumnName == "root_transfer_id"
    assert cat.Column.DataSetIdentifier == DS_INV_MONEY_TRAIL
    custom = cat.Configuration.CustomFilterConfiguration
    assert custom["MatchOperator"] == "EQUALS"
    assert custom["ParameterName"] == P_INV_MONEY_TRAIL_ROOT


def test_money_trail_hops_filter_caps_depth_via_parameter():
    """Max-hops filter is RangeMaximum bound to pInvMoneyTrailMaxHops on
    the depth column. Min-only would be the wrong shape — analysts care
    about ``depth ≤ N``, not a band of depths."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    hops = groups[FG_INV_MONEY_TRAIL_HOPS]
    nrf = hops.Filters[0].NumericRangeFilter
    assert nrf is not None
    assert nrf.Column.ColumnName == "depth"
    assert nrf.Column.DataSetIdentifier == DS_INV_MONEY_TRAIL
    assert nrf.RangeMaximum is not None
    assert nrf.RangeMaximum.Parameter == P_INV_MONEY_TRAIL_MAX_HOPS
    assert nrf.RangeMinimum is None
    assert nrf.IncludeMaximum is True


def test_money_trail_amount_filter_drops_noise_edges_via_parameter():
    """Min-hop-amount filter is RangeMinimum bound to
    pInvMoneyTrailMinAmount on hop_amount — drops edges below the
    slider so analysts can focus on meaningful flows."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    amt = groups[FG_INV_MONEY_TRAIL_AMOUNT]
    nrf = amt.Filters[0].NumericRangeFilter
    assert nrf is not None
    assert nrf.Column.ColumnName == "hop_amount"
    assert nrf.Column.DataSetIdentifier == DS_INV_MONEY_TRAIL
    assert nrf.RangeMinimum is not None
    assert nrf.RangeMinimum.Parameter == P_INV_MONEY_TRAIL_MIN_AMOUNT
    assert nrf.RangeMaximum is None
    assert nrf.IncludeMinimum is True


def test_money_trail_filters_are_all_visuals_scope():
    """Both Sankey and hop-by-hop table reflect the same chain
    selection — every money-trail filter group scopes ALL_VISUALS so
    the visual + table read together as one chain."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    for fg_id in (
        FG_INV_MONEY_TRAIL_ROOT,
        FG_INV_MONEY_TRAIL_HOPS,
        FG_INV_MONEY_TRAIL_AMOUNT,
    ):
        scope = (
            groups[fg_id]
            .ScopeConfiguration.SelectedSheets
            .SheetVisualScopingConfigurations
        )
        assert len(scope) == 1
        assert scope[0].SheetId == SHEET_INV_MONEY_TRAIL
        assert scope[0].Scope == SheetVisualScopingConfiguration.ALL_VISUALS


def test_money_trail_root_dropdown_links_to_dataset_column():
    """Dropdown auto-populates from the matview's distinct
    root_transfer_id values via LinkToDataSetColumn — analysts get a
    real list of chains, not an empty text input."""
    pc = build_money_trail_parameter_controls(_TEST_CFG)
    # 3 controls: root dropdown, hops slider, amount slider.
    assert len(pc) == 3
    dropdown = pc[0].Dropdown
    assert dropdown is not None
    assert dropdown.SourceParameterName == P_INV_MONEY_TRAIL_ROOT
    assert dropdown.Type == "SINGLE_SELECT"
    link = dropdown.SelectableValues["LinkToDataSetColumn"]
    assert link["DataSetIdentifier"] == DS_INV_MONEY_TRAIL
    assert link["ColumnName"] == "root_transfer_id"


def test_money_trail_sliders_bind_to_their_parameters():
    """Hops slider + amount slider both wired to their respective
    parameters with the documented bounds."""
    pc = build_money_trail_parameter_controls(_TEST_CFG)
    hops_slider = pc[1].Slider
    assert hops_slider is not None
    assert hops_slider.SourceParameterName == P_INV_MONEY_TRAIL_MAX_HOPS
    assert hops_slider.MinimumValue == HOPS_SLIDER_MIN
    assert hops_slider.MaximumValue == HOPS_SLIDER_MAX
    assert hops_slider.StepSize == 1

    amount_slider = pc[2].Slider
    assert amount_slider is not None
    assert amount_slider.SourceParameterName == P_INV_MONEY_TRAIL_MIN_AMOUNT
    assert amount_slider.MinimumValue == AMOUNT_SLIDER_MIN
    assert amount_slider.MaximumValue == AMOUNT_SLIDER_MAX
    # Step 10 because $-units rounded to dollars; 1-step would feel
    # uselessly granular over a $0–$1000 slider range.
    assert amount_slider.StepSize == 10


def test_money_trail_sheet_has_no_filter_controls():
    """All three money-trail surfaces are parameter-bound, so the sheet
    ships with ParameterControls only — no FilterControls widgets."""
    fc = build_money_trail_filter_controls(_TEST_CFG)
    assert fc == []


# ---------------------------------------------------------------------------
# K.4.5 — Money Trail sheet visuals + layout
# ---------------------------------------------------------------------------

def test_money_trail_sheet_has_sankey_and_table():
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_MONEY_TRAIL
    )
    assert sheet.Visuals is not None
    assert _visual_kinds(sheet) == ["SankeyDiagramVisual", "TableVisual"]


def test_money_trail_sankey_field_wells_use_account_names_and_sum_hop_amount():
    """Sankey ribbons go from source_account_name → target_account_name,
    weighted by SUM(hop_amount). Account names (not IDs) so Sankey labels
    read as banking entities, not opaque identifiers."""
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_MONEY_TRAIL
    )
    sankey = next(
        v.SankeyDiagramVisual for v in sheet.Visuals if v.SankeyDiagramVisual
    )
    fw = sankey.ChartConfiguration.FieldWells.SankeyDiagramAggregatedFieldWells
    src = [
        d.CategoricalDimensionField.Column.ColumnName
        for d in fw.Source if d.CategoricalDimensionField
    ]
    dst = [
        d.CategoricalDimensionField.Column.ColumnName
        for d in fw.Destination if d.CategoricalDimensionField
    ]
    assert src == ["source_account_name"]
    assert dst == ["target_account_name"]
    weight = fw.Weight[0].NumericalMeasureField
    assert weight.Column.ColumnName == "hop_amount"
    assert weight.AggregationFunction.SimpleNumericalAggregation == "SUM"


def test_money_trail_sankey_sort_weight_desc_with_node_cap():
    """WeightSort DESC so the heaviest ribbons render first; both
    items-limits set to the node cap with OtherCategories=INCLUDE so we
    don't silently drop edges past the cap (a real chain may have many
    siblings at the same depth)."""
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_MONEY_TRAIL
    )
    sankey = next(
        v.SankeyDiagramVisual for v in sheet.Visuals if v.SankeyDiagramVisual
    )
    sort = sankey.ChartConfiguration.SortConfiguration
    assert sort.WeightSort[0]["FieldSort"]["Direction"] == "DESC"
    assert sort.SourceItemsLimit["OtherCategories"] == "INCLUDE"
    assert sort.DestinationItemsLimit["OtherCategories"] == "INCLUDE"
    # Both caps match (50) — using the same constant so the diagram is
    # symmetric between source-side and destination-side density.
    assert (
        sort.SourceItemsLimit["ItemsLimit"]
        == sort.DestinationItemsLimit["ItemsLimit"]
    )


def test_money_trail_table_sorted_by_depth_asc_with_full_chain_grain():
    """Table aggregates to (depth, transfer_id, transfer_type, source,
    target, posted_at) so each row corresponds to one hop; sorted depth
    ASC so chains read top-to-bottom from root → leaf."""
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_MONEY_TRAIL
    )
    table = next(v.TableVisual for v in sheet.Visuals if v.TableVisual)
    fields = table.ChartConfiguration.FieldWells.TableAggregatedFieldWells
    group_by_cols = []
    for d in fields.GroupBy:
        if d.CategoricalDimensionField:
            group_by_cols.append(d.CategoricalDimensionField.Column.ColumnName)
        elif d.DateDimensionField:
            group_by_cols.append(d.DateDimensionField.Column.ColumnName)
        elif d.NumericalDimensionField:
            group_by_cols.append(d.NumericalDimensionField.Column.ColumnName)
    assert group_by_cols == [
        "depth",
        "transfer_id",
        "transfer_type",
        "source_account_name",
        "target_account_name",
        "posted_at",
    ]
    sort = table.ChartConfiguration.SortConfiguration["RowSort"][0]["FieldSort"]
    # Field-ids are auto-derived (L.1.16). Look up the depth field's
    # auto-id by walking the table's GroupBy and matching column name.
    depth_field_id = next(
        d.NumericalDimensionField.FieldId
        for d in table.ChartConfiguration.FieldWells.TableAggregatedFieldWells.GroupBy
        if d.NumericalDimensionField
        and d.NumericalDimensionField.Column.ColumnName == "depth"
    )
    assert sort["FieldId"] == depth_field_id
    assert sort["Direction"] == "ASC"


def test_money_trail_sheet_serializes_to_aws_json():
    """End-to-end serialization of the new Sankey dataclass surfaces
    cleanly through to_aws_json — no None-strip crashes, no missing
    keys."""
    j = build_analysis(_TEST_CFG).to_aws_json()
    sheet = next(
        s for s in j["Definition"]["Sheets"]
        if s["SheetId"] == SHEET_INV_MONEY_TRAIL
    )
    assert len(sheet["Visuals"]) == 2
    # 3 parameter controls (root dropdown + 2 sliders), no FilterControls.
    assert sheet.get("FilterControls", []) == []
    assert len(sheet["ParameterControls"]) == 3
    # Sankey visual surfaces with its dataclass key.
    # Sankey visual surfaces with its dataclass key. Visual_id is
    # auto-derived (L.1.21); just confirm the wrapper key exists.
    sankey = next(
        v for v in sheet["Visuals"] if "SankeyDiagramVisual" in v
    )
    assert sankey["SankeyDiagramVisual"]["VisualId"].startswith("v-sankey-")


# ---------------------------------------------------------------------------
# K.4.8 — Account Network sheet
# ---------------------------------------------------------------------------

def test_account_network_dataset_reuses_money_trail_matview():
    """K.4.8 wraps the same matview as K.4.5 — second dataset
    registration so account-centric filters live independently. SQL
    adds the source_display / target_display walking labels."""
    ds = build_all_datasets(_TEST_CFG)[3]
    sql = next(iter(ds.PhysicalTableMap.values())).CustomSql.SqlQuery
    assert "FROM inv_money_trail_edges" in sql
    assert "AS source_display" in sql
    assert "AS target_display" in sql


def test_anchor_calc_field_is_ifelse_on_anchor_param():
    """``is_anchor_edge`` returns 'yes' when source OR target equals
    pInvANetworkAnchor — single-column expression so the K.4.8 filter
    stays a single CategoryFilter rather than two."""
    analysis = build_analysis(_TEST_CFG)
    calc_fields = {
        cf["Name"]: cf for cf in analysis.Definition.CalculatedFields
    }
    is_anchor = calc_fields[CF_INV_ANETWORK_IS_ANCHOR_EDGE]
    assert is_anchor["DataSetIdentifier"] == DS_INV_ACCOUNT_NETWORK
    expr = is_anchor["Expression"]
    assert "ifelse" in expr
    # Walks compare display strings so a Sankey click delivers the
    # exact value the dropdown stores.
    assert "{source_display} = ${pInvANetworkAnchor}" in expr
    assert "{target_display} = ${pInvANetworkAnchor}" in expr
    assert "OR" in expr
    assert "'yes'" in expr
    assert "'no'" in expr


def test_anchor_filter_matches_calc_field_on_yes():
    """Anchor filter is a CategoryFilter on the calc field equal to
    'yes' — narrows visuals to edges touching the anchor account."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    anchor = groups[FG_INV_ANETWORK_ANCHOR]
    cf = anchor.Filters[0].CategoryFilter
    assert cf is not None
    assert cf.Column.DataSetIdentifier == DS_INV_ACCOUNT_NETWORK
    assert cf.Column.ColumnName == CF_INV_ANETWORK_IS_ANCHOR_EDGE
    config = cf.Configuration.FilterListConfiguration
    assert config["MatchOperator"] == "CONTAINS"
    assert config["CategoryValues"] == ["yes"]


def test_anetwork_amount_filter_drops_noise_edges_via_parameter():
    """Min-amount filter on hop_amount bound to pInvANetworkMinAmount;
    same NumericRangeFilter shape as the money-trail amount slider."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    amount = groups[FG_INV_ANETWORK_AMOUNT]
    nrf = amount.Filters[0].NumericRangeFilter
    assert nrf is not None
    assert nrf.Column.ColumnName == "hop_amount"
    assert nrf.Column.DataSetIdentifier == DS_INV_ACCOUNT_NETWORK
    assert nrf.RangeMinimum is not None
    assert nrf.RangeMinimum.Parameter == P_INV_ANETWORK_MIN_AMOUNT
    assert nrf.RangeMaximum is None
    assert nrf.IncludeMinimum is True


def test_anetwork_amount_filter_is_all_visuals_scope():
    """The amount filter applies to all three visuals on the sheet
    (both Sankeys + table)."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    sc = groups[FG_INV_ANETWORK_AMOUNT].ScopeConfiguration
    configs = sc.SelectedSheets.SheetVisualScopingConfigurations
    assert len(configs) == 1
    assert configs[0].SheetId == SHEET_INV_ACCOUNT_NETWORK
    assert configs[0].Scope == SheetVisualScopingConfiguration.ALL_VISUALS


def test_anetwork_anchor_filter_is_table_only():
    """K.4.8i: anchor filter (is_anchor_edge='yes') is scoped to the
    touching-edges table only. The two Sankeys each carry their own
    direction-specific filter (is_inbound_edge / is_outbound_edge) so
    the layout itself encodes direction.

    Walks the tree-emitted analysis (post-L.1.21) instead of the
    imperative ``build_filter_groups`` — the latter has stale visual_id
    constants that don't match the auto-derived IDs the tree emits."""
    analysis = build_analysis(_TEST_CFG)
    groups = {g.FilterGroupId: g for g in analysis.Definition.FilterGroups}
    sc = groups[FG_INV_ANETWORK_ANCHOR].ScopeConfiguration
    configs = sc.SelectedSheets.SheetVisualScopingConfigurations
    assert len(configs) == 1
    assert configs[0].SheetId == SHEET_INV_ACCOUNT_NETWORK
    assert configs[0].Scope == SheetVisualScopingConfiguration.SELECTED_VISUALS
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ACCOUNT_NETWORK
    )
    assert configs[0].VisualIds == [
        _visual_id_by_title(sheet, "Account Network — Touching Edges"),
    ]


def test_anetwork_inbound_filter_is_inbound_sankey_only():
    """K.4.8i: inbound filter scoped to the inbound Sankey only."""
    analysis = build_analysis(_TEST_CFG)
    groups = {g.FilterGroupId: g for g in analysis.Definition.FilterGroups}
    sc = groups[FG_INV_ANETWORK_INBOUND].ScopeConfiguration
    configs = sc.SelectedSheets.SheetVisualScopingConfigurations
    assert len(configs) == 1
    assert configs[0].SheetId == SHEET_INV_ACCOUNT_NETWORK
    assert configs[0].Scope == SheetVisualScopingConfiguration.SELECTED_VISUALS
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ACCOUNT_NETWORK
    )
    assert configs[0].VisualIds == [
        _visual_id_by_title(sheet, "Inbound — counterparties → anchor"),
    ]


def test_anetwork_outbound_filter_is_outbound_sankey_only():
    """K.4.8i: outbound filter scoped to the outbound Sankey only."""
    analysis = build_analysis(_TEST_CFG)
    groups = {g.FilterGroupId: g for g in analysis.Definition.FilterGroups}
    sc = groups[FG_INV_ANETWORK_OUTBOUND].ScopeConfiguration
    configs = sc.SelectedSheets.SheetVisualScopingConfigurations
    assert len(configs) == 1
    assert configs[0].SheetId == SHEET_INV_ACCOUNT_NETWORK
    assert configs[0].Scope == SheetVisualScopingConfiguration.SELECTED_VISUALS
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ACCOUNT_NETWORK
    )
    assert configs[0].VisualIds == [
        _visual_id_by_title(sheet, "Outbound — anchor → counterparties"),
    ]


def test_anetwork_directional_filters_are_category_filters_on_calc_fields():
    """K.4.8i: each directional Sankey's filter is a CategoryFilter
    matching the calc field to 'yes' — the standard pattern for using
    a calc field as a boolean filter."""
    groups = {g.FilterGroupId: g for g in build_filter_groups(_TEST_CFG)}
    for fg_id, expected_col in (
        (FG_INV_ANETWORK_INBOUND, CF_INV_ANETWORK_IS_INBOUND_EDGE),
        (FG_INV_ANETWORK_OUTBOUND, CF_INV_ANETWORK_IS_OUTBOUND_EDGE),
    ):
        cf = groups[fg_id].Filters[0].CategoryFilter
        assert cf is not None
        assert cf.Column.ColumnName == expected_col
        assert cf.Column.DataSetIdentifier == DS_INV_ACCOUNT_NETWORK
        flc = cf.Configuration.FilterListConfiguration
        assert flc["MatchOperator"] == "CONTAINS"
        assert flc["CategoryValues"] == ["yes"]


def test_anetwork_anchor_dropdown_links_to_narrow_accounts_dataset():
    """K.4.8k — dropdown auto-populates from the narrow accounts
    dataset's distinct ``source_display`` values, NOT the main Account
    Network dataset. The narrow dataset pushes DISTINCT inside its
    SELECT so PG dedupes (id, name) pairs before computing the concat;
    pointing the dropdown at the main wrapper forces O(matview rows)
    work and times out as the matview grows. SelectAll stays HIDDEN
    so QuickSight lands on the first row instead of an empty/All
    state that would render two blank Sankeys."""
    pc = build_account_network_parameter_controls(_TEST_CFG)
    # 2 controls: anchor dropdown, min-amount slider.
    assert len(pc) == 2
    dropdown = pc[0].Dropdown
    assert dropdown is not None
    assert dropdown.SourceParameterName == P_INV_ANETWORK_ANCHOR
    assert dropdown.Type == "SINGLE_SELECT"
    link = dropdown.SelectableValues["LinkToDataSetColumn"]
    assert link["DataSetIdentifier"] == DS_INV_ANETWORK_ACCOUNTS
    assert link["ColumnName"] == "source_display"
    assert dropdown.DisplayOptions == {
        "SelectAllOptions": {"Visibility": "HIDDEN"},
    }


def test_anetwork_amount_slider_binds_to_parameter():
    pc = build_account_network_parameter_controls(_TEST_CFG)
    amount_slider = pc[1].Slider
    assert amount_slider is not None
    assert amount_slider.SourceParameterName == P_INV_ANETWORK_MIN_AMOUNT
    assert amount_slider.MinimumValue == AMOUNT_SLIDER_MIN
    assert amount_slider.MaximumValue == AMOUNT_SLIDER_MAX
    assert amount_slider.StepSize == 10


def test_account_network_sheet_has_no_filter_controls():
    """All filters parameter-bound; ParameterControls only."""
    fc = build_account_network_filter_controls(_TEST_CFG)
    assert fc == []


def test_account_network_sheet_has_two_sankeys_and_table():
    """K.4.8i: layout is inbound Sankey | outbound Sankey side-by-side
    on top, full-width touching-edges table below. The anchor visually
    meets in the middle of the row."""
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ACCOUNT_NETWORK
    )
    assert sheet.Visuals is not None
    assert _visual_kinds(sheet) == [
        "SankeyDiagramVisual", "SankeyDiagramVisual", "TableVisual",
    ]


def test_account_network_sankeys_field_wells_use_account_names_and_sum_hop_amount():
    """K.4.8i: both directional Sankeys carry the same field-well shape
    (source_display → target_display, weight = SUM(hop_amount)),
    sourced from the K.4.8 dataset wrapper. Direction encoding lives
    in the per-Sankey filter, not the field wells."""
    inbound, outbound, _ = _account_network_visuals()
    for sankey in (inbound, outbound):
        fw = sankey.ChartConfiguration.FieldWells.SankeyDiagramAggregatedFieldWells
        src = [
            d.CategoricalDimensionField.Column.ColumnName
            for d in fw.Source if d.CategoricalDimensionField
        ]
        dst = [
            d.CategoricalDimensionField.Column.ColumnName
            for d in fw.Destination if d.CategoricalDimensionField
        ]
        # K.4.8f switched the field wells from raw _name to _display so a
        # Sankey click delivers the exact value the dropdown stores.
        assert src == ["source_display"]
        assert dst == ["target_display"]
        weight = fw.Weight[0].NumericalMeasureField
        assert weight.Column.ColumnName == "hop_amount"
        assert weight.AggregationFunction.SimpleNumericalAggregation == "SUM"
        # Confirm sankey is sourced from the K.4.8 dataset, not K.4.5.
        assert fw.Source[0].CategoricalDimensionField.Column.DataSetIdentifier == (
            DS_INV_ACCOUNT_NETWORK
        )


def test_account_network_sheet_serializes_to_aws_json():
    j = build_analysis(_TEST_CFG).to_aws_json()
    sheet = next(
        s for s in j["Definition"]["Sheets"]
        if s["SheetId"] == SHEET_INV_ACCOUNT_NETWORK
    )
    # K.4.8i: 3 visuals — inbound Sankey | outbound Sankey | table.
    assert len(sheet["Visuals"]) == 3
    assert sheet.get("FilterControls", []) == []
    # 2 parameter controls (anchor dropdown + amount slider).
    assert len(sheet["ParameterControls"]) == 2


def _account_network_visuals():
    """Helper: returns (inbound_sankey, outbound_sankey, table) from
    the deployed Account Network sheet — mirrors the K.4.8i layout.
    Visual_ids are auto-derived (L.1.21); look up by title."""
    analysis = build_analysis(_TEST_CFG)
    sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_INV_ACCOUNT_NETWORK
    )
    sankeys_by_title = {}
    for v in sheet.Visuals:
        if v.SankeyDiagramVisual:
            title = v.SankeyDiagramVisual.Title.FormatText["PlainText"]
            sankeys_by_title[title] = v.SankeyDiagramVisual
    inbound = sankeys_by_title["Inbound — counterparties → anchor"]
    outbound = sankeys_by_title["Outbound — anchor → counterparties"]
    table = next(
        v.TableVisual for v in sheet.Visuals if v.TableVisual
    )
    return inbound, outbound, table


def _sankey_field_id_for_column(sankey, role: str, column_name: str) -> str:
    """Look up the auto-derived field_id of a Sankey leaf by role +
    column. Field-ids are auto-derived (L.1.16) so tests resolve them
    via column-name lookup rather than hardcoded strings."""
    field_wells = sankey.ChartConfiguration.FieldWells.SankeyDiagramAggregatedFieldWells
    slot_attr = {"source": "Source", "target": "Destination"}[role]
    leaves = getattr(field_wells, slot_attr) or []
    for leaf in leaves:
        if leaf.CategoricalDimensionField:
            if leaf.CategoricalDimensionField.Column.ColumnName == column_name:
                return leaf.CategoricalDimensionField.FieldId
    raise AssertionError(
        f"No Sankey {role} field with column {column_name!r}"
    )


def _table_groupby_field_id_for_column(table, column_name: str) -> str:
    """Look up the auto-derived field_id of a Table GroupBy leaf by
    column name."""
    field_wells = table.ChartConfiguration.FieldWells.TableAggregatedFieldWells
    for leaf in field_wells.GroupBy or []:
        for sub in (
            leaf.CategoricalDimensionField,
            leaf.DateDimensionField,
            leaf.NumericalDimensionField,
        ):
            if sub and sub.Column.ColumnName == column_name:
                return sub.FieldId
    raise AssertionError(
        f"No Table GroupBy field with column {column_name!r}"
    )


def test_anetwork_inbound_sankey_left_click_walks_to_source_counterparty():
    """K.4.8i: inbound Sankey wires a single DATA_POINT_CLICK (left-
    click) action that reads the SOURCE field — the counterparty
    side when the target is the anchor — and writes it into the
    anchor parameter."""
    inbound, _, _ = _account_network_visuals()
    actions = inbound.Actions
    assert actions is not None
    assert len(actions) == 1
    walk = actions[0]
    assert walk.Name == "Walk to this counterparty"
    assert walk.Trigger == "DATA_POINT_CLICK"
    nav = walk.ActionOperations[0].NavigationOperation
    assert nav is not None
    assert nav.LocalNavigationConfiguration.TargetSheetId == (
        SHEET_INV_ACCOUNT_NETWORK
    )
    set_params = walk.ActionOperations[1].SetParametersOperation
    cfg = set_params.ParameterValueConfigurations
    assert len(cfg) == 1
    assert cfg[0]["DestinationParameterName"] == P_INV_ANETWORK_ANCHOR
    assert cfg[0]["Value"]["SourceField"] == _sankey_field_id_for_column(
        inbound, "source", "source_display",
    )


def test_anetwork_outbound_sankey_left_click_walks_to_target_counterparty():
    """K.4.8i: outbound Sankey wires a single DATA_POINT_CLICK (left-
    click) action that reads the TARGET field — the counterparty
    side when the source is the anchor — and writes it into the
    anchor parameter."""
    _, outbound, _ = _account_network_visuals()
    actions = outbound.Actions
    assert actions is not None
    assert len(actions) == 1
    walk = actions[0]
    assert walk.Name == "Walk to this counterparty"
    assert walk.Trigger == "DATA_POINT_CLICK"
    nav = walk.ActionOperations[0].NavigationOperation
    assert nav is not None
    assert nav.LocalNavigationConfiguration.TargetSheetId == (
        SHEET_INV_ACCOUNT_NETWORK
    )
    set_params = walk.ActionOperations[1].SetParametersOperation
    cfg = set_params.ParameterValueConfigurations
    assert len(cfg) == 1
    assert cfg[0]["DestinationParameterName"] == P_INV_ANETWORK_ANCHOR
    assert cfg[0]["Value"]["SourceField"] == _sankey_field_id_for_column(
        outbound, "target", "target_display",
    )


def test_anetwork_table_wires_single_counterparty_walk_action():
    """K.4.8f-3: Table carries a single, unambiguous "Walk to other
    account on this edge" action that SourceFields off the analysis-
    level counterparty_display calc field — that field always projects
    the side that ISN'T the current anchor, so the walk can never be a
    no-op."""
    _, _, table = _account_network_visuals()
    actions = table.Actions
    assert actions is not None
    assert len(actions) == 1
    walk = actions[0]
    assert walk.Name == "Walk to other account on this edge"
    assert walk.Trigger == "DATA_POINT_MENU"
    set_params = walk.ActionOperations[1].SetParametersOperation
    cfg = set_params.ParameterValueConfigurations
    assert len(cfg) == 1
    assert cfg[0]["DestinationParameterName"] == P_INV_ANETWORK_ANCHOR
    assert cfg[0]["Value"]["SourceField"] == _table_groupby_field_id_for_column(
        table, CF_INV_ANETWORK_COUNTERPARTY_DISPLAY,
    )


def test_anetwork_table_columns_use_display_strings():
    """Table source / target columns are the display strings AND the
    counterparty_display calc field is exposed as a column so the
    single-action walk has a SourceField to read off."""
    _, _, table = _account_network_visuals()
    fields = table.ChartConfiguration.FieldWells.TableAggregatedFieldWells
    cols = []
    for d in fields.GroupBy:
        if d.CategoricalDimensionField:
            cols.append(d.CategoricalDimensionField.Column.ColumnName)
    assert "source_display" in cols
    assert "target_display" in cols
    assert CF_INV_ANETWORK_COUNTERPARTY_DISPLAY in cols
    # And the raw _name columns are gone — display replaces them.
    assert "source_account_name" not in cols
    assert "target_account_name" not in cols


def test_counterparty_calc_field_picks_other_side_of_edge():
    """K.4.8f-3: counterparty_display returns target_display when the
    source IS the anchor, otherwise source_display. The single-action
    table walk reads from this field so it always picks the side that
    isn't the current anchor."""
    analysis = build_analysis(_TEST_CFG)
    calc_fields = {
        cf["Name"]: cf for cf in analysis.Definition.CalculatedFields
    }
    counterparty = calc_fields[CF_INV_ANETWORK_COUNTERPARTY_DISPLAY]
    assert counterparty["DataSetIdentifier"] == DS_INV_ACCOUNT_NETWORK
    expr = counterparty["Expression"]
    assert "ifelse" in expr
    assert "{source_display} = ${pInvANetworkAnchor}" in expr
    # If the source is the anchor, project the target; else the source.
    assert "{target_display}" in expr
    assert "{source_display}" in expr


def test_inbound_edge_calc_field_matches_target_to_anchor():
    """K.4.8i: is_inbound_edge = 'yes' when the edge's TARGET equals the
    anchor (the anchor received the money). The inbound Sankey's filter
    matches this calc field to 'yes'."""
    analysis = build_analysis(_TEST_CFG)
    calc_fields = {
        cf["Name"]: cf for cf in analysis.Definition.CalculatedFields
    }
    inbound = calc_fields[CF_INV_ANETWORK_IS_INBOUND_EDGE]
    assert inbound["DataSetIdentifier"] == DS_INV_ACCOUNT_NETWORK
    expr = inbound["Expression"]
    assert "ifelse" in expr
    assert "{target_display} = ${pInvANetworkAnchor}" in expr
    assert "'yes'" in expr
    assert "'no'" in expr


def test_outbound_edge_calc_field_matches_source_to_anchor():
    """K.4.8i: is_outbound_edge = 'yes' when the edge's SOURCE equals
    the anchor (the anchor sent the money). The outbound Sankey's
    filter matches this calc field to 'yes'."""
    analysis = build_analysis(_TEST_CFG)
    calc_fields = {
        cf["Name"]: cf for cf in analysis.Definition.CalculatedFields
    }
    outbound = calc_fields[CF_INV_ANETWORK_IS_OUTBOUND_EDGE]
    assert outbound["DataSetIdentifier"] == DS_INV_ACCOUNT_NETWORK
    expr = outbound["Expression"]
    assert "ifelse" in expr
    assert "{source_display} = ${pInvANetworkAnchor}" in expr
    assert "'yes'" in expr
    assert "'no'" in expr


def test_money_trail_root_dropdown_hides_select_all():
    """K.4.8f: Money Trail chain-root dropdown also hides SelectAll —
    a Sankey with no chain root selected renders blank, so 'All' is
    misleading. SelectAll HIDDEN forces QS to land on the first row."""
    pc = build_money_trail_parameter_controls(_TEST_CFG)
    dropdown = pc[0].Dropdown
    assert dropdown is not None
    assert dropdown.SourceParameterName == P_INV_MONEY_TRAIL_ROOT
    assert dropdown.DisplayOptions == {
        "SelectAllOptions": {"Visibility": "HIDDEN"},
    }


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
