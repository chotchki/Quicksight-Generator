"""L2 Flow Tracing app rendered against every L2 instance (M.3.9).

The L2 Flow Tracing dashboard's value claim is that it adapts to any
L2 instance with no per-instance code — sasquatch_pr's chain topology
should render the same shape as spec_example's (different content, same
structure), and a fuzz-generated L2 should render too. This file
parameterizes the structural assertions over ``L2_INSTANCES`` (the same
matrix ``test_l2_seed_contract.py`` uses), so adding a new YAML there
extends coverage here automatically.

What's checked across every L2 instance:

- The 4-sheet skeleton renders unchanged (Getting Started / Rails /
  Chains / L2 Exceptions in display order).
- Per-sheet visual counts: Rails has 1 Table; Chains has 1 Sankey + 1
  Table; L2 Exceptions has 12 KPIs + 6 Tables.
- Dataset count is exactly ``8 + N`` where N = the L2's distinct
  metadata key count. The fixed 8 are core (Rails + Chains + 6
  exceptions); the N is the per-instance dropdown source fan-out.
- Per-instance prefix on every dataset ID + analysis ID + dashboard
  ID, so multi-instance deploys don't collide in QuickSight.
- The metadata-driven dropdowns scale exactly with the L2's declared
  keys; an instance with 5 keys gets 5 dropdowns + 5 parameters; an
  instance with 28 gets 28 + 28.
- ``emit_analysis()`` + ``emit_dashboard()`` both succeed (full tree
  validation pass) — catches "L2 instance X has a shape that breaks
  the tree validator" regressions early.

Aurora deploy verification is M.3.10 — this file is unit-test only.
"""

from __future__ import annotations

from collections import Counter

import pytest

from quicksight_gen.apps.l2_flow_tracing.app import (
    build_l2_flow_tracing_app,
)
from quicksight_gen.apps.l2_flow_tracing.datasets import (
    declared_metadata_keys,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance, load_instance
from quicksight_gen.common.tree import KPI, Sankey, Table

# Reuse the matrix definition from the seed-contract test so every
# substep that adds an L2 instance to ``L2_INSTANCES`` automatically
# extends the M.3.9 verification surface here.
from tests.test_l2_seed_contract import L2_INSTANCES


_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


@pytest.fixture(params=L2_INSTANCES)
def l2_instance(request) -> L2Instance:
    """Load each parameterized L2 instance once per test."""
    return load_instance(request.param)


# -- Sheet structure invariants ----------------------------------------------


def test_four_sheets_in_display_order(l2_instance: L2Instance) -> None:
    """Same 4-sheet shape across every L2 instance — switching the L2
    doesn't reshuffle the dashboard."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    assert [s.name for s in app.analysis.sheets] == [
        "Getting Started", "Rails", "Chains", "L2 Exceptions",
    ]


def test_rails_sheet_visuals_invariant(l2_instance: L2Instance) -> None:
    """Rails sheet always has exactly 1 Table visual + the header
    text-box — the visual count doesn't bend with the L2."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    rails = next(s for s in app.analysis.sheets if s.name == "Rails")
    counts = Counter(type(v).__name__ for v in rails.visuals)
    assert counts == Counter(["Table"])


def test_chains_sheet_visuals_invariant(l2_instance: L2Instance) -> None:
    """Chains sheet always has exactly 1 Sankey + 1 Table — even
    against an L2 with zero chains (Sankey gracefully renders empty)."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    chains = next(s for s in app.analysis.sheets if s.name == "Chains")
    counts = Counter(type(v).__name__ for v in chains.visuals)
    assert counts == Counter(["Sankey", "Table"])


def test_l2_exceptions_sheet_visuals_invariant(
    l2_instance: L2Instance,
) -> None:
    """L2 Exceptions: 12 KPIs (2 per section × 6 sections) + 6 Tables
    — the section count doesn't bend with the L2."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    exc = next(s for s in app.analysis.sheets if s.name == "L2 Exceptions")
    counts = Counter(type(v).__name__ for v in exc.visuals)
    assert counts.get("KPI", 0) == 12
    assert counts.get("Table", 0) == 6


# -- Dataset count + ID prefix invariants -----------------------------------


def test_dataset_count_is_eight_plus_metadata_keys(
    l2_instance: L2Instance,
) -> None:
    """8 fixed core datasets + N metadata-key dropdown sources.
    Catches a substep regression where the core datasets drift OR
    the metadata-key fan-out detaches from `declared_metadata_keys`."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    n_meta = len(declared_metadata_keys(l2_instance))
    assert len(app.datasets) == 8 + n_meta


def test_every_dataset_id_carries_l2_prefix(
    l2_instance: L2Instance,
) -> None:
    """Per M.2d.3 — every dataset ID middle segment is the L2 instance
    prefix so multi-instance deploys don't collide in the same QS
    account. Mirrors `test_l1_dashboard_structure.py`'s prefix check."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    expected_prefix = f"qs-gen-{l2_instance.instance}-"
    for ds in app.datasets:
        # The arn carries the dataset ID; pull it out of the ARN's
        # `:dataset/<id>` suffix.
        ds_id = ds.arn.rsplit("/", 1)[-1]
        assert ds_id.startswith(expected_prefix), (
            f"dataset {ds.identifier!r} ID {ds_id!r} doesn't carry "
            f"the L2 prefix {expected_prefix!r}"
        )


def test_analysis_and_dashboard_ids_carry_l2_prefix(
    l2_instance: L2Instance,
) -> None:
    """Mirror — analysis + dashboard IDs both use the same per-instance
    prefix shape so deploys don't collide and cleanup-by-tag scopes
    correctly."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    analysis = app.emit_analysis()
    dashboard = app.emit_dashboard()
    expected_prefix = f"qs-gen-{l2_instance.instance}-"
    assert analysis.AnalysisId.startswith(expected_prefix)
    assert dashboard.DashboardId.startswith(expected_prefix)


def test_emit_analysis_and_dashboard_succeed(
    l2_instance: L2Instance,
) -> None:
    """Full tree validation passes for every L2 instance — catches
    'this YAML produces a shape the validator rejects' regressions."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    assert app.emit_analysis() is not None
    assert app.emit_dashboard() is not None


# -- Metadata controls scale per-instance ------------------------------------


def test_metadata_dropdowns_scale_with_declared_keys(
    l2_instance: L2Instance,
) -> None:
    """Per-instance ergonomics: the metadata dropdowns auto-walk
    `declared_metadata_keys(l2_instance)` — an instance with 5 keys
    gets 5 dropdowns + 5 parameters; an instance with 28 gets 28 + 28.
    Zero per-instance code; whatever the L2 declares becomes
    filterable."""
    app = build_l2_flow_tracing_app(_CFG, l2_instance=l2_instance)
    n_keys = len(declared_metadata_keys(l2_instance))
    meta_params = [
        p for p in app.analysis.parameters
        if str(p.name).startswith("pL2ftMeta_")
    ]
    assert len(meta_params) == n_keys
    exc = next(s for s in app.analysis.sheets if s.name == "L2 Exceptions")
    assert len(exc.parameter_controls) == n_keys


# -- Cross-instance differentiation ------------------------------------------


def test_instances_produce_different_dataset_id_namespaces() -> None:
    """Sanity: building the app against any two distinct L2 instances
    produces non-overlapping dataset ID sets — so a multi-instance
    QuickSight account can host both deploys without collision.

    This isn't parameterized — it cross-walks two specific instances
    to confirm the prefix isolation is real (not just one-instance
    coincidence)."""
    from pathlib import Path
    from quicksight_gen.common.l2 import load_instance

    spec = load_instance(
        Path(__file__).parent / "l2" / "spec_example.yaml"
    )
    sasq = load_instance(
        Path(__file__).parent / "l2" / "sasquatch_pr.yaml"
    )
    spec_app = build_l2_flow_tracing_app(_CFG, l2_instance=spec)
    sasq_app = build_l2_flow_tracing_app(_CFG, l2_instance=sasq)

    spec_ds_ids = {ds.arn.rsplit("/", 1)[-1] for ds in spec_app.datasets}
    sasq_ds_ids = {ds.arn.rsplit("/", 1)[-1] for ds in sasq_app.datasets}
    assert spec_ds_ids.isdisjoint(sasq_ds_ids), (
        "L2 prefix isolation broken — dataset IDs overlap between "
        "spec_example and sasquatch_pr"
    )
