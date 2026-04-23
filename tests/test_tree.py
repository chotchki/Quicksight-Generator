"""Unit tests for the L.1 tree primitives in ``common/tree.py``.

L.1.2 coverage: structural types (App / Dashboard / Analysis / Sheet),
GridSlot placement validation, emit() round-trip into models.py.

L.1.3+ coverage joins as each sub-step lands.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId, VisualId
from quicksight_gen.common.models import (
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    Visual,
)
from quicksight_gen.common.tree import (
    Analysis,
    App,
    Dashboard,
    GridSlot,
    ParameterControlNode,
    Sheet,
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
