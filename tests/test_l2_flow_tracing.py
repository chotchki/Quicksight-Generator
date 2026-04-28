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


def test_dataset_count_matches_populated_sheets() -> None:
    """M.3.5 ships the Rails dataset (1 total). Each subsequent populator
    substep grows this assertion (M.3.6 → 2, M.3.7 → 8 etc.). Re-key
    when a new tab populator lands."""
    app = build_l2_flow_tracing_app(_CFG)
    assert len(app.datasets) == 1
    assert {d.identifier for d in app.datasets} == {"l2ft-rails-ds"}


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
        ("Chains", "M.3.6"),
        ("L2 Exceptions", "M.3.7"),
    ],
)
def test_placeholder_sheets_point_to_their_substep(
    sheet_name: str, substep: str,
) -> None:
    """Each remaining placeholder TextBox names the substep that will
    replace it, so the next agent on this app sees a clear pointer to
    the next work item. Drop the parametrize entry as each substep
    populator lands (M.3.5 dropped 'Rails')."""
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
    writes theme + analysis + dashboard. M.3.5 adds the Rails dataset
    JSON under datasets/."""
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
    # M.3.5 — Rails dataset JSON lands under datasets/
    rails_dataset_json = (
        out_dir / "datasets" / "qs-gen-spec_example-l2ft-rails-dataset.json"
    )
    assert rails_dataset_json.exists()


# -- Rails sheet (M.3.5) -----------------------------------------------------


def _rails_dataset_sql(app) -> str:
    """Pull the SQL string out of the registered Rails dataset's underlying
    AWS DataSet — the tree's Dataset node is just a ref so we have to
    re-build via the dataset module to read SQL."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_rails_dataset,
    )
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    aws_ds = build_rails_dataset(_CFG, default_l2_instance())
    table = list(aws_ds.PhysicalTableMap.values())[0]
    return table.CustomSql.SqlQuery


def test_rails_dataset_targets_prefixed_current_transactions(
) -> None:
    """The runtime aggregate joins the prefixed current_transactions
    matview — `<prefix>_current_transactions`. Using current_* keeps
    the dataset supersession-aware (one Money record = the latest
    entry per id)."""
    sql = _rails_dataset_sql(None)
    assert "FROM spec_example_current_transactions" in sql


def test_rails_dataset_inlines_l2_rail_declarations() -> None:
    """The static columns come from a CTE of L2-declared rail rows.
    With spec_example.yaml's 4 rails, the CTE has 4 SELECT-literal rows
    joined by 3 UNION ALLs."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    inst = default_l2_instance()
    sql = _rails_dataset_sql(None)
    assert "WITH declared AS" in sql
    # Each rail name appears as a SQL string literal in the CTE.
    for rail in inst.rails:
        assert f"'{rail.name}'" in sql, (
            f"rail {rail.name!r} not inlined in the CTE"
        )
    # N rails → N-1 UNION ALLs in the CTE.
    assert sql.count("UNION ALL") == max(0, len(inst.rails) - 1)


def test_rails_dataset_left_joins_runtime_to_keep_dead_rails() -> None:
    """A LEFT JOIN preserves Rails with zero activity (those become
    L2.3 'Dead rails' rows on the Exceptions tab). An INNER JOIN here
    would silently hide them."""
    sql = _rails_dataset_sql(None)
    assert "LEFT JOIN runtime" in sql
    # COALESCE guarantees runtime nulls render as 0 in the visual.
    assert "COALESCE(r.total_postings, 0)" in sql


def test_rails_dataset_contract_columns_match_builder() -> None:
    """Contract columns and SQL projection match — visual ds["col"]
    references resolve cleanly."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        RAILS_CONTRACT, build_rails_dataset,
    )
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    aws_ds = build_rails_dataset(_CFG, default_l2_instance())
    cols = {
        c.Name for c in list(aws_ds.PhysicalTableMap.values())[0].CustomSql.Columns
    }
    expected = {c.name for c in RAILS_CONTRACT.columns}
    assert cols == expected


def test_rails_dataset_id_uses_l2_instance_prefix() -> None:
    """Per M.2d.3 — dataset ID middle segment is the L2 instance
    prefix so multi-instance deploys don't collide."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_rails_dataset,
    )
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from dataclasses import replace
    cfg = replace(_CFG, l2_instance_prefix="spec_example")
    ds = build_rails_dataset(cfg, default_l2_instance())
    assert ds.DataSetId == "qs-gen-spec_example-l2ft-rails-dataset"


def test_rails_sheet_has_a_table_visual() -> None:
    """M.3.5 promotes Rails out of the placeholder TextBox-only state.
    The Rails sheet now hosts a Table (in addition to the header
    text box)."""
    from quicksight_gen.common.tree import Table
    app = build_l2_flow_tracing_app(_CFG)
    rails = _sheet_by_name(app, "Rails")
    table_visuals = [v for v in rails.visuals if isinstance(v, Table)]
    assert len(table_visuals) == 1


def test_rails_sheet_table_columns_cover_full_contract() -> None:
    """Every column in RAILS_CONTRACT shows up in the visual's
    column list — the analyst sees the full declared + runtime
    projection per rail."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import RAILS_CONTRACT
    from quicksight_gen.common.tree import Table
    app = build_l2_flow_tracing_app(_CFG)
    rails = _sheet_by_name(app, "Rails")
    table = next(v for v in rails.visuals if isinstance(v, Table))
    table_col_names = {c.column.name for c in table.columns}
    contract_col_names = {c.name for c in RAILS_CONTRACT.columns}
    assert table_col_names == contract_col_names
