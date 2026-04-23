"""L.1.10.6 — Kitchen-sink app that uses every typed L.1 primitive.

Persona-agnostic minimal App for testing the tree itself (vs. testing
PR / AR / Investigation scenarios). Sheets are deliberately generic:

- Sheet 1 (Visuals Showcase): one of each typed Visual subtype
  (KPI / Table / BarChart / Sankey).
- Sheet 2 (Filters & Controls): every typed Filter wrapper +
  Parameter / Filter control variant. CategoryFilter binds to a
  CalcField; NumericRangeFilter is parameter-bound.
- Sheet 3 (Drill Target): single Table that's the destination of
  drill actions wired from Sheet 1's BarChart and Table.

Every typed primitive appears at least once. New typed primitives
we add later should add a usage here so the kitchen-sink stays
"complete coverage" by definition.

Used by:
- ``tests/test_kitchen_app.py`` — unit tests that build + emit the
  app and verify the resulting JSON contains every primitive.
- ``tests/e2e/test_tree_primitives.py`` (future, post-L.2) — e2e
  test that deploys + browser-validates via ``TreeValidator``. Needs
  the L.2 tree-to-files bridging plumbing to deploy through the
  existing CLI; until then the app is unit-test-only.
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import ColumnShape
from quicksight_gen.common.ids import (
    FilterGroupId,
    ParameterName,
    SheetId,
    VisualId,
)
from quicksight_gen.common.tree import (
    Analysis,
    App,
    BarChart,
    CalcField,
    CategoryFilter,
    Dashboard,
    Dataset,
    DateTimeParam,
    Dim,
    Drill,
    DrillParam,
    DrillSourceField,
    FilterCrossSheet,
    FilterDateTimePicker,
    FilterDropdown,
    FilterGroup,
    FilterSlider,
    IntegerParam,
    KPI,
    LinkedValues,
    Measure,
    NumericRangeFilter,
    ParameterDateTimePicker,
    ParameterDropdown,
    ParameterSlider,
    Sankey,
    Sheet,
    StaticValues,
    StringParam,
    Table,
    TimeRangeFilter,
)


def build_kitchen_app(cfg: Config) -> App:
    """Construct the kitchen-sink App.

    Returns the App ready for ``app.emit_analysis()`` /
    ``app.emit_dashboard()``. Caller may register additional datasets
    or modify before emitting; the default returned shape is
    self-contained and exercises every primitive at least once.
    """
    # Kitchen sink doesn't register a DatasetContract for its datasets,
    # so ds["col"] can't validate. Opt into the bare-string escape
    # hatch so the existing Dim(ds, "col") form survives.
    app = App(name="tree-kitchen", cfg=cfg, allow_bare_strings=True)

    # ------ Datasets -------------------------------------------------
    # Two datasets — one for visual data, one for the dropdown
    # LinkedValues column. Real apps deploy these as actual QuickSight
    # DataSets; the unit tests just confirm they appear in
    # DataSetIdentifierDeclarations.
    ds_main = app.add_dataset(Dataset(
        identifier="kitchen-main-ds",
        arn="arn:aws:quicksight:::dataset/kitchen-main",
    ))
    ds_categories = app.add_dataset(Dataset(
        identifier="kitchen-categories-ds",
        arn="arn:aws:quicksight:::dataset/kitchen-categories",
    ))

    # ------ Analysis -------------------------------------------------
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="tree-kitchen-analysis",
        name="Tree Kitchen Sink",
    ))

    # ------ Parameters (all three variants) --------------------------
    p_category = analysis.add_parameter(StringParam(
        name=ParameterName("pKitchenCategory"),
    ))
    p_threshold = analysis.add_parameter(IntegerParam(
        name=ParameterName("pKitchenThreshold"),
        default=[10],
    ))
    p_date = analysis.add_parameter(DateTimeParam(
        name=ParameterName("pKitchenDate"),
    ))

    # ------ Calc field -----------------------------------------------
    is_above_threshold = analysis.add_calc_field(CalcField(
        name="is_above_threshold",
        dataset=ds_main,
        expression=(
            "ifelse({amount} > ${pKitchenThreshold}, 'yes', 'no')"
        ),
    ))

    # ================================================================
    # Sheet 1 — Visuals Showcase (one of each typed Visual kind)
    # ================================================================
    showcase = analysis.add_sheet(Sheet(
        sheet_id=SheetId("kitchen-sheet-showcase"),
        name="Visuals Showcase",
        title="Visuals Showcase",
        description="One of every typed Visual subtype.",
    ))

    kpi = showcase.add_visual(KPI(
        title="Total Amount",
        subtitle="SUM of amount",
        values=[Measure.sum(ds_main, "amount")],
    ))

    # Tree-level vars for the leaves so drills + sort_by reference
    # them by object ref (no string field_ids needed for routing).
    # Drill-source leaves keep an explicit field_id only because the
    # kitchen sink isn't registered with a dataset contract — the
    # drill resolver can't auto-derive ColumnShape, so the kitchen-sink
    # uses the explicit DrillSourceField escape-hatch path.
    tbl_name_dim = Dim(ds_main, "name", field_id="kitchen-tbl-name")
    tbl_amount_measure = Measure.sum(ds_main, "amount")
    table = showcase.add_visual(Table(
        title="Detail Table",
        subtitle="GroupBy + Values",
        group_by=[
            Dim(ds_main, "id"),
            tbl_name_dim,
            # Calc-field reference (ColumnRef union)
            Dim(ds_main, is_above_threshold),
        ],
        values=[tbl_amount_measure],
        sort_by=(tbl_amount_measure, "DESC"),
    ))

    bar_cat_dim = Dim(ds_main, "category", field_id="kitchen-bar-cat")
    bar = showcase.add_visual(BarChart(
        title="By Category",
        subtitle="Counts per category",
        category=[bar_cat_dim],
        values=[Measure.count(ds_main, "id")],
    ))

    sankey_source_dim = Dim(
        ds_main, "source_account", field_id="kitchen-sk-source",
    )
    sankey = showcase.add_visual(Sankey(
        title="Flow",
        subtitle="Source → Target by amount",
        source=sankey_source_dim,
        target=Dim(ds_main, "target_account"),
        weight=Measure.sum(ds_main, "amount"),
        items_limit=25,
    ))

    showcase.place(kpi, col_span=8, row_span=6, col_index=0)
    showcase.place(table, col_span=28, row_span=6, col_index=8)
    showcase.place(bar, col_span=18, row_span=12, col_index=0)
    showcase.place(sankey, col_span=18, row_span=12, col_index=18)

    # ================================================================
    # Sheet 2 — Filters & Controls (every Filter wrapper + control
    # variant)
    # ================================================================
    filters_sheet = analysis.add_sheet(Sheet(
        sheet_id=SheetId("kitchen-sheet-filters"),
        name="Filters and Controls",
        title="Filters and Controls",
        description="Every typed Filter + Control variant.",
    ))

    # A target visual for the filter group scope.
    filtered_table = filters_sheet.add_visual(Table(
        title="Filtered Detail",
        group_by=[Dim(ds_main, "id")],
        values=[Measure.sum(ds_main, "amount")],
    ))

    filters_sheet.place(filtered_table, col_span=36, row_span=18, col_index=0)

    # Filter wrappers — one of each kind.
    cat_filter = CategoryFilter(
        dataset=ds_main, column="category",
        values=["a", "b", "c"], match_operator="CONTAINS",
    )
    num_filter = NumericRangeFilter(
        dataset=ds_main, column="amount",
        minimum_parameter=p_threshold,  # parameter-bound
    )
    time_filter = TimeRangeFilter(
        dataset=ds_main, column="posted_at",
    )
    # Calc-field-backed CategoryFilter — same pattern as
    # is_anchor_edge in Investigation.
    calc_filter = CategoryFilter(
        dataset=ds_main, column=is_above_threshold,  # CalcField ref
        values=["yes"],
    )

    analysis.add_filter_group(FilterGroup(
        filters=[cat_filter, num_filter, time_filter, calc_filter],
    )).scope_visuals(filters_sheet, [filtered_table])

    # Parameter controls — one of each kind.
    filters_sheet.add_parameter_control(ParameterDropdown(
        parameter=p_category,
        title="Category (Static)",
        type="MULTI_SELECT",
        selectable_values=StaticValues(values=["a", "b", "c"]),
    ))
    filters_sheet.add_parameter_control(ParameterDropdown(
        parameter=p_category,
        title="Category (Linked)",
        type="SINGLE_SELECT",
        selectable_values=LinkedValues(
            dataset=ds_categories, column="category",
        ),
        hidden_select_all=True,
    ))
    filters_sheet.add_parameter_control(ParameterSlider(
        parameter=p_threshold,
        title="Threshold",
        minimum_value=0, maximum_value=1000, step_size=10,
    ))
    filters_sheet.add_parameter_control(ParameterDateTimePicker(
        parameter=p_date,
        title="Date",
    ))

    # Filter controls — one of each kind.
    filters_sheet.add_filter_control(FilterDropdown(
        filter=cat_filter,
        title="Category Filter",
        type="MULTI_SELECT",
    ))
    filters_sheet.add_filter_control(FilterSlider(
        filter=num_filter,
        title="Amount Range",
        minimum_value=0, maximum_value=1000, step_size=10,
        type="RANGE",
    ))
    filters_sheet.add_filter_control(FilterDateTimePicker(
        filter=time_filter,
        title="Date Range",
        type="DATE_RANGE",
    ))
    filters_sheet.add_filter_control(FilterCrossSheet(filter=cat_filter))

    # ================================================================
    # Sheet 3 — Drill Target (drill destination from Sheet 1 visuals)
    # ================================================================
    drill_target = analysis.add_sheet(Sheet(
        sheet_id=SheetId("kitchen-sheet-drill-target"),
        name="Drill Target",
        title="Drill Target",
        description="Destination for drill actions from Visuals Showcase.",
    ))

    drill_dest_table = drill_target.add_visual(Table(
        title="Drill Destination",
        group_by=[Dim(ds_main, "id")],
        values=[Measure.sum(ds_main, "amount")],
    ))
    drill_target.place(drill_dest_table, col_span=36, row_span=18, col_index=0)

    # ------ Drill actions -------------------------------------------
    # Wire drill actions from Sheet 1 visuals to Sheet 3.
    # BarChart, Table, Sankey support Actions; KPI doesn't (per the
    # QuickSight model).
    drill_param = DrillParam(
        ParameterName("pKitchenCategory"), ColumnShape.ACCOUNT_DISPLAY,
    )

    bar.actions.append(Drill(
        target_sheet=drill_target,
        writes=[(drill_param, DrillSourceField(
            field_id="kitchen-bar-cat", shape=ColumnShape.ACCOUNT_DISPLAY,
        ))],
        name="Drill into category",
        trigger="DATA_POINT_MENU",
    ))

    table.actions.append(Drill(
        target_sheet=drill_target,
        writes=[(drill_param, DrillSourceField(
            field_id="kitchen-tbl-name", shape=ColumnShape.ACCOUNT_DISPLAY,
        ))],
        name="Drill into name",
        trigger="DATA_POINT_CLICK",
    ))

    sankey.actions.append(Drill(
        target_sheet=drill_target,
        writes=[(drill_param, DrillSourceField(
            field_id="kitchen-sk-source", shape=ColumnShape.ACCOUNT_DISPLAY,
        ))],
        name="Drill from source",
        trigger="DATA_POINT_CLICK",
    ))

    # ------ Dashboard -----------------------------------------------
    app.set_dashboard(Dashboard(
        dashboard_id_suffix="tree-kitchen-dashboard",
        name="Tree Kitchen Sink",
        analysis=analysis,
    ))

    return app
