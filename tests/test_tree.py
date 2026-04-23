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
    Dataset,
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


# Module-level Dataset fixtures used across the L.1.3 / L.1.6 tests.
# Real apps use a per-app dataset registry on the App; tests use these
# stand-ins. The identifiers ("ds", "ds-foo", "ds-anomalies") match
# the strings the pre-L.1.7 tests passed.
_DS = Dataset(identifier="ds", arn="arn:aws:quicksight:::dataset/ds")
_DS_FOO = Dataset(identifier="ds-foo", arn="arn:aws:quicksight:::dataset/ds-foo")
_DS_ANOMALIES = Dataset(
    identifier="ds-anomalies", arn="arn:aws:quicksight:::dataset/ds-anomalies",
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
        assert slot.element is node
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
        defn = analysis.emit_definition(datasets=[])
        assert [s.SheetId for s in defn.Sheets] == ["sheet-1", "sheet-2"]

    def test_emit_definition_emits_dataset_declarations_from_dataset_refs(self):
        analysis = Analysis(analysis_id_suffix="test-analysis", name="Test")
        defn = analysis.emit_definition(datasets=[_DS_FOO])
        assert len(defn.DataSetIdentifierDeclarations) == 1
        assert defn.DataSetIdentifierDeclarations[0].Identifier == "ds-foo"
        assert defn.DataSetIdentifierDeclarations[0].DataSetArn == _DS_FOO.arn


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
        analysis = app.emit_analysis()
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
            app.emit_analysis()

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
        dashboard = app.emit_dashboard()
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
            app.emit_dashboard()

    def test_emit_analysis_round_trips_through_to_aws_json(self):
        """The whole point — tree-built models.Analysis serializes
        cleanly through the existing to_aws_json path."""
        app = self._make_app_with_one_sheet()
        analysis = app.emit_analysis()
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
        dim = Dim(dataset=_DS_FOO, field_id="f-1", column="col_a")
        emitted = dim.emit()
        assert emitted.CategoricalDimensionField is not None
        assert emitted.CategoricalDimensionField.FieldId == "f-1"
        assert emitted.CategoricalDimensionField.Column.ColumnName == "col_a"
        assert emitted.CategoricalDimensionField.Column.DataSetIdentifier == "ds-foo"

    def test_date_factory(self):
        dim = Dim.date(dataset=_DS_FOO, field_id="f-d", column="posted_at")
        emitted = dim.emit()
        assert emitted.DateDimensionField is not None
        assert emitted.CategoricalDimensionField is None

    def test_numerical_factory(self):
        dim = Dim.numerical(dataset=_DS_FOO, field_id="f-n", column="depth")
        emitted = dim.emit()
        assert emitted.NumericalDimensionField is not None


class TestMeasure:
    def test_sum_emits_numerical_field(self):
        m = Measure.sum(dataset=_DS_FOO, field_id="f-1", column="amount")
        emitted = m.emit()
        assert emitted.NumericalMeasureField is not None
        assert emitted.NumericalMeasureField.AggregationFunction.SimpleNumericalAggregation == "SUM"

    def test_max_min_average(self):
        for kind, expected in [("max", "MAX"), ("min", "MIN"), ("average", "AVERAGE")]:
            m = getattr(Measure, kind)(dataset=_DS, field_id=f"f-{kind}", column="amount")
            emitted = m.emit()
            assert emitted.NumericalMeasureField.AggregationFunction.SimpleNumericalAggregation == expected

    def test_count_emits_categorical_field(self):
        m = Measure.count(dataset=_DS_FOO, field_id="f-1", column="account_id")
        emitted = m.emit()
        assert emitted.CategoricalMeasureField is not None
        assert emitted.CategoricalMeasureField.AggregationFunction == "COUNT"

    def test_distinct_count_emits_categorical_field(self):
        m = Measure.distinct_count(dataset=_DS_FOO, field_id="f-1", column="account_id")
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
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
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
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
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
                Dim(dataset=_DS, field_id="f-id", column="id"),
                Dim(dataset=_DS, field_id="f-name", column="name"),
            ],
            values=[Measure.sum(dataset=_DS, field_id="f-amt", column="amount")],
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
            category=[Dim(dataset=_DS, field_id="f-bucket", column="z_bucket")],
            values=[Measure.count(dataset=_DS, field_id="f-cnt", column="recipient_id")],
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
            source=Dim(dataset=_DS, field_id="f-src", column="source_display"),
            target=Dim(dataset=_DS, field_id="f-tgt", column="target_display"),
            weight=Measure.sum(dataset=_DS, field_id="f-wt", column="hop_amount"),
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
            weight=Measure.sum(dataset=_DS, field_id="f-wt", column="hop_amount"),
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
            values=[Measure.sum(_DS, "amount", field_id="f")],
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
        defn = analysis.emit_definition(datasets=[])
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
        defn = analysis.emit_definition(datasets=[])
        assert defn.ParameterDeclarations is None


# ---------------------------------------------------------------------------
# L.1.5 — FilterGroup with object-ref scope + scope-on-same-sheet validation
# ---------------------------------------------------------------------------

def _category_filter(
    filter_id: str, dataset: Dataset, column: str,
) -> CategoryFilter:
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
        f = _category_filter("f-1", _DS_FOO, "col_a")
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        assert fg in analysis.filter_groups

    def test_duplicate_filter_group_id_raises(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-dup"),
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
        ))
        with pytest.raises(ValueError, match="already on this Analysis"):
            analysis.add_filter_group(FilterGroup(
                filter_group_id=FilterGroupId("fg-dup"),
                filters=[_category_filter("f-2", _DS_FOO, "col_b")],
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
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        defn = analysis.emit_definition(datasets=[])
        assert len(defn.FilterGroups) == 1
        assert defn.FilterGroups[0].FilterGroupId == "fg-test"

    def test_no_filter_groups_emits_none(self):
        analysis = Analysis(analysis_id_suffix="test", name="Test")
        defn = analysis.emit_definition(datasets=[])
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
            filters=[_category_filter("f-1", _DS, "col")],
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
            dataset=_DS_FOO,
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
            filter_id="f-1", dataset=_DS, column="col_a",
            values=["a"], match_operator="EQUALS",
        )
        emitted = f.emit()
        assert emitted.CategoryFilter.Configuration.FilterListConfiguration["MatchOperator"] == "EQUALS"

    def test_satisfies_filter_like_protocol(self):
        f = CategoryFilter(
            filter_id="f-1", dataset=_DS, column="col_a", values=["x"],
        )
        assert isinstance(f, FilterLike)


class TestTypedNumericRangeFilter:
    def test_static_bounds(self):
        f = NumericRangeFilter(
            filter_id="f-1",
            dataset=_DS,
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
            dataset=_DS,
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
                dataset=_DS,
                column="amount",
                minimum_value=10.0,
                minimum_parameter=sigma,
            )

    def test_both_maximum_value_and_parameter_rejected(self):
        sigma = IntegerParam(name=ParameterName("pSigma"), default=[2])
        with pytest.raises(ValueError, match="not both"):
            NumericRangeFilter(
                filter_id="f-1",
                dataset=_DS,
                column="amount",
                maximum_value=10.0,
                maximum_parameter=sigma,
            )

    def test_no_bounds_emits_filter_with_no_range(self):
        """A NumericRangeFilter with no min/max is unusual but allowed
        (matches the existing model behaviour where RangeMinimum /
        RangeMaximum are optional)."""
        f = NumericRangeFilter(
            filter_id="f-1", dataset=_DS, column="amount",
        )
        emitted = f.emit()
        assert emitted.NumericRangeFilter.RangeMinimum is None
        assert emitted.NumericRangeFilter.RangeMaximum is None

    def test_satisfies_filter_like_protocol(self):
        f = NumericRangeFilter(
            filter_id="f-1", dataset=_DS, column="amount",
        )
        assert isinstance(f, FilterLike)


class TestTypedTimeRangeFilter:
    def test_emits_with_min_max_passthrough(self):
        f = TimeRangeFilter(
            filter_id="f-1",
            dataset=_DS,
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
            filter_id="f-1", dataset=_DS, column="posted_at",
        )
        assert isinstance(f, FilterLike)


class TestFullEmitRoundTripWithTypedFilters:
    """Replaces the placeholder above; threads through App.emit_analysis
    to confirm typed Filter wrappers serialize cleanly end-to-end."""

    def test_full_emit_round_trip(self):
        app = App(name="test", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
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
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        sheet.place(kpi, col_span=12, row_span=6, col_index=0)
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-sigma"),
            filters=[
                NumericRangeFilter(
                    filter_id="f-sigma",
                    dataset=_DS_FOO,
                    column="z_score",
                    minimum_parameter=sigma,
                ),
            ],
        ))
        fg.scope_visuals(sheet, [kpi])
        m = app.emit_analysis()
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
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="test", name="Test",
        ))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("sheet-test"),
            name="Test", title="Test", description="",
        ))
        kpi = sheet.add_visual(KPI(
            visual_id=VisualId("v-test"), title="Test",
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        sheet.place(kpi, col_span=12, row_span=6, col_index=0)
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-scoped"),
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        m = app.emit_analysis()
        j = m.to_aws_json()
        fgs = j["Definition"]["FilterGroups"]
        assert len(fgs) == 1
        assert fgs[0]["FilterGroupId"] == "fg-scoped"
        configs = fgs[0]["ScopeConfiguration"]["SelectedSheets"]["SheetVisualScopingConfigurations"]
        assert configs[0]["SheetId"] == "sheet-test"
        assert configs[0]["Scope"] == "SELECTED_VISUALS"
        assert configs[0]["VisualIds"] == ["v-test"]


# ---------------------------------------------------------------------------
# L.1.7 — Dataset tree nodes + dependency graph
# ---------------------------------------------------------------------------

class TestDataset:
    def test_emit_declaration(self):
        ds = Dataset(identifier="ds-foo", arn="arn:aws:quicksight:::dataset/foo")
        decl = ds.emit_declaration()
        assert decl.Identifier == "ds-foo"
        assert decl.DataSetArn == "arn:aws:quicksight:::dataset/foo"

    def test_dataset_is_hashable(self):
        """Dataset is the dependency-graph KEY — must be hashable so
        visuals/filters' refs can be collected into set[Dataset]."""
        a = Dataset(identifier="a", arn="arn:a")
        b = Dataset(identifier="b", arn="arn:b")
        s = {a, b, a}
        assert len(s) == 2

    def test_dim_carries_dataset_ref(self):
        """Hard-switch confirmation: Dim's dataset is the Dataset object,
        not the identifier string."""
        ds = Dataset(identifier="ds-foo", arn="arn:foo")
        dim = Dim(dataset=ds, field_id="f-1", column="col_a")
        assert dim.dataset is ds
        # emit() reads the identifier off the Dataset
        assert dim.emit().CategoricalDimensionField.Column.DataSetIdentifier == "ds-foo"

    def test_measure_carries_dataset_ref(self):
        ds = Dataset(identifier="ds-foo", arn="arn:foo")
        m = Measure.sum(ds, "amount", field_id="f")
        assert m.dataset is ds
        assert m.emit().NumericalMeasureField.Column.DataSetIdentifier == "ds-foo"


class TestAppDatasetRegistry:
    def test_add_dataset_returns_ref(self):
        app = App(name="test", cfg=_TEST_CFG)
        ds = app.add_dataset(_DS_FOO)
        assert ds is _DS_FOO
        assert _DS_FOO in app.datasets

    def test_duplicate_dataset_identifier_rejected(self):
        """Same shadow-bug class as duplicate parameters: two registrations
        sharing an identifier silently let one win at deploy."""
        app = App(name="test", cfg=_TEST_CFG)
        app.add_dataset(Dataset(identifier="ds-x", arn="arn:1"))
        with pytest.raises(ValueError, match="already registered"):
            app.add_dataset(Dataset(identifier="ds-x", arn="arn:2"))


class TestAppDatasetDependencies:
    """Walking the tree to extract the precise dataset dependency graph
    is the L.1.7 deployment-side-effect payoff. Selective deploy +
    matview REFRESH ordering both consume this graph."""

    def test_empty_when_no_analysis(self):
        app = App(name="test", cfg=_TEST_CFG)
        assert app.dataset_dependencies() == set()

    def test_collects_from_visuals(self):
        app = App(name="test", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        app.add_dataset(_DS_ANOMALIES)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-1"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v-foo"), title="From foo",
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v-anom"), title="From anomalies",
            values=[Measure.count(_DS_ANOMALIES, "id")],
        ))
        deps = app.dataset_dependencies()
        assert deps == {_DS_FOO, _DS_ANOMALIES}

    def test_collects_from_filter_groups(self):
        app = App(name="test", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-1"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
        ))  # No values; visual itself doesn't reference _DS_FOO
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-1"),
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
        ))
        fg.scope_visuals(sheet, [kpi])
        # Dependency comes via the filter group, not the visual.
        assert app.dataset_dependencies() == {_DS_FOO}

    def test_emit_analysis_rejects_unregistered_dataset(self):
        """The load-bearing validation: if a visual or filter references
        a Dataset that wasn't registered on the App, emit_analysis raises
        with the offending identifier(s)."""
        app = App(name="test", cfg=_TEST_CFG)
        # _DS_FOO is NOT registered on this app
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        with pytest.raises(ValueError, match="references unregistered datasets"):
            app.emit_analysis()

    def test_emit_analysis_includes_only_referenced_datasets(self):
        """Selective-by-construction: registered-but-unreferenced datasets
        DO NOT show up in the emitted DataSetIdentifierDeclarations.
        Catches dataset bloat at the deploy boundary."""
        app = App(name="test", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        app.add_dataset(_DS_ANOMALIES)  # registered but unreferenced
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        m = app.emit_analysis()
        decls = m.Definition.DataSetIdentifierDeclarations
        identifiers = {d.Identifier for d in decls}
        assert identifiers == {"ds-foo"}
        assert "ds-anomalies" not in identifiers

    def test_emit_dashboard_validates_references_too(self):
        app = App(name="test", cfg=_TEST_CFG)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        app.set_dashboard(Dashboard(
            dashboard_id_suffix="d", name="D", analysis=analysis,
        ))
        with pytest.raises(ValueError, match="references unregistered datasets"):
            app.emit_dashboard()


# ---------------------------------------------------------------------------
# L.1.8 — CalcField tree nodes
# ---------------------------------------------------------------------------

# Module-level CalcField fixture for the L.1.8 tests. Real apps construct
# CalcField nodes inside per-app builders; tests use a stand-in.
_CALC_IS_ANCHOR = None  # populated lazily inside tests so it can carry _DS_FOO


def _make_is_anchor() -> "CalcField":
    """A test-only calc field on _DS_FOO."""
    from quicksight_gen.common.tree import CalcField as _CF
    return _CF(
        name="is_anchor_edge",
        dataset=_DS_FOO,
        expression="ifelse({source} = ${pAnchor}, 'yes', 'no')",
    )


class TestCalcField:
    def test_emit_returns_dict(self):
        from quicksight_gen.common.tree import CalcField as _CF
        cf = _CF(
            name="my_calc", dataset=_DS_FOO, expression="1 + 1",
        )
        d = cf.emit()
        assert d == {
            "Name": "my_calc",
            "DataSetIdentifier": "ds-foo",
            "Expression": "1 + 1",
        }

    def test_calc_field_is_hashable(self):
        from quicksight_gen.common.tree import CalcField as _CF
        a = _CF(name="a", dataset=_DS_FOO, expression="1")
        b = _CF(name="b", dataset=_DS_FOO, expression="2")
        assert len({a, b, a}) == 2


class TestColumnRefAcceptsCalcField:
    """Dim / Measure / CategoryFilter / NumericRangeFilter / TimeRangeFilter
    accept either a string column name OR a CalcField object ref. The
    CalcField ref carries the calc-field identity through the type
    checker — typos at the wiring site become compile-time errors
    (or test-time failures via the unregistered-calc-field check)."""

    def test_dim_accepts_calc_field(self):
        cf = _make_is_anchor()
        dim = Dim(dataset=_DS_FOO, field_id="f-1", column=cf)
        # emit reads name off the calc field
        emitted = dim.emit()
        assert emitted.CategoricalDimensionField.Column.ColumnName == "is_anchor_edge"
        assert dim.calc_field() is cf

    def test_dim_accepts_bare_string(self):
        dim = Dim(dataset=_DS_FOO, field_id="f-1", column="real_column")
        emitted = dim.emit()
        assert emitted.CategoricalDimensionField.Column.ColumnName == "real_column"
        assert dim.calc_field() is None

    def test_measure_accepts_calc_field(self):
        cf = _make_is_anchor()
        m = Measure.count(_DS_FOO, cf, field_id="f-1")
        emitted = m.emit()
        assert emitted.CategoricalMeasureField.Column.ColumnName == "is_anchor_edge"
        assert m.calc_field() is cf

    def test_category_filter_accepts_calc_field(self):
        cf = _make_is_anchor()
        f = CategoryFilter(
            filter_id="f-1", dataset=_DS_FOO, column=cf, values=["yes"],
        )
        emitted = f.emit()
        assert emitted.CategoryFilter.Column.ColumnName == "is_anchor_edge"
        assert f.calc_field() is cf


class TestAnalysisAddCalcField:
    def test_add_calc_field_returns_ref(self):
        from quicksight_gen.common.tree import CalcField as _CF
        analysis = Analysis(analysis_id_suffix="t", name="T")
        cf = analysis.add_calc_field(_CF(
            name="my_calc", dataset=_DS_FOO, expression="1 + 1",
        ))
        assert cf in analysis.calc_fields

    def test_duplicate_name_rejected(self):
        from quicksight_gen.common.tree import CalcField as _CF
        analysis = Analysis(analysis_id_suffix="t", name="T")
        analysis.add_calc_field(_CF(
            name="dup", dataset=_DS_FOO, expression="1",
        ))
        with pytest.raises(ValueError, match="already on this Analysis"):
            analysis.add_calc_field(_CF(
                name="dup", dataset=_DS_FOO, expression="2",
            ))

    def test_emit_definition_carries_calc_fields(self):
        from quicksight_gen.common.tree import CalcField as _CF
        analysis = Analysis(analysis_id_suffix="t", name="T")
        analysis.add_calc_field(_CF(
            name="cf-1", dataset=_DS_FOO, expression="x",
        ))
        analysis.add_calc_field(_CF(
            name="cf-2", dataset=_DS_FOO, expression="y",
        ))
        defn = analysis.emit_definition(datasets=[_DS_FOO])
        assert len(defn.CalculatedFields) == 2
        assert defn.CalculatedFields[0]["Name"] == "cf-1"

    def test_no_calc_fields_emits_none(self):
        analysis = Analysis(analysis_id_suffix="t", name="T")
        defn = analysis.emit_definition(datasets=[])
        assert defn.CalculatedFields is None


class TestAppCalcFieldDependencies:
    """The L.1.8 dependency-graph extension: walk the tree to find
    every CalcField a visual or filter actually references."""

    def test_calc_fields_referenced_includes_visual_refs(self):
        cf = _make_is_anchor()
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="t", name="T",
        ))
        analysis.add_calc_field(cf)
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
            values=[Measure.count(_DS_FOO, cf)],
        ))
        # Tree walks the visual and finds the calc field ref.
        assert analysis.calc_fields_referenced() == {cf}

    def test_calc_fields_referenced_includes_filter_refs(self):
        cf = _make_is_anchor()
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="t", name="T",
        ))
        analysis.add_calc_field(cf)
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(visual_id=VisualId("v"), title="V"))
        analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg"),
            filters=[CategoryFilter(
                filter_id="f-1", dataset=_DS_FOO, column=cf, values=["yes"],
            )],
        )).scope_visuals(sheet, [kpi])
        assert analysis.calc_fields_referenced() == {cf}

    def test_emit_analysis_rejects_unregistered_calc_field(self):
        """The wrong-calc-field bug class — passing a CalcField that
        isn't registered on the Analysis. emit_analysis raises with
        the offending name."""
        cf = _make_is_anchor()  # NOT registered on the analysis
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="t", name="T",
        ))
        # Skip add_calc_field — the calc field is referenced but unregistered.
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
            values=[Measure.count(_DS_FOO, cf)],
        ))
        with pytest.raises(ValueError, match="references unregistered calc fields"):
            app.emit_analysis()

    def test_calc_field_dataset_in_dependency_graph(self):
        """A registered CalcField's Dataset participates in the App's
        dataset_dependencies — declaring a calc field on dataset D
        establishes D as a dep even when no visual touches D's columns."""
        from quicksight_gen.common.tree import CalcField as _CF
        cf = _CF(
            name="standalone_calc", dataset=_DS_ANOMALIES, expression="1",
        )
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        app.add_dataset(_DS_ANOMALIES)
        analysis = app.set_analysis(Analysis(
            analysis_id_suffix="t", name="T",
        ))
        analysis.add_calc_field(cf)
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        # KPI references _DS_FOO directly; calc field references _DS_ANOMALIES
        sheet.add_visual(KPI(
            visual_id=VisualId("v"), title="V",
            values=[Measure.sum(_DS_FOO, "amount", field_id="f-val")],
        ))
        deps = app.dataset_dependencies()
        # Both datasets show up — _DS_FOO from the visual, _DS_ANOMALIES
        # from the registered calc field.
        assert deps == {_DS_FOO, _DS_ANOMALIES}


# ---------------------------------------------------------------------------
# L.1.8.5 — Auto-IDs for internal IDs + tree-query helpers
# ---------------------------------------------------------------------------

class TestAutoVisualIds:
    """L.1.8.5: typed Visual subtypes get auto-IDs from their position in
    the tree when the user doesn't pass one explicitly."""

    def test_kpi_without_visual_id_gets_auto_id_at_emit(self):
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-test"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(
            title="Flagged",
            values=[Measure.count(_DS_FOO, "id")],
        ))
        # visual_id is None until emit-time resolution
        assert kpi.visual_id is None
        app.emit_analysis()
        # Now resolved
        assert kpi.visual_id == "v-kpi-s0-0"

    def test_explicit_visual_id_preserved(self):
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(
            visual_id=VisualId("v-special"),
            title="Special",
        ))
        app.emit_analysis()
        assert kpi.visual_id == "v-special"

    def test_mixed_explicit_and_auto(self):
        """Explicit IDs interleave with auto-IDs without conflict —
        auto-IDs use the position-indexed scheme, explicit ones pass
        through unchanged."""
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi_a = sheet.add_visual(KPI(title="A"))
        kpi_b = sheet.add_visual(KPI(title="B", visual_id=VisualId("v-special")))
        kpi_c = sheet.add_visual(KPI(title="C"))
        app.emit_analysis()
        assert kpi_a.visual_id == "v-kpi-s0-0"
        assert kpi_b.visual_id == "v-special"
        assert kpi_c.visual_id == "v-kpi-s0-2"

    def test_kind_prefix_distinguishes_visual_types(self):
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(title="K"))
        table = sheet.add_visual(Table(title="T"))
        bar = sheet.add_visual(BarChart(title="B"))
        sankey = sheet.add_visual(Sankey(title="S"))
        app.emit_analysis()
        assert kpi.visual_id == "v-kpi-s0-0"
        assert table.visual_id == "v-table-s0-1"
        assert bar.visual_id == "v-bar-s0-2"
        assert sankey.visual_id == "v-sankey-s0-3"

    def test_visual_id_is_sheet_scoped(self):
        """First visual on first sheet vs first visual on second sheet —
        position resets per sheet, scope encoded in the ID prefix."""
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet_a = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-a"), name="A", title="A", description="",
        ))
        sheet_b = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-b"), name="B", title="B", description="",
        ))
        kpi_a = sheet_a.add_visual(KPI(title="A0"))
        kpi_b = sheet_b.add_visual(KPI(title="B0"))
        app.emit_analysis()
        assert kpi_a.visual_id == "v-kpi-s0-0"
        assert kpi_b.visual_id == "v-kpi-s1-0"

    def test_factory_visual_node_still_requires_explicit_id(self):
        """The spike-shape VisualNode (factory wrapper) doesn't carry
        an _AUTO_KIND, so the auto-ID walk skips it. Authors must
        pass visual_id explicitly when using the factory pattern."""
        from quicksight_gen.common.models import (
            KPIConfiguration as _KPIC, KPIFieldWells as _KPIFW,
            KPIVisual as _KPIV,
        )
        from quicksight_gen.common.tree.visuals import VisualNode as _VN
        sheet = Sheet(sheet_id=SheetId("s"), name="S", title="S", description="")
        node = sheet.add_visual(_VN(
            visual_id=VisualId("v-factory-explicit"),
            builder=lambda: Visual(KPIVisual=_KPIV(
                VisualId="v-factory-explicit",
                ChartConfiguration=_KPIC(FieldWells=_KPIFW()),
            )),
        ))
        # Factory wrapper's visual_id is set explicitly; auto-ID walk
        # doesn't touch it (no _AUTO_KIND).
        assert node.visual_id == "v-factory-explicit"


class TestAutoFilterGroupIds:
    def test_filter_group_without_id_gets_auto_id(self):
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(title="K"))
        fg = analysis.add_filter_group(FilterGroup(
            filters=[_category_filter("f-1", _DS_FOO, "col")],
        ))
        fg.scope_visuals(sheet, [kpi])
        assert fg.filter_group_id is None
        app.emit_analysis()
        assert fg.filter_group_id == "fg-0"

    def test_explicit_filter_group_id_preserved(self):
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(title="K"))
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-special"),
            filters=[_category_filter("f-1", _DS_FOO, "col")],
        ))
        fg.scope_visuals(sheet, [kpi])
        app.emit_analysis()
        assert fg.filter_group_id == "fg-special"


class TestTreeQueryHelpers:
    """The L.1.8.5 introspection API. e2e tests + the dependency-graph
    walk consume these instead of importing per-app constants."""

    def _make_app(self) -> tuple[App, Sheet, KPI, Table, FilterGroup]:
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-anet"),
            name="Account Network", title="Account Network", description="",
        ))
        kpi = sheet.add_visual(KPI(title="Flagged Pair-Windows"))
        table = sheet.add_visual(Table(title="Account Network — Touching Edges"))
        fg = analysis.add_filter_group(FilterGroup(
            filter_group_id=FilterGroupId("fg-anchor"),
            filters=[_category_filter("f-1", _DS_FOO, "col_a")],
        ))
        fg.scope_visuals(sheet, [table])
        return app, sheet, kpi, table, fg

    def test_app_find_sheet_by_name(self):
        app, sheet, _, _, _ = self._make_app()
        found = app.find_sheet(name="Account Network")
        assert found is sheet

    def test_app_find_sheet_by_sheet_id(self):
        app, sheet, _, _, _ = self._make_app()
        found = app.find_sheet(sheet_id=SheetId("s-anet"))
        assert found is sheet

    def test_app_find_sheet_no_match_raises(self):
        app, _, _, _, _ = self._make_app()
        with pytest.raises(ValueError, match="No sheet"):
            app.find_sheet(name="Nonexistent")

    def test_sheet_find_visual_by_title(self):
        app, sheet, kpi, _, _ = self._make_app()
        found = sheet.find_visual(title="Flagged Pair-Windows")
        assert found is kpi

    def test_sheet_find_visual_by_partial_title(self):
        app, sheet, _, table, _ = self._make_app()
        found = sheet.find_visual(title_contains="Touching Edges")
        assert found is table

    def test_sheet_find_visual_no_match_raises(self):
        app, sheet, _, _, _ = self._make_app()
        with pytest.raises(ValueError, match="No visual"):
            sheet.find_visual(title="Doesn't Exist")

    def test_sheet_find_visual_multiple_matches_raises(self):
        """When the criteria are ambiguous, the helper raises rather
        than returning a non-deterministic match."""
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_visual(KPI(title="Same Title"))
        sheet.add_visual(KPI(title="Same Title"))
        with pytest.raises(ValueError, match="Multiple visuals"):
            sheet.find_visual(title="Same Title")

    def test_analysis_find_filter_group_by_id(self):
        app, _, _, _, fg = self._make_app()
        found = app.analysis.find_filter_group(filter_group_id=FilterGroupId("fg-anchor"))
        assert found is fg

    def test_analysis_find_calc_field_by_name(self):
        from quicksight_gen.common.tree import CalcField as _CF
        cf = _CF(name="my_calc", dataset=_DS_FOO, expression="1")
        analysis = Analysis(analysis_id_suffix="t", name="T")
        analysis.add_calc_field(cf)
        found = analysis.find_calc_field(name="my_calc")
        assert found is cf


# ---------------------------------------------------------------------------
# L.1.9 — Typed FilterControl + ParameterControl variants
# ---------------------------------------------------------------------------

from quicksight_gen.common.tree import (
    FilterCrossSheet,
    FilterDateTimePicker,
    FilterDropdown,
    FilterSlider,
    LinkedValues,
    ParameterDateTimePicker,
    ParameterDropdown,
    ParameterSlider,
    StaticValues,
)


class TestParameterDropdown:
    def test_emits_with_static_values(self):
        sigma = IntegerParam(name=ParameterName("pSigma"), default=[2])
        ctrl = ParameterDropdown(
            parameter=sigma,
            title="σ Threshold",
            type="SINGLE_SELECT",
            selectable_values=StaticValues(values=["1", "2", "3", "4"]),
            control_id="pc-test",
        )
        emitted = ctrl.emit()
        assert emitted.Dropdown.SourceParameterName == "pSigma"
        assert emitted.Dropdown.Title == "σ Threshold"
        assert emitted.Dropdown.Type == "SINGLE_SELECT"
        assert emitted.Dropdown.SelectableValues == {"Values": ["1", "2", "3", "4"]}

    def test_emits_with_linked_values(self):
        anchor = StringParam(name=ParameterName("pAnchor"))
        ctrl = ParameterDropdown(
            parameter=anchor,
            title="Anchor account",
            selectable_values=LinkedValues(dataset=_DS_FOO, column="display"),
            hidden_select_all=True,
            control_id="pc-anchor",
        )
        emitted = ctrl.emit()
        sv = emitted.Dropdown.SelectableValues
        assert sv == {
            "LinkToDataSetColumn": {
                "DataSetIdentifier": "ds-foo",
                "ColumnName": "display",
            },
        }
        # SelectAll suppression encodes as the documented dict shape
        assert emitted.Dropdown.DisplayOptions == {
            "SelectAllOptions": {"Visibility": "HIDDEN"},
        }

    def test_linked_values_dataset_in_dependency_graph(self):
        """A ParameterDropdown's LinkedValues dataset must be registered
        on the App — same enforcement the visuals get."""
        anchor = StringParam(name=ParameterName("pAnchor"))
        app = App(name="t", cfg=_TEST_CFG)
        # Don't register _DS_FOO — should raise.
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        analysis.add_parameter(anchor)
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        sheet.add_parameter_control(ParameterDropdown(
            parameter=anchor,
            title="Anchor",
            selectable_values=LinkedValues(dataset=_DS_FOO, column="d"),
        ))
        with pytest.raises(ValueError, match="references unregistered datasets"):
            app.emit_analysis()


class TestParameterSlider:
    def test_emits(self):
        sigma = IntegerParam(name=ParameterName("pSigma"), default=[2])
        ctrl = ParameterSlider(
            parameter=sigma,
            title="σ",
            minimum_value=1, maximum_value=4, step_size=1,
            control_id="pc-test",
        )
        emitted = ctrl.emit()
        assert emitted.Slider.SourceParameterName == "pSigma"
        assert emitted.Slider.MinimumValue == 1
        assert emitted.Slider.MaximumValue == 4
        assert emitted.Slider.StepSize == 1


class TestParameterDateTimePicker:
    def test_emits(self):
        date_param = DateTimeParam(name=ParameterName("pDate"))
        ctrl = ParameterDateTimePicker(
            parameter=date_param,
            title="Date",
            control_id="pc-date",
        )
        emitted = ctrl.emit()
        assert emitted.DateTimePicker.SourceParameterName == "pDate"
        assert emitted.DateTimePicker.Title == "Date"


class TestFilterDropdown:
    def test_emits_with_filter_id_resolved(self):
        f = CategoryFilter(
            filter_id="filter-anchor", dataset=_DS_FOO,
            column="col", values=["yes"],
        )
        ctrl = FilterDropdown(
            filter=f, title="Anchor",
            control_id="fc-anchor",
        )
        emitted = ctrl.emit()
        assert emitted.Dropdown.SourceFilterId == "filter-anchor"
        assert emitted.Dropdown.Title == "Anchor"

    def test_emits_with_auto_filter_id(self):
        """Filter wrapper's auto-ID resolves to a string — the dropdown
        reads it via the object ref. Tests the L.1.8.5 + L.1.9
        interaction."""
        f = CategoryFilter(
            dataset=_DS_FOO, column="col", values=["yes"],
        )  # no filter_id — auto
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(title="K"))
        fg = analysis.add_filter_group(FilterGroup(filters=[f]))
        fg.scope_visuals(sheet, [kpi])
        sheet.add_filter_control(FilterDropdown(filter=f, title="A"))
        app.emit_analysis()
        # Auto-IDs resolved
        assert f.filter_id == "f-category-fg0-0"
        # The dropdown picked it up
        assert sheet.filter_controls[0].emit().Dropdown.SourceFilterId == "f-category-fg0-0"


class TestFilterSlider:
    def test_emits(self):
        sigma_param = IntegerParam(name=ParameterName("pSigma"), default=[2])
        f = NumericRangeFilter(
            filter_id="filter-sigma",
            dataset=_DS_FOO, column="z_score",
            minimum_parameter=sigma_param,
        )
        ctrl = FilterSlider(
            filter=f, title="σ",
            minimum_value=1, maximum_value=4, step_size=1,
            control_id="fc-sigma",
        )
        emitted = ctrl.emit()
        assert emitted.Slider.SourceFilterId == "filter-sigma"


class TestFilterDateTimePicker:
    def test_emits(self):
        f = TimeRangeFilter(
            filter_id="filter-date",
            dataset=_DS_FOO, column="posted_at",
        )
        ctrl = FilterDateTimePicker(
            filter=f, title="Date Range",
            control_id="fc-date",
        )
        emitted = ctrl.emit()
        assert emitted.DateTimePicker.SourceFilterId == "filter-date"


class TestFilterCrossSheet:
    def test_emits_with_no_title(self):
        f = CategoryFilter(
            filter_id="filter-x", dataset=_DS_FOO,
            column="col", values=["yes"],
        )
        ctrl = FilterCrossSheet(filter=f, control_id="fc-x")
        emitted = ctrl.emit()
        assert emitted.CrossSheet.SourceFilterId == "filter-x"


class TestControlAutoIds:
    """L.1.9 + L.1.8.5: control IDs auto-generate at emit time."""

    def test_parameter_control_auto_id(self):
        sigma = IntegerParam(name=ParameterName("pSigma"), default=[2])
        app = App(name="t", cfg=_TEST_CFG)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        analysis.add_parameter(sigma)
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        ctrl = sheet.add_parameter_control(ParameterSlider(
            parameter=sigma, title="σ",
            minimum_value=1, maximum_value=4, step_size=1,
        ))
        assert ctrl.control_id is None
        app.emit_analysis()
        assert ctrl.control_id == "pc-slider-s0-0"

    def test_filter_control_auto_id(self):
        f = CategoryFilter(
            filter_id="filter-x", dataset=_DS_FOO,
            column="col", values=["yes"],
        )
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(title="K"))
        fg = analysis.add_filter_group(FilterGroup(filters=[f]))
        fg.scope_visuals(sheet, [kpi])
        ctrl = sheet.add_filter_control(FilterDropdown(filter=f, title="X"))
        assert ctrl.control_id is None
        app.emit_analysis()
        assert ctrl.control_id == "fc-dropdown-s0-0"


class TestSheetEmitsFilterControls:
    """SheetDefinition.FilterControls populated from sheet.filter_controls."""

    def test_filter_controls_appear_in_emitted_sheet(self):
        f = CategoryFilter(
            filter_id="filter-x", dataset=_DS_FOO,
            column="col", values=["yes"],
        )
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        kpi = sheet.add_visual(KPI(title="K"))
        fg = analysis.add_filter_group(FilterGroup(filters=[f]))
        fg.scope_visuals(sheet, [kpi])
        sheet.add_filter_control(FilterDropdown(
            filter=f, title="X", control_id="fc-x",
        ))
        m = app.emit_analysis()
        emitted_sheet = m.Definition.Sheets[0]
        assert len(emitted_sheet.FilterControls) == 1
        assert emitted_sheet.FilterControls[0].Dropdown.FilterControlId == "fc-x"


# ---------------------------------------------------------------------------
# L.1.10 — Typed Drill action
# ---------------------------------------------------------------------------

from quicksight_gen.common.dataset_contract import ColumnShape
from quicksight_gen.common.tree import Drill as TreeDrill
from quicksight_gen.common.tree import (
    DrillParam as TreeDrillParam,
)
from quicksight_gen.common.tree import (
    DrillSourceField as TreeDrillSourceField,
)


class TestDrillEmit:
    def _setup(self) -> tuple[App, Sheet, Sheet, Table]:
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        anchor = analysis.add_parameter(StringParam(
            name=ParameterName("pAnchor"),
        ))
        src_sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-source"),
            name="Source", title="Source", description="",
        ))
        dest_sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-dest"),
            name="Dest", title="Dest", description="",
        ))
        # Set up a table on the source sheet that has a drill action
        # targeting the dest sheet.
        table = src_sheet.add_visual(Table(
            title="Source Table",
            group_by=[Dim(dataset=_DS_FOO, field_id="f-acct", column="display")],
            actions=[TreeDrill(
                target_sheet=dest_sheet,  # OBJECT REF
                writes=[(
                    TreeDrillParam(ParameterName("pAnchor"), ColumnShape.ACCOUNT_DISPLAY),
                    TreeDrillSourceField(field_id="f-acct", shape=ColumnShape.ACCOUNT_DISPLAY),
                )],
                name="Walk to anchor",
                trigger="DATA_POINT_MENU",
            )],
        ))
        src_sheet.place(table, col_span=36, row_span=18, col_index=0)
        return app, src_sheet, dest_sheet, table

    def test_drill_emits_with_target_sheet_resolved(self):
        app, _, dest_sheet, table = self._setup()
        m = app.emit_analysis()
        # Find the source sheet in the emitted JSON
        emitted_src = m.Definition.Sheets[0]
        emitted_table = emitted_src.Visuals[0].TableVisual
        actions = emitted_table.Actions
        assert len(actions) == 1
        action = actions[0]
        assert action.Name == "Walk to anchor"
        assert action.Trigger == "DATA_POINT_MENU"
        # NavigationOperation should have the dest sheet's id
        nav = action.ActionOperations[0].NavigationOperation
        assert nav.LocalNavigationConfiguration.TargetSheetId == "s-dest"

    def test_drill_action_id_auto_assigned(self):
        app, _, _, table = self._setup()
        action = table.actions[0]
        assert action.action_id is None
        app.emit_analysis()
        # auto-IDed: act-s{sheet_idx}-v{visual_idx}-{action_idx}
        assert action.action_id == "act-s0-v0-0"

    def test_drill_target_sheet_must_be_registered(self):
        """Drill into a sheet that isn't on the analysis raises at
        emit time. Catches the wrong-sheet bug class — the typed
        ref means the Sheet must be a real, registered Sheet object."""
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        src_sheet = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s-src"),
            name="Source", title="Source", description="",
        ))
        # An UNregistered sheet — never goes through analysis.add_sheet
        rogue_sheet = Sheet(
            sheet_id=SheetId("s-rogue"),
            name="Rogue", title="Rogue", description="",
        )
        table = src_sheet.add_visual(Table(
            title="X",
            actions=[TreeDrill(
                target_sheet=rogue_sheet,  # not on the analysis!
                writes=[(
                    TreeDrillParam(ParameterName("pX"), ColumnShape.ACCOUNT_ID),
                    TreeDrillSourceField(field_id="f", shape=ColumnShape.ACCOUNT_ID),
                )],
                name="Bad drill",
            )],
        ))
        src_sheet.place(table, col_span=36, row_span=18, col_index=0)
        with pytest.raises(ValueError, match="drill actions targeting sheets"):
            app.emit_analysis()

    def test_explicit_action_id_preserved(self):
        app = App(name="t", cfg=_TEST_CFG)
        app.add_dataset(_DS_FOO)
        analysis = app.set_analysis(Analysis(analysis_id_suffix="t", name="T"))
        src = analysis.add_sheet(Sheet(
            sheet_id=SheetId("s"), name="S", title="S", description="",
        ))
        table = src.add_visual(Table(
            title="T",
            actions=[TreeDrill(
                target_sheet=src,  # same sheet — also valid
                writes=[(
                    TreeDrillParam(ParameterName("pX"), ColumnShape.ACCOUNT_ID),
                    TreeDrillSourceField(field_id="f", shape=ColumnShape.ACCOUNT_ID),
                )],
                name="Drill",
                action_id="my-explicit-id",
            )],
        ))
        src.place(table, col_span=36, row_span=18, col_index=0)
        app.emit_analysis()
        assert table.actions[0].action_id == "my-explicit-id"
