"""Tests for the L1 Dashboard app — phase M.2a.

The L1 dashboard is the parallel-stack v6 app that consumes M.1a.7's L1
invariant views directly (no v5-idiom translation layer). M.2a.1 ships
the package skeleton + Analysis + Dashboard registration but no sheets;
M.2a.2-M.2a.6 add sheets one at a time, each tested at the substep
that introduces it.

Tests here cover:
- Build pipeline shape (cfg + l2_instance plumb through).
- Analysis + Dashboard emit cleanly.
- Dashboard ID + Analysis ID follow the `<l2_prefix>-l1-dashboard`
  convention so multi-instance deployments are distinguishable.
- Default L2 instance auto-loads the canonical Sasquatch fixture.
"""

from __future__ import annotations

import inspect

import pytest

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.l1_dashboard.app import build_l1_dashboard_app
from quicksight_gen.common.config import Config
from quicksight_gen.common.l2 import L2Instance


_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


# -- Build pipeline -----------------------------------------------------------


def test_build_with_default_loads_sasquatch_ar() -> None:
    """No kwarg → auto-load the canonical Sasquatch AR L2 fixture."""
    app = build_l1_dashboard_app(_CFG)
    assert app is not None
    assert app.name == "l1-dashboard"


def test_build_with_explicit_l2_instance_uses_caller_value() -> None:
    """Caller-supplied instance overrides the default."""
    explicit = default_l2_instance()
    app = build_l1_dashboard_app(_CFG, l2_instance=explicit)
    # Smoke; the deeper "instance was used for view targeting" assertions
    # land at M.2a.3+ when sheets actually consume views from the L2 prefix.
    assert app is not None


def test_build_signature_l2_instance_is_kwarg_only() -> None:
    """Same convention as build_account_recon_app: positional callers
    keep working without passing l2_instance; tests + alternative-persona
    deployments override via the kwarg."""
    sig = inspect.signature(build_l1_dashboard_app)
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
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    assert "sasquatch_ar" in app.analysis.name


def test_dashboard_registered() -> None:
    app = build_l1_dashboard_app(_CFG)
    assert app.dashboard is not None


def test_three_sheets_after_m2a4() -> None:
    """M.2a.2 shipped Getting Started; M.2a.3 shipped Drift; M.2a.4
    ships Overdraft. Remaining per-invariant sheets land in M.2a.5 -
    M.2a.6. This guard fires if a future commit accidentally lands a
    sheet outside its own substep."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    sheet_names = [s.name for s in app.analysis.sheets]
    assert sheet_names == ["Getting Started", "Drift", "Overdraft"]


# -- Getting Started — description-driven prose (M.2a.2) ---------------------


def test_getting_started_welcome_uses_l2_instance_description() -> None:
    """Core M.2a "description-driven prose" rule: the welcome body
    comes from `l2_instance.description`, NOT from a hardcoded persona
    string. Switching L2 instance switches the prose; M.7's render
    pipeline becomes "walk the L2 instance" instead of "substitute
    Sasquatch tokens"."""
    app = build_l1_dashboard_app(_CFG)
    gs = app.analysis.sheets[0]
    assert len(gs.text_boxes) == 1
    welcome_xml = gs.text_boxes[0].content
    # The fixture's top-level description string is the body source.
    assert "Sasquatch National Bank" in welcome_xml
    assert "Cash Management Suite" in welcome_xml


def test_getting_started_welcome_falls_back_when_l2_description_missing() -> None:
    """If the L2 instance has no top-level description, we surface a
    hint to fill it rather than a blank welcome — quicker debug."""
    from dataclasses import replace
    explicit = default_l2_instance()
    minimal = replace(explicit, description=None)
    app = build_l1_dashboard_app(_CFG, l2_instance=minimal)
    gs = app.analysis.sheets[0]
    welcome_xml = gs.text_boxes[0].content
    assert "L2 instance description missing" in welcome_xml


def test_getting_started_title_is_constant_ui_vocabulary() -> None:
    """The title 'L1 Reconciliation Dashboard' is constant UI vocabulary
    (NOT pulled from L2). Per the M.2a.4 design note: titles stay
    hardcoded, subtitles + bodies pull from L2 descriptions."""
    app = build_l1_dashboard_app(_CFG)
    gs = app.analysis.sheets[0]
    assert "L1 Reconciliation Dashboard" in gs.text_boxes[0].content


# -- Drift sheet (M.2a.3) ----------------------------------------------------


def test_drift_sheet_present_after_m2a3() -> None:
    """M.2a.3 lands the Drift sheet — second tab in display order."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    drift = app.analysis.sheets[1]
    assert drift.name == "Drift"
    assert drift.title == "Account Balance Drift"


def test_drift_sheet_has_two_kpis_and_two_tables() -> None:
    """Drift sheet structure: 2 KPIs side-by-side + leaf table + parent
    table. KPIs surface the "how many violations" headline; tables surface
    "which accounts on which days"."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    drift = app.analysis.sheets[1]
    titles = [v.title for v in drift.visuals]
    assert titles == [
        "Leaf Accounts in Drift",
        "Parent Accounts in Drift",
        "Leaf Account Drift",
        "Parent Account Drift",
    ]


def test_drift_datasets_registered_and_target_l1_views() -> None:
    """The L1 drift datasets must be registered on the App and their
    custom SQL must target the per-L2-instance L1 invariant views by
    prefix — that's the M.2a "L1 dashboard configured by L2" promise."""
    from quicksight_gen.apps.l1_dashboard.datasets import (
        DS_DRIFT,
        DS_LEDGER_DRIFT,
    )

    app = build_l1_dashboard_app(_CFG)
    registered_ids = {ds.identifier for ds in app.datasets}
    assert DS_DRIFT in registered_ids
    assert DS_LEDGER_DRIFT in registered_ids


def test_drift_dataset_sql_targets_prefixed_l1_views() -> None:
    """SQL for each drift dataset must SELECT from the L2-prefixed L1
    invariant view emitted by M.1a.7. Switching L2 instance switches the
    view targets — the parallel-stack v6 promise."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.apps.l1_dashboard.datasets import (
        build_drift_dataset,
        build_ledger_drift_dataset,
    )

    instance = default_l2_instance()
    prefix = instance.instance

    drift_ds = build_drift_dataset(_CFG, instance)
    ledger_ds = build_ledger_drift_dataset(_CFG, instance)

    drift_sql = next(iter(drift_ds.PhysicalTableMap.values())).CustomSql
    ledger_sql = next(iter(ledger_ds.PhysicalTableMap.values())).CustomSql
    assert drift_sql is not None
    assert ledger_sql is not None
    assert drift_sql.SqlQuery == f"SELECT * FROM {prefix}_drift"
    assert ledger_sql.SqlQuery == f"SELECT * FROM {prefix}_ledger_drift"


# -- Overdraft sheet (M.2a.4) ------------------------------------------------


def test_overdraft_sheet_present_after_m2a4() -> None:
    """M.2a.4 lands the Overdraft sheet — third tab in display order."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    overdraft = app.analysis.sheets[2]
    assert overdraft.name == "Overdraft"
    assert overdraft.title == "Internal Account Overdrafts"


def test_overdraft_sheet_has_kpi_and_table() -> None:
    """Overdraft sheet structure: 1 KPI (count) + 1 violations table.
    Single-dataset sheet — every row in the table IS one violation."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    overdraft = app.analysis.sheets[2]
    titles = [v.title for v in overdraft.visuals]
    assert titles == [
        "Internal Accounts in Overdraft",
        "Overdraft Violations",
    ]


def test_overdraft_dataset_registered_and_targets_l1_view() -> None:
    """The L1 overdraft dataset must be registered + its SQL must point
    at the L2-prefixed `<prefix>_overdraft` invariant view."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.apps.l1_dashboard.datasets import (
        DS_OVERDRAFT,
        build_overdraft_dataset,
    )

    app = build_l1_dashboard_app(_CFG)
    registered_ids = {ds.identifier for ds in app.datasets}
    assert DS_OVERDRAFT in registered_ids

    instance = default_l2_instance()
    overdraft_ds = build_overdraft_dataset(_CFG, instance)
    sql = next(iter(overdraft_ds.PhysicalTableMap.values())).CustomSql
    assert sql is not None
    assert sql.SqlQuery == f"SELECT * FROM {instance.instance}_overdraft"


# -- Emit shape (substitutability with other apps) ---------------------------


def test_analysis_emits_with_expected_id_suffix() -> None:
    app = build_l1_dashboard_app(_CFG)
    analysis = app.emit_analysis()
    assert analysis.AnalysisId.endswith("-l1-dashboard-analysis")


def test_dashboard_emits_with_expected_id_suffix() -> None:
    """Per the M.2a reframe naming: `<prefix>-l1-dashboard`.

    The QuickSight resource prefix (default `qs-gen`) prepends, so the
    full DashboardId is `qs-gen-l1-dashboard`.
    """
    app = build_l1_dashboard_app(_CFG)
    dashboard = app.emit_dashboard()
    assert dashboard.DashboardId.endswith("-l1-dashboard")
    assert dashboard.DashboardId == "qs-gen-l1-dashboard"
