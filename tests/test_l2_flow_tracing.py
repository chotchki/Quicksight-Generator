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
    """M.3.5 ships Rails (1); M.3.6 adds Chains (2). Each subsequent
    populator substep grows this assertion (M.3.7 → ~8). Re-key when a
    new tab populator lands."""
    app = build_l2_flow_tracing_app(_CFG)
    assert len(app.datasets) == 2
    assert {d.identifier for d in app.datasets} == {
        "l2ft-rails-ds", "l2ft-chains-ds",
    }


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
        ("L2 Exceptions", "M.3.7"),
    ],
)
def test_placeholder_sheets_point_to_their_substep(
    sheet_name: str, substep: str,
) -> None:
    """Each remaining placeholder TextBox names the substep that will
    replace it, so the next agent on this app sees a clear pointer to
    the next work item. Drop the parametrize entry as each substep
    populator lands (M.3.5 dropped Rails; M.3.6 dropped Chains)."""
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


# -- Chains sheet (M.3.6) ----------------------------------------------------


def _chains_dataset_sql_against(yaml_path: Path) -> str:
    """Pull the SQL string out of the Chains dataset against a chosen
    L2 instance. Used by tests that want to assert non-empty CTEs
    (sasquatch_pr.yaml has 6 chains; spec_example has 0)."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_chains_dataset,
    )
    inst = load_instance(yaml_path)
    aws_ds = build_chains_dataset(_CFG, inst)
    table = list(aws_ds.PhysicalTableMap.values())[0]
    return table.CustomSql.SqlQuery


def test_chains_dataset_targets_prefixed_current_transactions() -> None:
    """Chains runtime joins reference the prefixed current_transactions
    matview — `<prefix>_current_transactions`."""
    sql = _chains_dataset_sql_against(SASQUATCH_PR_YAML)
    assert "FROM sasquatch_pr_current_transactions" in sql


def test_chains_dataset_inlines_l2_chain_entries() -> None:
    """The declared edges CTE inlines every ChainEntry as a SQL
    string-literal SELECT row joined by N-1 UNION ALLs.
    sasquatch_pr.yaml has 6 chains; spec_example has 0 (the empty
    path is exercised in another test)."""
    inst = load_instance(SASQUATCH_PR_YAML)
    sql = _chains_dataset_sql_against(SASQUATCH_PR_YAML)
    assert "WITH declared AS" in sql
    for c in inst.chains:
        assert f"'{c.parent}'" in sql
        assert f"'{c.child}'" in sql
    assert sql.count("UNION ALL") == max(0, len(inst.chains) - 1)


def test_chains_dataset_emits_required_optional_labels() -> None:
    """The 'required' column in the dataset is emitted as the
    display-friendly 'Required' / 'Optional' labels (not boolean
    literals) so the visual reads cleanly."""
    sql = _chains_dataset_sql_against(SASQUATCH_PR_YAML)
    inst = load_instance(SASQUATCH_PR_YAML)
    has_required = any(c.required for c in inst.chains)
    has_optional = any(not c.required for c in inst.chains)
    if has_required:
        assert "'Required'" in sql
    if has_optional:
        assert "'Optional'" in sql


def test_chains_dataset_xor_group_emits_null_for_no_group() -> None:
    """ChainEntries without an xor_group serialize as NULL in the
    CTE, not as an empty string. Visuals can then treat NULL as
    'no XOR group' explicitly."""
    inst = load_instance(SASQUATCH_PR_YAML)
    has_no_group = any(c.xor_group is None for c in inst.chains)
    assert has_no_group, "test fixture lost its no-xor-group rows"
    sql = _chains_dataset_sql_against(SASQUATCH_PR_YAML)
    # At least one CTE row must have NULL in the xor_group slot.
    assert " NULL AS xor_group" in sql


def test_chains_dataset_orphan_rate_clamps_at_zero() -> None:
    """Orphan count uses GREATEST(...,  0) so child-fires-more-than-
    parent doesn't go negative — non-intuitive in a Sankey legend."""
    sql = _chains_dataset_sql_against(SASQUATCH_PR_YAML)
    assert "GREATEST(e.parent_firing_count - e.child_firing_count, 0)" in sql


def test_chains_dataset_orphan_rate_avoids_divide_by_zero() -> None:
    """Dead parent (zero firings) → orphan_rate of 0 instead of NaN
    or a divide-by-zero error. CASE guards the division."""
    sql = _chains_dataset_sql_against(SASQUATCH_PR_YAML)
    assert "WHEN e.parent_firing_count > 0" in sql
    assert "ELSE 0" in sql


def test_chains_dataset_contract_columns_match_builder() -> None:
    """Contract columns and SQL projection match — visual ds["col"]
    references resolve cleanly."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        CHAINS_CONTRACT, build_chains_dataset,
    )
    aws_ds = build_chains_dataset(_CFG, default_l2_instance())
    cols = {
        c.Name for c in list(aws_ds.PhysicalTableMap.values())[0].CustomSql.Columns
    }
    expected = {c.name for c in CHAINS_CONTRACT.columns}
    assert cols == expected


def test_chains_dataset_handles_empty_chains_list() -> None:
    """spec_example.yaml has zero chains; the empty CTE path
    (WHERE FALSE) keeps the SQL valid + visual harmless."""
    sql = _chains_dataset_sql_against(
        Path(__file__).parent / "l2" / "spec_example.yaml"
    )
    assert "WHERE FALSE" in sql
    assert "WITH declared AS" in sql


def test_chains_dataset_id_uses_l2_instance_prefix() -> None:
    """Per M.2d.3 — dataset ID middle segment is the L2 instance
    prefix so multi-instance deploys don't collide."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_chains_dataset,
    )
    from dataclasses import replace
    cfg = replace(_CFG, l2_instance_prefix="sasquatch_pr")
    ds = build_chains_dataset(cfg, load_instance(SASQUATCH_PR_YAML))
    assert ds.DataSetId == "qs-gen-sasquatch_pr-l2ft-chains-dataset"


def test_chains_sheet_has_a_sankey_visual() -> None:
    """M.3.6 promotes Chains out of the placeholder TextBox-only state.
    The Chains sheet now hosts a Sankey + a detail Table."""
    from quicksight_gen.common.tree import Sankey, Table
    app = build_l2_flow_tracing_app(_CFG)
    chains = _sheet_by_name(app, "Chains")
    sankey_visuals = [v for v in chains.visuals if isinstance(v, Sankey)]
    table_visuals = [v for v in chains.visuals if isinstance(v, Table)]
    assert len(sankey_visuals) == 1
    assert len(table_visuals) == 1


def test_chains_sankey_uses_node_columns_for_source_target() -> None:
    """The Sankey uses source_node + target_node (not parent_name +
    child_name) so future M.3.6+ display-string changes don't bust
    the SQL semantics."""
    from quicksight_gen.common.tree import Sankey
    app = build_l2_flow_tracing_app(_CFG)
    chains = _sheet_by_name(app, "Chains")
    sankey = next(v for v in chains.visuals if isinstance(v, Sankey))
    assert sankey.source.column.name == "source_node"
    assert sankey.target.column.name == "target_node"


def test_chains_sankey_weighted_by_parent_firing_count() -> None:
    """Edge thickness = how many times the parent fired in the
    window. Choosing a different weight (e.g., orphan_count) would
    invert the visual meaning."""
    from quicksight_gen.common.tree import Sankey
    app = build_l2_flow_tracing_app(_CFG)
    chains = _sheet_by_name(app, "Chains")
    sankey = next(v for v in chains.visuals if isinstance(v, Sankey))
    assert sankey.weight.column.name == "parent_firing_count"


def test_chains_detail_table_includes_orphan_columns() -> None:
    """The detail Table carries the orphan_count + orphan_rate
    columns Sankey can't show natively. Without these, analysts
    can't see chain orphans on this tab — they'd have to wait for
    M.3.7's L2.1 'Chain orphans' surface."""
    from quicksight_gen.common.tree import Table
    app = build_l2_flow_tracing_app(_CFG)
    chains = _sheet_by_name(app, "Chains")
    table = next(v for v in chains.visuals if isinstance(v, Table))
    table_col_names = {c.column.name for c in table.columns}
    assert {"orphan_count", "orphan_rate"} <= table_col_names
