"""Unit tests for the L.1 tree primitives in ``common/tree.py``.

L.1.2 coverage: structural types (App / Dashboard / Analysis / Sheet),
GridSlot placement validation, emit() round-trip into models.py.

L.1.3+ coverage joins as each sub-step lands.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import (
    FilterGroupId,
    ParameterName,
    SheetId,
    VisualId,
)
from quicksight_gen.common.models import (
    DateTimeDefaultValues,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    SheetVisualScopingConfiguration,
    Visual,
)
from quicksight_gen.common.tree import (
    KPI,
    Analysis,
    App,
    BarChart,
    CategoryFilter,
    Dashboard,
    DateTimeParam,
    Dim,
    FilterGroup,
    FilterLike,
    GridSlot,
    IntegerParam,
    Measure,
    NumericRangeFilter,
    ParameterControlNode,
    Sankey,
    Sheet,
    StringParam,
    Table,
    TimeRangeFilter,
    VisualLike,
    VisualNode,
)


_TEST_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


def _kpi_factory(visual_id: str, title: str) -> Visual:
    """Minimal KPI visual factory for placeholder tests. The L.1.3
    typed KPI subtype will replace VisualNode + factory pattern."""
    return Visual(
        KPIVisual=KPIVisual(
            VisualId=visual_id,
            ChartConfiguration=KPIConfiguration(
                FieldWells=KPIFieldWells(),
            ),
        ),
    )


def _make_kpi(visual_id: str = "v-test-kpi") -> VisualNode:
    return VisualNode(
        visual_id=VisualId(visual_id),
        builder=lambda: _kpi_factory(visual_id, "Test KPI"),
    )


# ---------------------------------------------------------------------------
# Sheet
# ---------------------------------------------------------------------------

class TestSheet:
    def test_emits_minimal_sheet_definition(self):
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test",
            title="Test Sheet",
            description="Test sheet for unit tests.",
        )
        emitted = sheet.emit()
        assert emitted.SheetId == "sheet-test"
        assert emitted.Name == "Test"
        assert emitted.Title == "Test Sheet"
        assert emitted.Description == "Test sheet for unit tests."
        assert emitted.ContentType == "INTERACTIVE"
        assert emitted.Visuals is None
        assert emitted.ParameterControls is None
        assert emitted.FilterControls == []  # explicit empty for L.1.6 forward-compat

    def test_add_visual_returns_node_for_chaining(self):
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        )
        node = _make_kpi()
        ret = sheet.add_visual(node)
        assert ret is node
        assert sheet.visuals == [node]

    def test_emit_includes_visuals(self):
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        )
        sheet.add_visual(_make_kpi("v-a"))
        sheet.add_visual(_make_kpi("v-b"))
        emitted = sheet.emit()
        assert emitted.Visuals is not None
        assert [v.KPIVisual.VisualId for v in emitted.Visuals] == ["v-a", "v-b"]

    def test_place_requires_visual_to_be_registered(self):
        """Construction-time check: place() rejects an unregistered visual.
        Catches the wrong-sheet bug class at the call site."""
        sheet_a = Sheet(
            sheet_id=SheetId("sheet-a"),
            name="A", title="A", description="",
        )
        sheet_b = Sheet(
            sheet_id=SheetId("sheet-b"),
            name="B", title="B", description="",
        )
        node = _make_kpi("v-on-a")
        sheet_a.add_visual(node)
        with pytest.raises(ValueError, match="isn't registered on this sheet"):
            sheet_b.place(node, col_span=12, row_span=6, col_index=0)

    def test_place_returns_grid_slot(self):
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        )
        node = sheet.add_visual(_make_kpi("v-placed"))
        slot = sheet.place(node, col_span=12, row_span=6, col_index=0)
        assert isinstance(slot, GridSlot)
        assert slot.visual is node
        assert slot.col_span == 12
        assert slot.row_span == 6
        assert slot.col_index == 0

    def test_emit_layout_references_visual_id_at_emit_time(self):
        """GridSlot stores an object ref; ElementId resolves to the
        referenced visual's id at emit time. Locked decision: object
        refs over string IDs."""
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        )
        node = sheet.add_visual(_make_kpi("v-the-one"))
        sheet.place(node, col_span=36, row_span=18, col_index=0)
        emitted = sheet.emit()
        layout = emitted.Layouts[0]
        elements = layout.Configuration.GridLayout.Elements
        assert len(elements) == 1
        assert elements[0].ElementId == "v-the-one"
        assert elements[0].ElementType == "VISUAL"
        assert elements[0].ColumnSpan == 36


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

class TestAnalysis:
    def test_add_sheet_rejects_duplicate_id(self):
        analysis = Analysis(analysis_id_suffix="test-analysis", name="Test")
        analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-dup"),
            name="A", title="A", description="",
        ))
        with pytest.raises(ValueError, match="already on this Analysis"):
            analysis.add_sheet(Sheet(
                sheet_id=SheetId("sheet-dup"),
                name="B", title="B", description="",
            ))

    def test_emit_definition_carries_sheets(self):
        analysis = Analysis(analysis_id_suffix="test-analysis", name="Test")
        analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-1"),
            name="A", title="A", description="",
        ))
        analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-2"),
            name="B", title="B", description="",
        ))
        defn = analysis.emit_definition(dataset_declarations=[])
        assert [s.SheetId for s in defn.Sheets] == ["sheet-1", "sheet-2"]

    def test_emit_definition_passes_through_dataset_declarations(self):
        from quicksight_gen.common.models import DataSetIdentifierDeclaration
        analysis = Analysis(analysis_id_suffix="test-analysis", name="Test")
        decls = [
            DataSetIdentifierDeclaration(
                Identifier="ds-foo",
                DataSetArn="arn:aws:quicksight:::dataset/foo",
            ),
        ]
        defn = analysis.emit_definition(dataset_declarations=decls)
        assert defn.DataSetIdentifierDeclarations == decls


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

class TestApp:
    def _make_app_with_one_sheet(self) -> App:
        app = App(name="test-app", cfg=_TEST_CFG)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="test-analysis",
            name="Test Analysis",
        ))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-1"),
            name="A", title="A", description="",
        ))
        node = sheet.add_visual(_make_kpi("v-1"))
        sheet.place(node, col_span=36, row_span=18, col_index=0)
        return app

    def test_emit_analysis_builds_model_analysis(self):
        app = self._make_app_with_one_sheet()
        analysis = app.emit_analysis(dataset_declarations=[])
        assert analysis.AwsAccountId == "111122223333"
        assert analysis.AnalysisId.startswith("qs-gen-")
        assert analysis.AnalysisId.endswith("test-analysis")
        assert analysis.Name == "Test Analysis"
        assert analysis.ThemeArn  # non-empty
        assert analysis.Definition is not None
        assert len(analysis.Definition.Sheets) == 1

    def test_emit_analysis_without_analysis_raises(self):
        app = App(name="test-app", cfg=_TEST_CFG)
        with pytest.raises(ValueError, match="set_analysis"):
            app.emit_analysis(dataset_declarations=[])

    def test_set_dashboard_validates_analysis_match(self):
        """Dashboard.analysis must be the same instance the App owns —
        catches the cross-app dashboard wiring bug class."""
        app = self._make_app_with_one_sheet()
        other_analysis = Analysis(
            analysis_id_suffix="other-analysis", name="Other",
        )
        with pytest.raises(ValueError, match="must be the same Analysis"):
            app.set_dashboard(Dashboard(
                dashboard_id_suffix="test-dashboard",
                name="Test Dashboard",
                analysis=other_analysis,  # wrong instance
            ))

    def test_set_dashboard_with_correct_analysis(self):
        app = self._make_app_with_one_sheet()
        ret = app.set_dashboard(Dashboard(
            dashboard_id_suffix="test-dashboard",
            name="Test Dashboard",
            analysis=app.analysis,  # correct
        ))
        assert ret is app.dashboard

    def test_emit_dashboard_builds_model_dashboard(self):
        app = self._make_app_with_one_sheet()
        app.set_dashboard(Dashboard(
            dashboard_id_suffix="test-dashboard",
            name="Test Dashboard",
            analysis=app.analysis,
        ))
        dashboard = app.emit_dashboard(dataset_declarations=[])
        assert dashboard.AwsAccountId == "111122223333"
        assert dashboard.DashboardId.startswith("qs-gen-")
        assert dashboard.DashboardId.endswith("test-dashboard")
        assert dashboard.Name == "Test Dashboard"
        assert dashboard.Definition is not None
        # Same definition shape as the Analysis's
        assert len(dashboard.Definition.Sheets) == 1

    def test_emit_dashboard_without_dashboard_raises(self):
        app = self._make_app_with_one_sheet()
        with pytest.raises(ValueError, match="set_dashboard"):
            app.emit_dashboard(dataset_declarations=[])

    def test_emit_analysis_round_trips_through_to_aws_json(self):
        """The whole point — tree-built models.Analysis serializes
        cleanly through the existing to_aws_json path."""
        app = self._make_app_with_one_sheet()
        analysis = app.emit_analysis(dataset_declarations=[])
        j = analysis.to_aws_json()
        assert j["AwsAccountId"] == "111122223333"
        assert j["AnalysisId"].endswith("test-analysis")
        assert "Definition" in j
        assert len(j["Definition"]["Sheets"]) == 1
        assert j["Definition"]["Sheets"][0]["SheetId"] == "sheet-1"


# ---------------------------------------------------------------------------
# L.1.3 — Field-well wrappers (Dim, Measure)
# ---------------------------------------------------------------------------

class TestDim:
    def test_categorical_default(self):
        dim = Dim(dataset="ds-foo", field_id="f-1", column="col_a")
        emitted = dim.emit()
        assert emitted.CategoricalDimensionField is not None
        assert emitted.CategoricalDimensionField.FieldId == "f-1"
        assert emitted.CategoricalDimensionField.Column.ColumnName == "col_a"
        assert emitted.CategoricalDimensionField.Column.DataSetIdentifier == "ds-foo"

    def test_date_factory(self):
        dim = Dim.date(dataset="ds-foo", field_id="f-d", column="posted_at")
        emitted = dim.emit()
        assert emitted.DateDimensionField is not None
        assert emitted.CategoricalDimensionField is None

    def test_numerical_factory(self):
        dim = Dim.numerical(dataset="ds-foo", field_id="f-n", column="depth")
        emitted = dim.emit()
        assert emitted.NumericalDimensionField is not None


class TestMeasure:
    def test_sum_emits_numerical_field(self):
        m = Measure.sum(dataset="ds-foo", field_id="f-1", column="amount")
        emitted = m.emit()
        assert emitted.NumericalMeasureField is not None
        assert emitted.NumericalMeasureField.AggregationFunction.SimpleNumericalAggregation == "SUM"

    def test_max_min_average(self):
        for kind, expected in [("max", "MAX"), ("min", "MIN"), ("average", "AVERAGE")]:
            m = getattr(Measure, kind)(dataset="ds", field_id=f"f-{kind}", column="amount")
            emitted = m.emit()
            assert emitted.NumericalMeasureField.AggregationFunction.SimpleNumericalAggregation == expected

    def test_count_emits_categorical_field(self):
        m = Measure.count(dataset="ds-foo", field_id="f-1", column="account_id")
        emitted = m.emit()
        assert emitted.CategoricalMeasureField is not None
        assert emitted.CategoricalMeasureField.AggregationFunction == "COUNT"

    def test_distinct_count_emits_categorical_field(self):
        m = Measure.distinct_count(dataset="ds-foo", field_id="f-1", column="account_id")
        emitted = m.emit()
        assert emitted.CategoricalMeasureField is not None
        assert emitted.CategoricalMeasureField.AggregationFunction == "DISTINCT_COUNT"


# ---------------------------------------------------------------------------
# L.1.3 — Typed Visual subtypes
# ---------------------------------------------------------------------------

class TestKPIVisual:
    def test_emits_kpi_visual(self):
        kpi = KPI(
            visual_id=VisualId("v-kpi"),
            title="Total",
            subtitle="Sum of amounts",
            values=[Measure.sum("ds-foo", "f-val", "amount")],
        )
        emitted = kpi.emit()
        assert emitted.KPIVisual is not None
        assert emitted.KPIVisual.VisualId == "v-kpi"
        assert emitted.KPIVisual.Title.FormatText["PlainText"] == "Total"
        assert emitted.KPIVisual.Subtitle.FormatText["PlainText"] == "Sum of amounts"

    def test_subtitle_optional(self):
        kpi = KPI(
            visual_id=VisualId("v-kpi"),
            title="Total",
            values=[Measure.sum("ds-foo", "f-val", "amount")],
        )
        emitted = kpi.emit()
        assert emitted.KPIVisual.Subtitle is None

    def test_satisfies_visual_like_protocol(self):
        kpi = KPI(visual_id=VisualId("v-kpi"), title="Test")
        assert isinstance(kpi, VisualLike)


class TestTableVisual:
    def test_emits_table_with_group_by_and_values(self):
        table = Table(
            visual_id=VisualId("v-tbl"),
            title="Detail",
            group_by=[
                Dim(dataset="ds", field_id="f-id", column="id"),
                Dim(dataset="ds", field_id="f-name", column="name"),
            ],
            values=[Measure.sum(dataset="ds", field_id="f-amt", column="amount")],
        )
        emitted = table.emit()
        assert emitted.TableVisual is not None
        wells = emitted.TableVisual.ChartConfiguration.FieldWells.TableAggregatedFieldWells
        assert len(wells.GroupBy) == 2
        assert len(wells.Values) == 1

    def test_sort_by(self):
        table = Table(
            visual_id=VisualId("v-tbl"),
            title="Detail",
            sort_by=("f-amt", "DESC"),
        )
        emitted = table.emit()
        sort = emitted.TableVisual.ChartConfiguration.SortConfiguration
        assert sort["RowSort"][0]["FieldSort"]["FieldId"] == "f-amt"
        assert sort["RowSort"][0]["FieldSort"]["Direction"] == "DESC"


class TestBarChartVisual:
    def test_emits_bar_with_category_and_values(self):
        bar = BarChart(
            visual_id=VisualId("v-bar"),
            title="By Bucket",
            category=[Dim(dataset="ds", field_id="f-bucket", column="z_bucket")],
            values=[Measure.count(dataset="ds", field_id="f-cnt", column="recipient_id")],
        )
        emitted = bar.emit()
        assert emitted.BarChartVisual is not None
        wells = emitted.BarChartVisual.ChartConfiguration.FieldWells.BarChartAggregatedFieldWells
        assert len(wells.Category) == 1
        assert len(wells.Values) == 1


class TestSankeyVisual:
    def test_emits_sankey_with_source_target_weight(self):
        sankey = Sankey(
            visual_id=VisualId("v-sankey"),
            title="Flow",
            source=Dim(dataset="ds", field_id="f-src", column="source_display"),
            target=Dim(dataset="ds", field_id="f-tgt", column="target_display"),
            weight=Measure.sum(dataset="ds", field_id="f-wt", column="hop_amount"),
            items_limit=50,
        )
        emitted = sankey.emit()
        assert emitted.SankeyDiagramVisual is not None
        wells = emitted.SankeyDiagramVisual.ChartConfiguration.FieldWells.SankeyDiagramAggregatedFieldWells
        assert len(wells.Source) == 1
        assert wells.Source[0].CategoricalDimensionField.Column.ColumnName == "source_display"
        assert len(wells.Destination) == 1
        assert wells.Destination[0].CategoricalDimensionField.Column.ColumnName == "target_display"
        assert len(wells.Weight) == 1

    def test_weight_drives_sort_desc(self):
        sankey = Sankey(
            visual_id=VisualId("v-sankey"),
            title="Flow",
            weight=Measure.sum(dataset="ds", field_id="f-wt", column="hop_amount"),
        )
        emitted = sankey.emit()
        sort = emitted.SankeyDiagramVisual.ChartConfiguration.SortConfiguration
        assert sort.WeightSort[0]["FieldSort"]["FieldId"] == "f-wt"
        assert sort.WeightSort[0]["FieldSort"]["Direction"] == "DESC"

    def test_items_limit_caps_both_sides(self):
        sankey = Sankey(
            visual_id=VisualId("v-sankey"),
            title="Flow",
            items_limit=25,
        )
        emitted = sankey.emit()
        sort = emitted.SankeyDiagramVisual.ChartConfiguration.SortConfiguration
        assert sort.SourceItemsLimit["ItemsLimit"] == 25
        assert sort.DestinationItemsLimit["ItemsLimit"] == 25
        assert sort.SourceItemsLimit["OtherCategories"] == "INCLUDE"


class TestSheetAcceptsTypedVisuals:
    """Sheet.add_visual accepts both spike-shape VisualNode and typed
    subtypes — same VisualLike Protocol path."""

    def test_add_kpi(self):
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        )
        kpi = sheet.add_visual(KPI(
            visual_id=VisualId("v-kpi"),
            title="Total",
            values=[Measure.sum("ds", "f", "amount")],
        ))
        sheet.place(kpi, col_span=12, row_span=6, col_index=0)
        emitted = sheet.emit()
        assert emitted.Visuals[0].KPIVisual.VisualId == "v-kpi"
        assert emitted.Layouts[0].Configuration.GridLayout.Elements[0].ElementId == "v-kpi"

    def test_add_visual_returns_concrete_subtype(self):
        """Generic add_visual preserves the caller's concrete subtype
        — the returned ref still types as KPI, not the widened
        VisualLike Protocol."""
        sheet = Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        )
        kpi: KPI = sheet.add_visual(KPI(
            visual_id=VisualId("v-kpi"), title="Test",
        ))
        # If the generic worked, kpi is still a KPI — accessing
        # KPI-only attributes shouldn't widen.
        assert kpi.title == "Test"


# ---------------------------------------------------------------------------
# L.1.4 — Parameter declarations
# ---------------------------------------------------------------------------

class TestStringParam:
    def test_emits_single_valued_string_param(self):
        p = StringParam(
            name=ParameterName("pTest"),
            default=["default-value"],
        )
        emitted = p.emit()
        assert emitted.StringParameterDeclaration is not None
        assert emitted.StringParameterDeclaration.Name == "pTest"
        assert emitted.StringParameterDeclaration.ParameterValueType == "SINGLE_VALUED"
        assert emitted.StringParameterDeclaration.DefaultValues == {"StaticValues": ["default-value"]}

    def test_no_default_emits_empty_static_values(self):
        """No-default pattern matches the existing
        ``DefaultValues={"StaticValues": []}`` shape used by the
        K.4.5 chain-root + K.4.8 anchor parameters (which rely on
        the SelectAll=HIDDEN dropdown to land on first row)."""
        p = StringParam(name=ParameterName("pNoDefault"))
        emitted = p.emit()
        assert emitted.StringParameterDeclaration.DefaultValues == {"StaticValues": []}

    def test_multi_valued(self):
        p = StringParam(
            name=ParameterName("pMulti"),
            default=["a", "b"],
            multi_valued=True,
        )
        emitted = p.emit()
        assert emitted.StringParameterDeclaration.ParameterValueType == "MULTI_VALUED"


class TestIntegerParam:
    def test_emits_integer_param_with_default(self):
        p = IntegerParam(
            name=ParameterName("pSigma"),
            default=[2],
        )
        emitted = p.emit()
        assert emitted.IntegerParameterDeclaration is not None
        assert emitted.IntegerParameterDeclaration.Name == "pSigma"
        assert emitted.IntegerParameterDeclaration.DefaultValues == {"StaticValues": [2]}


class TestDateTimeParam:
    def test_emits_datetime_param_with_rolling_default(self):
        """RollingDate pattern — same shape as AR's pArDsBalanceDate
        (P_AR_DS_BALANCE_DATE) which uses ``truncDate('DD', now())``
        for "today"."""
        p = DateTimeParam(
            name=ParameterName("pDate"),
            time_granularity="DAY",
            default=DateTimeDefaultValues(
                RollingDate={"Expression": "truncDate('DD', now())"},
            ),
        )
        emitted = p.emit()
        assert emitted.DateTimeParameterDeclaration is not None
        assert emitted.DateTimeParameterDeclaration.TimeGranularity == "DAY"
        assert emitted.DateTimeParameterDeclaration.DefaultValues.RollingDate is not None


class TestAnalysisAddParameter:
    def test_add_parameter_returns_concrete_subtype(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        sigma: IntegerParam = analysis.add_parameter(IntegerParam(
            name=ParameterName("pSigma"), default=[2],
        ))
        # Concrete subtype preserved through the generic.
        assert sigma.default == [2]

    def test_duplicate_parameter_name_raises(self):
        """Same-name shadow bug class: two declarations sharing a Name
        silently let one win at deploy time. Caught at construction."""
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        analysis.add_parameter(IntegerParam(name=ParameterName("pDup"), default=[1]))
        with pytest.raises(ValueError, match="already declared"):
            analysis.add_parameter(StringParam(name=ParameterName("pDup")))

    def test_emit_definition_carries_parameter_declarations(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        analysis.add_parameter(IntegerParam(
            name=ParameterName("pSigma"), default=[2],
        ))
        analysis.add_parameter(StringParam(
            name=ParameterName("pAnchor"),
        ))
        defn = analysis.emit_definition(dataset_declarations=[])
        names = []
        for pd in defn.ParameterDeclarations:
            if pd.IntegerParameterDeclaration:
                names.append(pd.IntegerParameterDeclaration.Name)
            elif pd.StringParameterDeclaration:
                names.append(pd.StringParameterDeclaration.Name)
        assert names == ["pSigma", "pAnchor"]

    def test_no_parameters_emits_none(self):
        """Analysis without any parameter declarations passes None to
        models.AnalysisDefinition (preserving the existing pattern that
        omits empty fields)."""
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        defn = analysis.emit_definition(dataset_declarations=[])
        assert defn.ParameterDeclarations is None


# ---------------------------------------------------------------------------
# L.1.5 — FilterGroup with object-ref scope + scope-on-same-sheet validation
# ---------------------------------------------------------------------------

def _category_filter(filter_id: str, dataset: str, column: str) -> CategoryFilter:
    """Test-only typed CategoryFilter constructor — keeps the test
    focus on scope validation, not Filter construction details."""
    return CategoryFilter(
        filter_id=filter_id,
        dataset=dataset,
        column=column,
        values=["yes"],
    )


class TestFilterGroupScope:
    def _make_sheet_with_visuals(
        self, sheet_id: str, *visual_ids: str,
    ) -> tuple[Sheet, list[KPI]]:
        sheet = Sheet(
            sheet_id=SheetId(sheet_id),
            name="Test", title="Test", description="",
        )
        visuals = []
        for vid in visual_ids:
            v = sheet.add_visual(KPI(visual_id=VisualId(vid), title=vid))
            visuals.append(v)
        return sheet, visuals

    def test_scope_visuals_validates_visual_is_on_sheet(self):
        """Wrong-sheet bug: scope_visuals raises if any visual isn't
        registered on the given sheet. Catches the bug class at the
        wiring line."""
        sheet_a, [v_a] = self._make_sheet_with_visuals("sheet-a", "v-a")
        sheet_b, [v_b] = self._make_sheet_with_visuals("sheet-b", "v-b")

        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        )
        with pytest.raises(ValueError, match="isn't registered on sheet"):
            # Trying to scope a visual from sheet-a onto sheet-b
            fg.scope_visuals(sheet_b, [v_a])

    def test_scope_visuals_with_correct_visuals_succeeds(self):
        sheet, [v1, v2] = self._make_sheet_with_visuals(
            "sheet-test", "v-1", "v-2",
        )
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        )
        ret = fg.scope_visuals(sheet, [v1, v2])
        assert ret is fg  # chains
        assert len(fg._scope_entries) == 1

    def test_scope_visuals_emits_selected_visuals_configuration(self):
        sheet, [v1, v2] = self._make_sheet_with_visuals(
            "sheet-test", "v-1", "v-2",
        )
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        )
        fg.scope_visuals(sheet, [v1, v2])
        emitted = fg.emit()
        configs = emitted.ScopeConfiguration.SelectedSheets.SheetVisualScopingConfigurations
        assert len(configs) == 1
        assert configs[0].SheetId == "sheet-test"
        assert configs[0].Scope == "SELECTED_VISUALS"
        assert configs[0].VisualIds == ["v-1", "v-2"]

    def test_scope_sheet_emits_all_visuals_configuration(self):
        sheet, _ = self._make_sheet_with_visuals(
            "sheet-test", "v-1", "v-2",
        )
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        )
        fg.scope_sheet(sheet)
        emitted = fg.emit()
        configs = emitted.ScopeConfiguration.SelectedSheets.SheetVisualScopingConfigurations
        assert configs[0].SheetId == "sheet-test"
        assert configs[0].Scope == "ALL_VISUALS"
        assert configs[0].VisualIds is None

    def test_emit_without_scope_raises(self):
        """A FilterGroup with no scope configured wouldn't apply to
        anything at deploy — fail loud at construction rather than
        silently emitting an empty configuration."""
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        )
        with pytest.raises(ValueError, match="has no scope"):
            fg.emit()

    def test_multiple_scope_entries(self):
        """A FilterGroup can scope to (visual subset on sheet A) plus
        (all visuals on sheet B). Each entry emits its own
        SheetVisualScopingConfiguration."""
        sheet_a, [v_a1, v_a2] = self._make_sheet_with_visuals(
            "sheet-a", "v-a1", "v-a2",
        )
        sheet_b, _ = self._make_sheet_with_visuals(
            "sheet-b", "v-b1",
        )
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-multi"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        )
        fg.scope_visuals(sheet_a, [v_a1])
        fg.scope_sheet(sheet_b)
        emitted = fg.emit()
        configs = emitted.ScopeConfiguration.SelectedSheets.SheetVisualScopingConfigurations
        assert len(configs) == 2
        assert configs[0].SheetId == "sheet-a"
        assert configs[0].Scope == "SELECTED_VISUALS"
        assert configs[0].VisualIds == ["v-a1"]
        assert configs[1].SheetId == "sheet-b"
        assert configs[1].Scope == "ALL_VISUALS"

    def test_emit_carries_filters_through(self):
        """Each typed FilterLike's emit() runs at FilterGroup.emit() time —
        the emitted Filters list contains the corresponding models.Filter
        instances, not the typed wrappers themselves."""
        sheet, _ = self._make_sheet_with_visuals("sheet-test", "v-1")
        f = _category_filter("f-1", "ds-foo", "col_a")
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[f],
        )
        fg.scope_sheet(sheet)
        emitted = fg.emit()
        assert len(emitted.Filters) == 1
        emitted_filter = emitted.Filters[0]
        assert emitted_filter.CategoryFilter is not None
        assert emitted_filter.CategoryFilter.FilterId == "f-1"

    def test_disabled_filter_group(self):
        sheet, _ = self._make_sheet_with_visuals("sheet-test", "v-1")
        fg = FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
            enabled=False,
        )
        fg.scope_sheet(sheet)
        emitted = fg.emit()
        assert emitted.Status == "DISABLED"


class TestAnalysisAddFilterGroup:
    def test_add_filter_group_returns_ref(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        ))
        kpi = sheet.add_visual(KPI(visual_id=VisualId("v-1"), title="Test"))
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        assert fg in analysis.filter_groups

    def test_duplicate_filter_group_id_raises(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-dup"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        ))
        with pytest.raises(ValueError, match="already on this Analysis"):
            analysis.add_filter_group(FilterGroup(
                filter_group_id=FilterGroupId("fg-dup"),
                filters=[_category_filter("f-2", "ds-foo", "col_b")],
            ))

    def test_emit_definition_carries_filter_groups(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        ))
        kpi = sheet.add_visual(KPI(visual_id=VisualId("v-1"), title="Test"))
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-test"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        defn = analysis.emit_definition(dataset_declarations=[])
        assert len(defn.FilterGroups) == 1
        assert defn.FilterGroups[0].FilterGroupId == "fg-test"

    def test_no_filter_groups_emits_none(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        defn = analysis.emit_definition(dataset_declarations=[])
        assert defn.FilterGroups is None


class TestFilterGroupCompositionWithApp:
    """Cross-check: the wrong-sheet bug class is caught even when
    FilterGroups go through the full App.emit_analysis path.

    The L.1.5 check-in moment — the load-bearing object-ref scope
    validation works end-to-end."""

    def test_wrong_sheet_visual_caught_at_scope_call(self):
        app = App(name="test", cfg=_TEST_CFG)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="test", name="Test",
        ))
        sheet_a = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-a"),
            name="A", title="A", description="",
        ))
        v_a = sheet_a.add_visual(KPI(
            visual_id=VisualId("v-a"), title="A",
        ))
        sheet_b = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-b"),
            name="B", title="B", description="",
        ))
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-cross"),
            filters=[_category_filter("f-1", "ds", "col")],
        ))
        # Try to scope sheet-A's visual onto sheet-B → caught here.
        with pytest.raises(ValueError, match="isn't registered on sheet"):
            fg.scope_visuals(sheet_b, [v_a])

# ---------------------------------------------------------------------------
# L.1.6 — Typed Filter wrappers
# ---------------------------------------------------------------------------

class TestTypedCategoryFilter:
    def test_emits_filter_list_configuration(self):
        f = CategoryFilter(
            filter_id="f-1",
            dataset="ds-foo",
            column="col_a",
            values=["yes", "maybe"],
        )
        emitted = f.emit()
        assert emitted.CategoryFilter is not None
        assert emitted.CategoryFilter.FilterId == "f-1"
        assert emitted.CategoryFilter.Column.DataSetIdentifier == "ds-foo"
        assert emitted.CategoryFilter.Column.ColumnName == "col_a"
        config = emitted.CategoryFilter.Configuration.FilterListConfiguration
        assert config["MatchOperator"] == "CONTAINS"
        assert config["CategoryValues"] == ["yes", "maybe"]

    def test_match_operator_is_configurable(self):
        f = CategoryFilter(
            filter_id="f-1", dataset="ds", column="col_a",
            values=["a"], match_operator="EQUALS",
        )
        emitted = f.emit()
        assert emitted.CategoryFilter.Configuration.FilterListConfiguration["MatchOperator"] == "EQUALS"

    def test_satisfies_filter_like_protocol(self):
        f = CategoryFilter(
            filter_id="f-1", dataset="ds", column="col_a", values=["x"],
        )
        assert isinstance(f, FilterLike)


class TestTypedNumericRangeFilter:
    def test_static_bounds(self):
        f = NumericRangeFilter(
            filter_id="f-1",
            dataset="ds",
            column="amount",
            minimum_value=10.0,
            maximum_value=1000.0,
        )
        emitted = f.emit()
        assert emitted.NumericRangeFilter is not None
        assert emitted.NumericRangeFilter.RangeMinimum.StaticValue == 10.0
        assert emitted.NumericRangeFilter.RangeMaximum.StaticValue == 1000.0
        assert emitted.NumericRangeFilter.RangeMinimum.Parameter is None

    def test_parameter_bound_minimum(self):
        """The wiring catches "filter bound to a parameter that doesn't
        exist" — pass an actual ParameterDecl object, the type checker
        guarantees it has a .name. emit() reads param.name to populate
        NumericRangeFilterValue.Parameter."""
        sigma = IntegerParam(
            name=ParameterName("pSigma"), default=[2],
        )
        f = NumericRangeFilter(
            filter_id="f-sigma",
            dataset="ds",
            column="z_score",
            minimum_parameter=sigma,
        )
        emitted = f.emit()
        assert emitted.NumericRangeFilter.RangeMinimum.Parameter == "pSigma"
        assert emitted.NumericRangeFilter.RangeMinimum.StaticValue is None
        assert emitted.NumericRangeFilter.RangeMaximum is None

    def test_both_minimum_value_and_parameter_rejected(self):
        sigma = IntegerParam(name=ParameterName("pSigma"), default=[2])
        with pytest.raises(ValueError, match="not both"):
            NumericRangeFilter(
                filter_id="f-1",
                dataset="ds",
                column="amount",
                minimum_value=10.0,
                minimum_parameter=sigma,
            )

    def test_both_maximum_value_and_parameter_rejected(self):
        sigma = IntegerParam(name=ParameterName("pSigma"), default=[2])
        with pytest.raises(ValueError, match="not both"):
            NumericRangeFilter(
                filter_id="f-1",
                dataset="ds",
                column="amount",
                maximum_value=10.0,
                maximum_parameter=sigma,
            )

    def test_no_bounds_emits_filter_with_no_range(self):
        """A NumericRangeFilter with no min/max is unusual but allowed
        (matches the existing model behaviour where RangeMinimum /
        RangeMaximum are optional)."""
        f = NumericRangeFilter(
            filter_id="f-1", dataset="ds", column="amount",
        )
        emitted = f.emit()
        assert emitted.NumericRangeFilter.RangeMinimum is None
        assert emitted.NumericRangeFilter.RangeMaximum is None

    def test_satisfies_filter_like_protocol(self):
        f = NumericRangeFilter(
            filter_id="f-1", dataset="ds", column="amount",
        )
        assert isinstance(f, FilterLike)


class TestTypedTimeRangeFilter:
    def test_emits_with_min_max_passthrough(self):
        f = TimeRangeFilter(
            filter_id="f-1",
            dataset="ds",
            column="posted_at",
            minimum={"StaticValue": "2026-01-01T00:00:00"},
            maximum={"StaticValue": "2026-12-31T23:59:59"},
            time_granularity="DAY",
        )
        emitted = f.emit()
        assert emitted.TimeRangeFilter is not None
        assert emitted.TimeRangeFilter.RangeMinimumValue == {"StaticValue": "2026-01-01T00:00:00"}
        assert emitted.TimeRangeFilter.TimeGranularity == "DAY"

    def test_satisfies_filter_like_protocol(self):
        f = TimeRangeFilter(
            filter_id="f-1", dataset="ds", column="posted_at",
        )
        assert isinstance(f, FilterLike)


class TestFullEmitRoundTripWithTypedFilters:
    """Replaces the placeholder above; threads through App.emit_analysis
    to confirm typed Filter wrappers serialize cleanly end-to-end."""

    def test_full_emit_round_trip(self):
        app = App(name="test", cfg=_TEST_CFG)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="test", name="Test",
        ))
        sigma = analysis.add_parameter(IntegerParam(
            name=ParameterName("pSigma"), default=[2],
        ))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        ))
        kpi = sheet.add_visual(KPI(
            visual_id=VisualId("v-test"), title="Test",
            values=[Measure.sum("ds-foo", "f-val", "amount")],
        ))
        sheet.place(kpi, col_span=12, row_span=6, col_index=0)
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-sigma"),
            filters=[
                NumericRangeFilter(
                    filter_id="f-sigma",
                    dataset="ds-foo",
                    column="z_score",
                    minimum_parameter=sigma,
                ),
            ],
        ))
        fg.scope_visuals(sheet, [kpi])
        m = app.emit_analysis(dataset_declarations=[])
        j = m.to_aws_json()
        fg_json = j["Definition"]["FilterGroups"][0]
        nrf = fg_json["Filters"][0]["NumericRangeFilter"]
        assert nrf["FilterId"] == "f-sigma"
        assert nrf["Column"]["ColumnName"] == "z_score"
        assert nrf["RangeMinimum"]["Parameter"] == "pSigma"
        # Static values not emitted when unset.
        assert "StaticValue" not in nrf["RangeMinimum"]


    def test_scoping_configuration_round_trips(self):
        """End-to-end: tree → FilterGroup with scope → App.emit_analysis →
        models.Analysis.to_aws_json carries the scoping configuration
        through to the emitted JSON. Carried over from the L.1.5
        composition tests; lives here now alongside the typed-filter
        round-trip."""
        app = App(name="test", cfg=_TEST_CFG)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="test", name="Test",
        ))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        ))
        kpi = sheet.add_visual(KPI(
            visual_id=VisualId("v-test"), title="Test",
            values=[Measure.sum("ds-foo", "f-val", "amount")],
        ))
        sheet.place(kpi, col_span=12, row_span=6, col_index=0)
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-scoped"),
            filters=[_category_filter("f-1", "ds-foo", "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        m = app.emit_analysis(dataset_declarations=[])
        j = m.to_aws_json()
        fgs = j["Definition"]["FilterGroups"]
        assert len(fgs) == 1
        assert fgs[0]["FilterGroupId"] == "fg-scoped"
        configs = fgs[0]["ScopeConfiguration"]["SelectedSheets"]["SheetVisualScopingConfigurations"]
        assert configs[0]["SheetId"] == "sheet-test"
        assert configs[0]["Scope"] == "SELECTED_VISUALS"
        assert configs[0]["VisualIds"] == ["v-test"]
