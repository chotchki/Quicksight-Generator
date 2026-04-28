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
    """M.3.5 → 1 (Rails); M.3.6 → 2 (+ Chains); M.3.7 → 8 (+ 6
    L2 exception sections); M.3.8 → 8 + N (one dropdown source per
    declared metadata key). The fixed 8 are core; the metadata-key
    fan-out is per-instance."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys,
    )
    app = build_l2_flow_tracing_app(_CFG)
    n_meta = len(declared_metadata_keys(default_l2_instance()))
    assert len(app.datasets) == 8 + n_meta
    fixed = {
        "l2ft-rails-ds",
        "l2ft-chains-ds",
        "l2ft-exc-chain-orphans-ds",
        "l2ft-exc-unmatched-transfer-type-ds",
        "l2ft-exc-dead-rails-ds",
        "l2ft-exc-dead-bundles-activity-ds",
        "l2ft-exc-dead-metadata-ds",
        "l2ft-exc-dead-limit-schedules-ds",
    }
    assert fixed <= {d.identifier for d in app.datasets}


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


def test_no_remaining_placeholder_sheets() -> None:
    """M.3.7 lands the last populator (L2 Exceptions). No sheet
    should retain the M.3.4 'skeleton' placeholder marker — every
    sheet has its real visuals + prose now."""
    app = build_l2_flow_tracing_app(_CFG)
    for s in app.analysis.sheets:
        body_blob = "".join(tb.content for tb in s.text_boxes)
        assert "Skeleton at M.3.4" not in body_blob, (
            f"sheet {s.name!r} still carries the M.3.4 placeholder marker"
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


def test_cli_generate_l2_flow_tracing_l2_instance_flag(tmp_path: Path) -> None:
    """M.3.9 CLI surface: `--l2-instance PATH` overrides the default
    spec_example fixture. Generated dataset filenames carry the
    overridden prefix."""
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
            "--l2-instance", str(SASQUATCH_PR_YAML),
        ],
    )
    assert result.exit_code == 0, result.output
    # Dataset filenames carry the sasquatch_pr prefix, not spec_example.
    sasq_chains = (
        out_dir / "datasets"
        / "qs-gen-sasquatch_pr-l2ft-chains-dataset.json"
    )
    assert sasq_chains.exists()
    spec_chains = (
        out_dir / "datasets"
        / "qs-gen-spec_example-l2ft-chains-dataset.json"
    )
    assert not spec_chains.exists()


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


# -- L2 Exceptions sheet (M.3.7) ---------------------------------------------


_EXC_DATASETS = (
    ("l2ft-exc-chain-orphans-ds", "build_exc_chain_orphans_dataset"),
    ("l2ft-exc-unmatched-transfer-type-ds",
     "build_exc_unmatched_transfer_type_dataset"),
    ("l2ft-exc-dead-rails-ds", "build_exc_dead_rails_dataset"),
    ("l2ft-exc-dead-bundles-activity-ds",
     "build_exc_dead_bundles_activity_dataset"),
    ("l2ft-exc-dead-metadata-ds", "build_exc_dead_metadata_dataset"),
    ("l2ft-exc-dead-limit-schedules-ds",
     "build_exc_dead_limit_schedules_dataset"),
)


def _exc_dataset_sql(builder_name: str, yaml_path: Path) -> str:
    import quicksight_gen.apps.l2_flow_tracing.datasets as ds_mod
    inst = load_instance(yaml_path)
    builder = getattr(ds_mod, builder_name)
    aws_ds = builder(_CFG, inst)
    table = list(aws_ds.PhysicalTableMap.values())[0]
    return table.CustomSql.SqlQuery


@pytest.mark.parametrize("ds_id,builder_name", _EXC_DATASETS)
def test_exc_dataset_targets_prefixed_current_transactions(
    ds_id: str, builder_name: str,
) -> None:
    """Every L2 Exceptions dataset queries `<prefix>_current_transactions`
    so the supersession-aware ('latest entry per id') view drives the
    runtime side. The CTE may also reference the prefix; the broader
    check is that the target table name appears at least once."""
    sql = _exc_dataset_sql(builder_name, SASQUATCH_PR_YAML)
    assert "sasquatch_pr_current_transactions" in sql, (
        f"{builder_name} doesn't reference the prefixed transactions matview"
    )


@pytest.mark.parametrize("ds_id,builder_name", _EXC_DATASETS)
def test_exc_dataset_id_uses_l2_instance_prefix(
    ds_id: str, builder_name: str,
) -> None:
    """Per M.2d.3 — every exception dataset's ID middle segment is
    the L2 instance prefix so multi-instance deploys don't collide."""
    import quicksight_gen.apps.l2_flow_tracing.datasets as ds_mod
    from dataclasses import replace
    cfg = replace(_CFG, l2_instance_prefix="sasquatch_pr")
    builder = getattr(ds_mod, builder_name)
    aws_ds = builder(cfg, load_instance(SASQUATCH_PR_YAML))
    assert aws_ds.DataSetId.startswith("qs-gen-sasquatch_pr-l2ft-exc-"), (
        f"{builder_name} dataset ID lacks prefix: {aws_ds.DataSetId}"
    )


def test_exc_chain_orphans_filters_required_only() -> None:
    """L2.1 surfaces ONLY required orphans. Optional chain entries
    with unmatched children are by-design (XOR groups, optional
    follow-ons) — they don't constitute violations."""
    sql = _exc_dataset_sql(
        "build_exc_chain_orphans_dataset", SASQUATCH_PR_YAML,
    )
    assert "WHERE e.required = 'Required'" in sql


def test_exc_unmatched_transfer_type_excludes_declared_types() -> None:
    """L2.2 LEFT JOINs on declared types and filters to the unmatched
    side (NULL after join). All declared transfer_types appear as
    SELECT-literal rows in the declared_types CTE."""
    sql = _exc_dataset_sql(
        "build_exc_unmatched_transfer_type_dataset", SASQUATCH_PR_YAML,
    )
    inst = load_instance(SASQUATCH_PR_YAML)
    declared_types = {str(r.transfer_type) for r in inst.rails}
    for t in declared_types:
        assert f"'{t}'" in sql
    assert "LEFT JOIN declared_types" in sql
    assert "WHERE d.transfer_type IS NULL" in sql


def test_exc_dead_rails_filters_zero_postings_only() -> None:
    """L2.3 filters to ``COALESCE(r.total_postings, 0) = 0``. A LEFT
    JOIN preserves Rails with no matching runtime activity at all."""
    sql = _exc_dataset_sql(
        "build_exc_dead_rails_dataset", SASQUATCH_PR_YAML,
    )
    assert "COALESCE(r.total_postings, 0) = 0" in sql


def test_exc_dead_bundles_activity_checks_both_attributions() -> None:
    """L2.4: bundles_activity refs MAY name a rail OR a transfer_type
    — the SQL's NOT EXISTS checks BOTH attributions to avoid false
    positives."""
    sql = _exc_dataset_sql(
        "build_exc_dead_bundles_activity_dataset", SASQUATCH_PR_YAML,
    )
    assert "t.rail_name = db.bundle_target" in sql
    assert "t.transfer_type = db.bundle_target" in sql


def test_exc_dead_metadata_uses_static_json_paths() -> None:
    """L2.5 emits one NOT EXISTS fragment per (rail, metadata_key)
    with a static `$.<key>` JSONPath — keeps the SQL portable per
    the project's no-JSONB constraint (PG's JSON_VALUE prefers
    constant paths)."""
    sql = _exc_dataset_sql(
        "build_exc_dead_metadata_dataset", SASQUATCH_PR_YAML,
    )
    inst = load_instance(SASQUATCH_PR_YAML)
    declared_keys = {
        (str(r.name), str(k))
        for r in inst.rails for k in r.metadata_keys
    }
    if declared_keys:
        # At least one fragment per declared (rail, key) — checks
        # the literal '$.key' substring shows up.
        for _, key in declared_keys:
            assert f"'$.{key}'" in sql
        assert sql.count("JSON_VALUE(t.metadata,") == len(declared_keys)


def test_exc_dead_limit_schedules_filters_outbound_debit() -> None:
    """L2.6 only counts a LimitSchedule cell as 'used' if there's
    outbound DEBIT flow against the parent_role + transfer_type. A
    cap on inbound flow doesn't make sense; matching credit-only
    flow would give a false 'alive' signal."""
    sql = _exc_dataset_sql(
        "build_exc_dead_limit_schedules_dataset", SASQUATCH_PR_YAML,
    )
    assert "AND t.amount_direction = 'Debit'" in sql


@pytest.mark.parametrize("ds_id,builder_name", _EXC_DATASETS)
def test_exc_dataset_contract_columns_match_builder(
    ds_id: str, builder_name: str,
) -> None:
    """Every exception dataset's contract columns match its SQL
    projection — visual ds["col"] references resolve cleanly."""
    import quicksight_gen.apps.l2_flow_tracing.datasets as ds_mod
    contract_name_map = {
        "l2ft-exc-chain-orphans-ds": "EXC_CHAIN_ORPHANS_CONTRACT",
        "l2ft-exc-unmatched-transfer-type-ds":
            "EXC_UNMATCHED_TRANSFER_TYPE_CONTRACT",
        "l2ft-exc-dead-rails-ds": "EXC_DEAD_RAILS_CONTRACT",
        "l2ft-exc-dead-bundles-activity-ds":
            "EXC_DEAD_BUNDLES_ACTIVITY_CONTRACT",
        "l2ft-exc-dead-metadata-ds": "EXC_DEAD_METADATA_CONTRACT",
        "l2ft-exc-dead-limit-schedules-ds":
            "EXC_DEAD_LIMIT_SCHEDULES_CONTRACT",
    }
    contract = getattr(ds_mod, contract_name_map[ds_id])
    builder = getattr(ds_mod, builder_name)
    aws_ds = builder(_CFG, load_instance(SASQUATCH_PR_YAML))
    cols = {
        c.Name for c in list(aws_ds.PhysicalTableMap.values())[0].CustomSql.Columns
    }
    expected = {c.name for c in contract.columns}
    assert cols == expected


def test_exceptions_sheet_has_six_kpi_pairs_and_six_tables() -> None:
    """M.3.7 lands all 6 sections: each has 2 KPIs (count + distinct)
    and 1 detail Table. Final tally on the L2 Exceptions sheet:
    12 KPIs + 6 Tables."""
    from collections import Counter
    from quicksight_gen.common.tree import KPI, Table
    app = build_l2_flow_tracing_app(_CFG)
    exc = _sheet_by_name(app, "L2 Exceptions")
    counts = Counter(type(v).__name__ for v in exc.visuals)
    assert counts.get("KPI", 0) == 12, f"expected 12 KPIs, got {counts}"
    assert counts.get("Table", 0) == 6, f"expected 6 Tables, got {counts}"


def test_exceptions_sheet_titles_have_l2_prefix() -> None:
    """Every KPI + Table on the L2 Exceptions sheet leads with 'L2:' so
    analysts spot the surface at a glance vs the L1 dashboard's
    exceptions tab."""
    from quicksight_gen.common.tree import KPI, Table
    app = build_l2_flow_tracing_app(_CFG)
    exc = _sheet_by_name(app, "L2 Exceptions")
    for v in exc.visuals:
        if isinstance(v, (KPI, Table)):
            assert v.title.startswith("L2:"), (
                f"visual title {v.title!r} doesn't carry the L2: prefix"
            )


@pytest.mark.parametrize(
    "section_label,title_fragment",
    [
        ("L2.1", "Chain Orphans"),
        ("L2.2", "Unmatched Transfer Type"),
        ("L2.3", "Dead Rails"),
        ("L2.4", "Dead Bundles Activity"),
        ("L2.5", "Dead Metadata Declarations"),
        ("L2.6", "Dead Limit Schedules"),
    ],
)
def test_exceptions_sheet_has_each_section_header(
    section_label: str, title_fragment: str,
) -> None:
    """Each of the 6 L2 hygiene sections renders its named header
    text-box on the sheet. Catches accidental section drops in the
    populator."""
    app = build_l2_flow_tracing_app(_CFG)
    exc = _sheet_by_name(app, "L2 Exceptions")
    body_blob = "".join(tb.content for tb in exc.text_boxes)
    assert section_label in body_blob, (
        f"section {section_label!r} header missing from L2 Exceptions"
    )
    assert title_fragment in body_blob, (
        f"section {title_fragment!r} title missing from L2 Exceptions"
    )


# -- Metadata-driven filters (M.3.8) -----------------------------------------


def test_declared_metadata_keys_walks_union_across_rails() -> None:
    """`declared_metadata_keys` returns the sorted union of every
    Rail's `metadata_keys`. Drives both the dropdown-source dataset
    list AND the analysis-level parameter list — single source of
    truth so a key declared on a rail can't silently miss a control."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys,
    )
    inst = load_instance(SASQUATCH_PR_YAML)
    keys = declared_metadata_keys(inst)
    expected = sorted({
        str(k) for r in inst.rails for k in r.metadata_keys
    })
    assert keys == expected
    # Sorted (deterministic across runs).
    assert keys == sorted(keys)


def test_metadata_dropdown_dataset_per_declared_key() -> None:
    """One dataset per declared metadata key; missing keys means
    missing dropdowns."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_metadata_dropdown_datasets,
        declared_metadata_keys,
    )
    inst = load_instance(SASQUATCH_PR_YAML)
    dss = build_metadata_dropdown_datasets(_CFG, inst)
    assert len(dss) == len(declared_metadata_keys(inst))


def test_metadata_dropdown_dataset_uses_distinct_json_value() -> None:
    """Per-key dataset: distinct JSON_VALUE over the prefixed
    transactions matview, NULLs filtered, sorted output."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_metadata_dropdown_dataset,
    )
    inst = load_instance(SASQUATCH_PR_YAML)
    aws_ds = build_metadata_dropdown_dataset(_CFG, inst, "merchant_id")
    sql = list(aws_ds.PhysicalTableMap.values())[0].CustomSql.SqlQuery
    assert "SELECT DISTINCT JSON_VALUE(metadata, '$.merchant_id')" in sql
    assert "FROM sasquatch_pr_current_transactions" in sql
    assert "IS NOT NULL" in sql  # NULL filter
    assert "ORDER BY value" in sql


def test_metadata_dropdown_dataset_id_uses_l2_prefix_and_slug() -> None:
    """Per-key ID = `qs-gen-<l2-prefix>-l2ft-meta-<slug>-dataset`.
    Slug is the lowercased key with non-alphanumerics replaced by '-'."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        build_metadata_dropdown_dataset,
    )
    from dataclasses import replace
    cfg = replace(_CFG, l2_instance_prefix="sasquatch_pr")
    inst = load_instance(SASQUATCH_PR_YAML)
    # external_reference → 'external-reference' slug.
    ds = build_metadata_dropdown_dataset(cfg, inst, "external_reference")
    assert ds.DataSetId == (
        "qs-gen-sasquatch_pr-l2ft-meta-external-reference-dataset"
    )


def test_one_string_param_declared_per_metadata_key() -> None:
    """Every declared metadata key gets one analysis-level
    StringParam — the parameter is universal so any future visual on
    any sheet can read it via FilterGroup."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys, metadata_param_name,
    )
    app = build_l2_flow_tracing_app(_CFG)
    keys = declared_metadata_keys(default_l2_instance())
    expected_param_names = {metadata_param_name(k) for k in keys}
    actual_param_names = {str(p.name) for p in app.analysis.parameters}
    assert expected_param_names <= actual_param_names


def test_metadata_dropdown_per_key_on_l2_exceptions_sheet() -> None:
    """One ParameterDropdown per key on the L2 Exceptions sheet —
    the natural home for filtering. Other sheets have no metadata
    controls (deferred to M.3.8b for visual filter wiring)."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys,
    )
    app = build_l2_flow_tracing_app(_CFG)
    keys = declared_metadata_keys(default_l2_instance())
    exc = _sheet_by_name(app, "L2 Exceptions")
    assert len(exc.parameter_controls) == len(keys), (
        f"L2 Exceptions: expected {len(keys)} dropdowns, "
        f"got {len(exc.parameter_controls)}"
    )
    # Other sheets (Getting Started / Rails / Chains) have no
    # parameter controls in M.3.8 — controls are not duplicated.
    for sheet_name in ("Getting Started", "Rails", "Chains"):
        sheet = _sheet_by_name(app, sheet_name)
        assert len(sheet.parameter_controls) == 0, (
            f"{sheet_name}: expected 0 parameter controls, "
            f"got {len(sheet.parameter_controls)}"
        )


def test_metadata_dropdown_titles_are_human_readable() -> None:
    """Dropdown titles read as 'Metadata: <key>' so the analyst can
    scan the filter bar without reverse-engineering the parameter
    name."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys,
    )
    app = build_l2_flow_tracing_app(_CFG)
    exc = _sheet_by_name(app, "L2 Exceptions")
    titles = {ctrl.title for ctrl in exc.parameter_controls}
    for k in declared_metadata_keys(default_l2_instance()):
        assert f"Metadata: {k}" in titles


def test_metadata_dropdown_sourced_from_per_key_dataset() -> None:
    """Each dropdown's selectable_values point at the per-key
    dropdown source dataset's `value` column. Catches a wiring bug
    where the dropdown loses its options at deploy time."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys, metadata_dropdown_ds_id,
    )
    from quicksight_gen.common.tree import LinkedValues
    app = build_l2_flow_tracing_app(_CFG)
    exc = _sheet_by_name(app, "L2 Exceptions")
    expected_ds_ids = {
        metadata_dropdown_ds_id(k)
        for k in declared_metadata_keys(default_l2_instance())
    }
    actual_ds_ids = set()
    for ctrl in exc.parameter_controls:
        assert isinstance(ctrl.selectable_values, LinkedValues)
        assert ctrl.selectable_values.column_name == "value"
        actual_ds_ids.add(ctrl.selectable_values.dataset.identifier)
    assert actual_ds_ids == expected_ds_ids


def test_no_metadata_controls_when_l2_has_no_metadata_keys(
    tmp_path: Path,
) -> None:
    """An L2 instance with no Rail.metadata_keys produces zero
    metadata dropdowns + zero metadata parameters — no-op path."""
    bare = tmp_path / "no_metadata.yaml"
    bare.write_text(
        "instance: no_metadata\n"
        "accounts:\n"
        "  - id: control\n"
        "    role: ControlAccount\n"
        "    scope: internal\n"
        "    expected_eod_balance: 0\n"
        "  - id: ext\n"
        "    role: External\n"
        "    scope: external\n"
        "rails:\n"
        # 1-leg rail with no metadata_keys.
        "  - name: BareRail\n"
        "    transfer_type: bare\n"
        "    leg_role: ControlAccount\n"
        "    leg_direction: Debit\n"
        "    origin: InternalInitiated\n"
    )
    inst = load_instance(bare, validate=False)
    app = build_l2_flow_tracing_app(_CFG, l2_instance=inst)
    # Zero metadata-key parameters; only base params (none today, but
    # the assertion is on the metadata-key prefix).
    meta_params = [
        p for p in app.analysis.parameters
        if str(p.name).startswith("pL2ftMeta_")
    ]
    assert meta_params == []
    exc = _sheet_by_name(app, "L2 Exceptions")
    assert exc.parameter_controls == []


def test_metadata_dropdowns_scale_with_l2_instance() -> None:
    """sasquatch_pr (28 keys) and spec_example (5 keys) both produce
    the right control + parameter counts. The dashboard adapts to the
    L2 — zero per-instance code, whatever the L2 declares becomes
    filterable."""
    from quicksight_gen.apps.l2_flow_tracing.datasets import (
        declared_metadata_keys,
    )
    sasq = load_instance(SASQUATCH_PR_YAML)
    sasq_app = build_l2_flow_tracing_app(_CFG, l2_instance=sasq)
    sasq_meta_count = len(declared_metadata_keys(sasq))
    sasq_meta_params = [
        p for p in sasq_app.analysis.parameters
        if str(p.name).startswith("pL2ftMeta_")
    ]
    assert len(sasq_meta_params) == sasq_meta_count
    sasq_exc = _sheet_by_name(sasq_app, "L2 Exceptions")
    assert len(sasq_exc.parameter_controls) == sasq_meta_count

    spec_app = build_l2_flow_tracing_app(_CFG)
    spec_meta_count = len(declared_metadata_keys(default_l2_instance()))
    assert spec_meta_count != sasq_meta_count, (
        "test fixtures lost their differentiation"
    )
    spec_exc = _sheet_by_name(spec_app, "L2 Exceptions")
    assert len(spec_exc.parameter_controls) == spec_meta_count
