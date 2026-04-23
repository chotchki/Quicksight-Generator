"""Unit tests for the L.1.10.6 kitchen-sink app.

These tests confirm the kitchen-sink builds + emits cleanly + actually
contains every typed L.1 primitive at least once. Real e2e (deploy +
TreeValidator browser walk) lands when L.2's tree-to-files bridging
exists; until then these tests guard the "the kitchen-sink is
complete coverage" property at the unit level.

If a future commit adds a new typed primitive (say a new Visual
subtype) and forgets to wire it into the kitchen-sink, the
"every primitive present" assertions here fail loud.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.config import Config
from tests.e2e._kitchen_app import build_kitchen_app


_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


@pytest.fixture
def kitchen_app():
    return build_kitchen_app(_CFG)


@pytest.fixture
def emitted(kitchen_app):
    """The full models.Analysis instance from the kitchen-sink."""
    return kitchen_app.emit_analysis()


@pytest.fixture
def emitted_dashboard(kitchen_app):
    return kitchen_app.emit_dashboard()


class TestKitchenAppBuilds:
    def test_emit_analysis_succeeds(self, kitchen_app):
        """Validates the App's resolve_auto_ids + dataset / calc-field /
        drill-destination checks all pass on the kitchen-sink. If a
        typed primitive added later breaks one of these, this test
        fires."""
        kitchen_app.emit_analysis()  # doesn't raise

    def test_emit_dashboard_succeeds(self, kitchen_app):
        kitchen_app.emit_dashboard()  # doesn't raise


class TestEveryVisualKindPresent:
    """Walking the emitted Analysis must surface every typed Visual
    subtype at least once."""

    def _visual_kinds(self, emitted) -> set[str]:
        kinds: set[str] = set()
        for sheet in emitted.Definition.Sheets:
            for visual in (sheet.Visuals or []):
                if visual.KPIVisual is not None:
                    kinds.add("kpi")
                if visual.TableVisual is not None:
                    kinds.add("table")
                if visual.BarChartVisual is not None:
                    kinds.add("bar")
                if visual.SankeyDiagramVisual is not None:
                    kinds.add("sankey")
        return kinds

    def test_all_four_visual_kinds_present(self, emitted):
        assert self._visual_kinds(emitted) >= {"kpi", "table", "bar", "sankey"}


class TestEveryFilterKindPresent:
    def _filter_kinds(self, emitted) -> set[str]:
        kinds: set[str] = set()
        for fg in emitted.Definition.FilterGroups or []:
            for f in fg.Filters or []:
                if f.CategoryFilter is not None:
                    kinds.add("category")
                if f.NumericRangeFilter is not None:
                    kinds.add("numeric_range")
                if f.TimeRangeFilter is not None:
                    kinds.add("time_range")
        return kinds

    def test_all_three_filter_kinds_present(self, emitted):
        assert self._filter_kinds(emitted) >= {
            "category", "numeric_range", "time_range",
        }


class TestEveryParameterKindPresent:
    def _param_kinds(self, emitted) -> set[str]:
        kinds: set[str] = set()
        for p in emitted.Definition.ParameterDeclarations or []:
            if p.StringParameterDeclaration is not None:
                kinds.add("string")
            if p.IntegerParameterDeclaration is not None:
                kinds.add("integer")
            if p.DateTimeParameterDeclaration is not None:
                kinds.add("datetime")
        return kinds

    def test_all_three_parameter_kinds_present(self, emitted):
        assert self._param_kinds(emitted) >= {"string", "integer", "datetime"}


class TestEveryControlKindPresent:
    def _control_kinds(self, emitted) -> tuple[set[str], set[str]]:
        param_kinds: set[str] = set()
        filter_kinds: set[str] = set()
        for sheet in emitted.Definition.Sheets:
            for ctrl in (sheet.ParameterControls or []):
                if ctrl.Dropdown is not None:
                    param_kinds.add("dropdown")
                if ctrl.Slider is not None:
                    param_kinds.add("slider")
                if ctrl.DateTimePicker is not None:
                    param_kinds.add("datetime")
            for ctrl in (sheet.FilterControls or []):
                if ctrl.Dropdown is not None:
                    filter_kinds.add("dropdown")
                if ctrl.Slider is not None:
                    filter_kinds.add("slider")
                if ctrl.DateTimePicker is not None:
                    filter_kinds.add("datetime")
                if ctrl.CrossSheet is not None:
                    filter_kinds.add("crosssheet")
        return param_kinds, filter_kinds

    def test_every_parameter_control_kind_present(self, emitted):
        param_kinds, _ = self._control_kinds(emitted)
        assert param_kinds >= {"dropdown", "slider", "datetime"}

    def test_every_filter_control_kind_present(self, emitted):
        _, filter_kinds = self._control_kinds(emitted)
        assert filter_kinds >= {"dropdown", "slider", "datetime", "crosssheet"}


class TestStaticAndLinkedDropdownValues:
    """Both StaticValues and LinkedValues SelectableValues shapes appear."""

    def test_both_selectable_value_kinds_present(self, emitted):
        seen_static = False
        seen_linked = False
        for sheet in emitted.Definition.Sheets:
            for ctrl in (sheet.ParameterControls or []):
                if ctrl.Dropdown is None or ctrl.Dropdown.SelectableValues is None:
                    continue
                sv = ctrl.Dropdown.SelectableValues
                if "Values" in sv:
                    seen_static = True
                if "LinkToDataSetColumn" in sv:
                    seen_linked = True
        assert seen_static, "kitchen-sink missing a StaticValues dropdown"
        assert seen_linked, "kitchen-sink missing a LinkedValues dropdown"


class TestDrillActionsPresent:
    """Every triggerable visual kind that supports Actions has at least
    one drill wired to a non-self destination."""

    def _drills(self, emitted) -> list[tuple[str, str, str]]:
        """(visual_kind, action_name, target_sheet_id) triples."""
        drills: list[tuple[str, str, str]] = []
        for sheet in emitted.Definition.Sheets:
            for visual in (sheet.Visuals or []):
                for kind, vis in (
                    ("table", visual.TableVisual),
                    ("bar", visual.BarChartVisual),
                    ("sankey", visual.SankeyDiagramVisual),
                ):
                    if vis is None or not vis.Actions:
                        continue
                    for a in vis.Actions:
                        nav = a.ActionOperations[0].NavigationOperation
                        target = nav.LocalNavigationConfiguration.TargetSheetId
                        drills.append((kind, a.Name, target))
        return drills

    def test_drill_actions_on_table_bar_sankey(self, emitted):
        kinds = {kind for kind, _, _ in self._drills(emitted)}
        assert kinds >= {"table", "bar", "sankey"}, (
            f"Expected drill actions on table + bar + sankey; got {kinds}"
        )

    def test_drill_targets_resolve_to_real_sheet(self, emitted):
        sheet_ids = {s.SheetId for s in emitted.Definition.Sheets}
        for kind, name, target in self._drills(emitted):
            assert target in sheet_ids, (
                f"Drill {name!r} on {kind} → unknown sheet {target!r}"
            )

    def test_kpi_has_no_actions(self, emitted):
        """KPI doesn't carry Actions in the QuickSight model — typed
        KPI subtype omits the field. If anyone ever adds it, this
        test reminds them to verify the model supports it."""
        for sheet in emitted.Definition.Sheets:
            for visual in (sheet.Visuals or []):
                if visual.KPIVisual is not None:
                    # KPIVisual model should not have Actions attr at all
                    assert not hasattr(visual.KPIVisual, "Actions") or (
                        getattr(visual.KPIVisual, "Actions", None) is None
                    )


class TestCalcFieldsAndDatasets:
    def test_calc_field_present(self, emitted):
        names = [
            c["Name"] for c in (emitted.Definition.CalculatedFields or [])
        ]
        assert "is_above_threshold" in names

    def test_both_datasets_declared(self, emitted):
        ids = {
            d.Identifier
            for d in emitted.Definition.DataSetIdentifierDeclarations
        }
        assert ids >= {"kitchen-main-ds", "kitchen-categories-ds"}

    def test_dependency_graph_includes_both_datasets(self, kitchen_app):
        """LinkedValues + visual + calc field + filter all reference
        datasets — App.dataset_dependencies should surface both."""
        deps = kitchen_app.dataset_dependencies()
        ids = {d.identifier for d in deps}
        assert ids >= {"kitchen-main-ds", "kitchen-categories-ds"}
