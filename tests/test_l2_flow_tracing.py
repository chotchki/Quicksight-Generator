"""Tests for the L2 Flow Tracing app — phase M.3.4 skeleton.

The L2 Flow Tracing app is the second L2-fed app (after L1 dashboard).
Its job is to make every L2 primitive observable on a runtime
dashboard so analysts (and integrators) can spot 'L2 hygiene'
problems — declared rails with zero activity, declared chains with
broken parent-child firing, declared LimitSchedules that no flow
ever exercises.

M.3.4 ships the skeleton: 4 sheets (Getting Started + Rails +
Chains + L2 Exceptions), description-driven prose on Getting
Started, placeholder TextBox content on the other three sheets.
M.3.5+ populates each tab with its real visuals + datasets.

Tests here cover:

- Build pipeline shape (cfg + l2_instance plumb through).
- Analysis + Dashboard emit cleanly with the M.2d.3 prefix pattern.
- Default L2 instance auto-loads the persona-neutral spec_example
  fixture (M.3.2 repoint — production library code carries no
  Sasquatch flavor).
- 4 sheets in display order match the M.3.4 spec.
- Getting Started welcome uses ``l2_instance.description`` as the
  body (description-driven prose contract).
- M.3.4 CLI smoke: ``quicksight-gen generate l2-flow-tracing``
  writes the expected files.
- ``--all`` includes l2-flow-tracing in the bundle.
- Per-instance prefix isolation: changing the L2 instance changes
  the analysis ID + dashboard ID middle segment.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.l2_flow_tracing.app import (
    build_l2_flow_tracing_app,
)
from quicksight_gen.cli import APP_CHOICE, APPS, main
from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance, load_instance


_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


SASQUATCH_PR_YAML = (
    Path(__file__).parent / "l2" / "sasquatch_pr.yaml"
)


def _sheet_by_name(app, name: str):
    """Look up a Sheet by display name. Position-agnostic so sheet
    insertion order can be reshuffled without re-keying these tests."""
    assert app.analysis is not None
    for s in app.analysis.sheets:
        if s.name == name:
            return s
    raise AssertionError(
        f"sheet {name!r} missing — found {[s.name for s in app.analysis.sheets]}"
    )


# -- Build pipeline ----------------------------------------------------------


def test_build_with_default_loads_spec_example() -> None:
    """No kwarg → auto-load the persona-neutral spec_example L2 fixture
    (M.3.2 repointed default; production library code carries no
    implicit Sasquatch flavor)."""
    app = build_l2_flow_tracing_app(_CFG)
    assert app is not None
    assert app.name == "l2-flow-tracing"


def test_build_with_explicit_l2_instance_uses_caller_value() -> None:
    """Caller-supplied instance overrides the default."""
    explicit = default_l2_instance()
    app = build_l2_flow_tracing_app(_CFG, l2_instance=explicit)
    assert app is not None


def test_build_signature_l2_instance_is_kwarg_only() -> None:
    """Same convention as build_l1_dashboard_app: positional callers
    keep working without passing l2_instance; tests + alternative-persona
    deployments override via the kwarg."""
    sig = inspect.signature(build_l2_flow_tracing_app)
    p = sig.parameters.get("l2_instance")
    assert p is not None
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
    assert p.default is None
    annot_str = str(p.annotation)
    assert "L2Instance" in annot_str


# -- Analysis + Dashboard registration ---------------------------------------


def test_analysis_registered_with_l2_aware_name() -> None:
    """The Analysis title surfaces the L2 prefix so multi-instance
    deployments are distinguishable in the QuickSight UI."""
    app = build_l2_flow_tracing_app(_CFG)
    assert app.analysis is not None
    assert "spec_example" in app.analysis.name
    assert "L2 Flow Tracing" in app.analysis.name


def test_dashboard_registered() -> None:
    app = build_l2_flow_tracing_app(_CFG)
    assert app.dashboard is not None


def test_emit_analysis_and_dashboard_succeed() -> None:
    """Tree validation passes — no orphan refs / shape errors."""
    app = build_l2_flow_tracing_app(_CFG)
    analysis = app.emit_analysis()
    dashboard = app.emit_dashboard()
    assert analysis is not None
    assert dashboard is not None


def test_analysis_id_uses_l2_instance_prefix() -> None:
    """M.2d.3 prefix pattern: ``<resource_prefix>-<l2_prefix>-l2-flow-tracing-analysis``.
    Default L2 instance is spec_example."""
    app = build_l2_flow_tracing_app(_CFG)
    analysis = app.emit_analysis()
    assert analysis.AnalysisId == (
        "qs-gen-spec_example-l2-flow-tracing-analysis"
    )


def test_dashboard_id_uses_l2_instance_prefix() -> None:
    app = build_l2_flow_tracing_app(_CFG)
    dashboard = app.emit_dashboard()
    assert dashboard.DashboardId == (
        "qs-gen-spec_example-l2-flow-tracing"
    )


def test_per_instance_prefix_isolates_resource_ids() -> None:
    """Two L2 instances → two non-colliding analysis IDs. Prevents
    multi-instance deploy collisions in the same QS account."""
    spec_inst = default_l2_instance()
    sasquatch_pr_inst = load_instance(SASQUATCH_PR_YAML)

    spec_app = build_l2_flow_tracing_app(_CFG, l2_instance=spec_inst)
    sasq_app = build_l2_flow_tracing_app(_CFG, l2_instance=sasquatch_pr_inst)

    spec_analysis_id = spec_app.emit_analysis().AnalysisId
    sasq_analysis_id = sasq_app.emit_analysis().AnalysisId
    assert spec_analysis_id != sasq_analysis_id
    assert "spec_example" in spec_analysis_id
    assert "sasquatch_pr" in sasq_analysis_id


# -- Sheet structure (M.3.4 — 4 sheets) --------------------------------------


def test_four_sheets_in_display_order() -> None:
    """M.3.4 spec: Getting Started + Rails + Chains + L2 Exceptions.
    Position-stable — the order matches the spec."""
    app = build_l2_flow_tracing_app(_CFG)
    assert app.analysis is not None
    assert [s.name for s in app.analysis.sheets] == [
        "Getting Started", "Rails", "Chains", "L2 Exceptions",
    ]


def test_every_sheet_has_a_description() -> None:
    """Subtitle text drives the per-sheet prose — every sheet must
    have one (description-driven-prose contract from M.2a.7)."""
    app = build_l2_flow_tracing_app(_CFG)
    for s in app.analysis.sheets:
        assert s.description, f"sheet {s.name!r} missing description"


def test_every_sheet_has_at_least_one_text_box() -> None:
    """Skeleton invariant: every sheet renders at least the
    description prose. Removed when M.3.5+ replaces the placeholders
    with real visuals."""
    app = build_l2_flow_tracing_app(_CFG)
    for s in app.analysis.sheets:
        assert len(s.text_boxes) >= 1, (
            f"sheet {s.name!r} has no text_boxes — placeholder missing?"
        )


def test_skeleton_has_zero_datasets() -> None:
    """M.3.4 ships zero datasets. M.3.5+ populates them."""
    app = build_l2_flow_tracing_app(_CFG)
    assert app.datasets == []


# -- Getting Started — description-driven prose (M.2a.2 contract) ------------


def test_getting_started_welcome_uses_l2_instance_description() -> None:
    """The welcome body comes from ``l2_instance.description``, NOT a
    hardcoded persona string. Switching L2 instance switches the
    prose — same contract the L1 dashboard's Getting Started follows."""
    app = build_l2_flow_tracing_app(_CFG)
    gs = _sheet_by_name(app, "Getting Started")
    welcome_xml = gs.text_boxes[0].content
    # Default L2 instance is spec_example — its description is what shows.
    assert "Generic SPEC-shaped instance" in welcome_xml


def test_getting_started_welcome_falls_back_when_l2_description_missing() -> None:
    """If the L2 instance has no top-level description, surface a
    hint to fill it rather than rendering blank — quicker debug."""
    from dataclasses import replace
    explicit = default_l2_instance()
    minimal = replace(explicit, description=None)
    app = build_l2_flow_tracing_app(_CFG, l2_instance=minimal)
    gs = _sheet_by_name(app, "Getting Started")
    assert "L2 instance description missing" in gs.text_boxes[0].content


def test_getting_started_title_is_constant_ui_vocabulary() -> None:
    """The title 'L2 Flow Tracing' is constant UI vocabulary (NOT
    pulled from L2). Per the M.2a.4 design note: titles stay
    hardcoded, subtitles + bodies pull from L2 descriptions."""
    app = build_l2_flow_tracing_app(_CFG)
    gs = _sheet_by_name(app, "Getting Started")
    assert "L2 Flow Tracing" in gs.text_boxes[0].content


# -- Placeholder sheets — substep pointers (removed when populated) ----------


@pytest.mark.parametrize(
    "sheet_name,substep",
    [
        ("Rails", "M.3.5"),
        ("Chains", "M.3.6"),
        ("L2 Exceptions", "M.3.7"),
    ],
)
def test_placeholder_sheets_point_to_their_substep(
    sheet_name: str, substep: str,
) -> None:
    """Each placeholder TextBox names the substep that will replace it,
    so the next agent on this app sees a clear pointer to the next
    work item."""
    app = build_l2_flow_tracing_app(_CFG)
    sheet = _sheet_by_name(app, sheet_name)
    body = sheet.text_boxes[0].content
    assert f"M.3.4" in body  # documents that this is the skeleton
    assert substep in body, (
        f"sheet {sheet_name!r} placeholder doesn't point at {substep}"
    )


# -- CLI plumbing ------------------------------------------------------------


def test_l2_flow_tracing_in_apps_tuple() -> None:
    """CLI's APPS tuple drives `--all` + the deploy block. Missing here
    means `generate --all` would skip l2-flow-tracing silently."""
    assert "l2-flow-tracing" in APPS


def test_l2_flow_tracing_in_app_choice() -> None:
    """Click's APP_CHOICE drives positional argument validation for
    deploy + cleanup. Missing here means `deploy l2-flow-tracing`
    fails with 'invalid choice'."""
    assert "l2-flow-tracing" in APP_CHOICE.choices


def test_cli_generate_l2_flow_tracing_writes_files(tmp_path: Path) -> None:
    """M.3.4 CLI smoke: `quicksight-gen generate l2-flow-tracing`
    writes theme + analysis + dashboard. No datasets dir at the
    skeleton (datasets land at M.3.5+)."""
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "aws_account_id: '111122223333'\n"
        "aws_region: us-west-2\n"
        "theme_preset: default\n"
        "datasource_arn: 'arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds'\n"
    )
    out_dir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(
        main, [
            "generate",
            "-c", str(cfg_path),
            "-o", str(out_dir),
            "l2-flow-tracing",
        ],
    )
    assert result.exit_code == 0, result.output
    assert (out_dir / "theme.json").exists()
    assert (out_dir / "l2-flow-tracing-analysis.json").exists()
    assert (out_dir / "l2-flow-tracing-dashboard.json").exists()
