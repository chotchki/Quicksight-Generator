"""Y.2.app2.cde.l2ft-wiring.b — ``make_filter_specs_for_sheet`` tests.

Locks the tree-walk → App2 ``FilterSpec`` derivation: a MULTI_SELECT
``ParameterDropdown`` whose ``selectable_values`` is a ``StaticValues``
becomes a ``ParameterMultiSelectSpec``; SINGLE_SELECT dropdowns, sliders,
and ``LinkedValues`` dropdowns are skipped (App2 either can't replicate the
QS cascade-refresh-options behaviour or would have to query to enumerate).
"""

from __future__ import annotations

from quicksight_gen.common.html import (
    ParameterMultiSelectSpec,
    make_filter_specs_for_sheet,
)
from quicksight_gen.common.ids import ParameterName, SheetId
from quicksight_gen.common.tree import (
    Analysis,
    App,
    IntegerParam,
    Sheet,
    StaticValues,
    StringParam,
)
from tests._test_helpers import make_test_config


def _sheet_with_controls() -> Sheet:
    app = App(name="ft-specs-test", cfg=make_test_config())
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="ft-specs-analysis", name="FT Specs",
    ))
    sheet = analysis.add_sheet(Sheet(
        sheet_id=SheetId("ft-specs-sheet"), name="FT", title="FT", description="x",
    ))
    # A MULTI_SELECT StaticValues dropdown — should become a spec.
    p_rail = analysis.add_parameter(StringParam(
        name=ParameterName("pL2ftRail"), multi_valued=True,
        default=["ach", "wire", "check"],
    ))
    sheet.add_parameter_dropdown(
        parameter=p_rail, title="Rail", type="MULTI_SELECT",
        selectable_values=StaticValues(values=["ach", "wire", "check"]),
    )
    # A SINGLE_SELECT StaticValues dropdown — should be skipped.
    p_key = analysis.add_parameter(StringParam(name=ParameterName("pKey")))
    sheet.add_parameter_dropdown(
        parameter=p_key, title="Metadata Key",
        selectable_values=StaticValues(values=["__ALL__", "memo_kind"]),
    )
    # A slider — should be skipped (not a ParameterDropdown).
    p_n = analysis.add_parameter(IntegerParam(name=ParameterName("pThreshold")))
    sheet.add_parameter_slider(
        parameter=p_n, title="Threshold",
        minimum_value=1, maximum_value=10, step_size=1,
    )
    return sheet


def test_make_filter_specs_returns_one_per_multiselect_static_dropdown() -> None:
    sheet = _sheet_with_controls()
    specs = make_filter_specs_for_sheet(sheet)
    assert len(specs) == 1
    (spec,) = specs
    assert isinstance(spec, ParameterMultiSelectSpec)
    assert spec.name == "pL2ftRail"
    assert spec.label == "Rail"
    assert spec.options == ("ach", "wire", "check")


def test_make_filter_specs_skips_single_select_and_sliders() -> None:
    """The hand-built sheet has a SINGLE_SELECT dropdown + a slider on top
    of the MULTI_SELECT one — only the MULTI_SELECT survives."""
    sheet = _sheet_with_controls()
    specs = make_filter_specs_for_sheet(sheet)
    names = {s.name for s in specs if isinstance(s, ParameterMultiSelectSpec)}
    assert names == {"pL2ftRail"}
    assert all("pKey" not in s.name and "pThreshold" not in s.name for s in specs)


def test_make_filter_specs_empty_for_sheet_with_no_parameter_controls() -> None:
    app = App(name="ft-empty-test", cfg=make_test_config())
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="ft-empty-analysis", name="FT Empty",
    ))
    sheet = analysis.add_sheet(Sheet(
        sheet_id=SheetId("ft-empty-sheet"), name="FT", title="FT", description="x",
    ))
    assert make_filter_specs_for_sheet(sheet) == []


# --- Integration: the real L2FT Rails sheet has rail/status/bundle MULTI_SELECTs ---

def test_l2ft_rails_sheet_auto_derives_three_multiselect_specs() -> None:
    """The Rails sheet's filter bar is Date From/To + Rail/Status/Bundle
    (MULTI_SELECT pushdown dropdowns) + a SINGLE_SELECT metadata-key
    cascade dropdown. Only the 3 MULTI_SELECTs become App2 filter specs."""
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.apps.l2_flow_tracing.app import build_l2_flow_tracing_app
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_all_l2_flow_tracing_datasets,
    )

    inst = default_l2_instance()
    cfg = make_test_config().with_l2_instance_prefix(str(inst.instance))
    build_all_l2_flow_tracing_datasets(cfg, inst)
    tree_app = build_l2_flow_tracing_app(cfg, l2_instance=inst)
    assert tree_app.analysis is not None
    rails_sheet = next(
        s for s in tree_app.analysis.sheets if s.name == "Rails"
    )
    specs = make_filter_specs_for_sheet(rails_sheet)
    names = [s.name for s in specs if isinstance(s, ParameterMultiSelectSpec)]
    assert names == ["pL2ftRail", "pL2ftStatus", "pL2ftBundle"]
    # Each carries a non-empty option list (the L2-derived closed set).
    for spec in specs:
        assert isinstance(spec, ParameterMultiSelectSpec)
        assert len(spec.options) >= 1
