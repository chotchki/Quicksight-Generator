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


def test_five_sheets_after_m2a6() -> None:
    """M.2a.2-M.2a.6 ships 5 sheets: Getting Started + 4 per-invariant
    + Today's Exceptions. This guard fires if a future commit accidentally
    lands a sheet outside its own substep."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    sheet_names = [s.name for s in app.analysis.sheets]
    assert sheet_names == [
        "Getting Started", "Drift", "Overdraft",
        "Limit Breach", "Today's Exceptions",
    ]


# -- Getting Started — description-driven prose (M.2a.2) ---------------------


def test_getting_started_welcome_uses_l2_instance_description() -> None:
    """Core M.2a "description-driven prose" rule: the welcome body
    comes from `l2_instance.description`, NOT from a hardcoded persona
    string. Switching L2 instance switches the prose; M.7's render
    pipeline becomes "walk the L2 instance" instead of "substitute
    Sasquatch tokens".

    M.2a.7 added a second text box (L2 Coverage block) below the
    welcome — both are description-driven."""
    app = build_l1_dashboard_app(_CFG)
    gs = app.analysis.sheets[0]
    assert len(gs.text_boxes) == 2
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


# -- Limit Breach sheet (M.2a.5) ---------------------------------------------


def test_limit_breach_sheet_present_after_m2a5() -> None:
    """M.2a.5 lands the Limit Breach sheet — fourth tab in display order."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    lb = app.analysis.sheets[3]
    assert lb.name == "Limit Breach"
    assert lb.title == "Outbound Transfer Limit Breaches"


def test_limit_breach_sheet_has_kpi_and_table() -> None:
    """Limit Breach sheet structure: 1 KPI (count of breach cells) +
    1 detail table that puts outbound_total + cap side-by-side."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    lb = app.analysis.sheets[3]
    titles = [v.title for v in lb.visuals]
    assert titles == ["Limit Breach Cells", "Limit Breach Detail"]


def test_limit_breach_dataset_registered_and_targets_l1_view() -> None:
    """The L1 limit-breach dataset must be registered + its SQL must
    point at the L2-prefixed `<prefix>_limit_breach` invariant view."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.apps.l1_dashboard.datasets import (
        DS_LIMIT_BREACH,
        build_limit_breach_dataset,
    )

    app = build_l1_dashboard_app(_CFG)
    registered_ids = {ds.identifier for ds in app.datasets}
    assert DS_LIMIT_BREACH in registered_ids

    instance = default_l2_instance()
    lb_ds = build_limit_breach_dataset(_CFG, instance)
    sql = next(iter(lb_ds.PhysicalTableMap.values())).CustomSql
    assert sql is not None
    assert sql.SqlQuery == f"SELECT * FROM {instance.instance}_limit_breach"


# -- Today's Exceptions sheet (M.2a.6) ---------------------------------------


def test_todays_exceptions_sheet_present_after_m2a6() -> None:
    """M.2a.6 lands the Today's Exceptions sheet — fifth tab in display
    order, last in the M.2a.2-M.2a.6 sheet rollout."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    te = app.analysis.sheets[4]
    assert te.name == "Today's Exceptions"
    assert te.title == "Today's Exceptions"


def test_todays_exceptions_sheet_has_kpi_bar_table() -> None:
    """Today's Exceptions structure: 1 KPI (count) + 1 BarChart by
    check_type + 1 detail table sorted by magnitude DESC."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    te = app.analysis.sheets[4]
    titles = [v.title for v in te.visuals]
    assert titles == [
        "Open Exceptions",
        "Exceptions by Check Type",
        "Exception Detail",
    ]


def test_todays_exceptions_dataset_unions_all_five_l1_views() -> None:
    """The Today's Exceptions dataset SQL must UNION ALL across every
    L1 invariant view — drift / ledger_drift / overdraft / limit_breach
    / expected_eod_balance_breach — and pre-filter each branch to the
    most recent business day from `<prefix>_current_daily_balances`."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.apps.l1_dashboard.datasets import (
        DS_TODAYS_EXCEPTIONS,
        build_todays_exceptions_dataset,
    )

    app = build_l1_dashboard_app(_CFG)
    registered_ids = {ds.identifier for ds in app.datasets}
    assert DS_TODAYS_EXCEPTIONS in registered_ids

    instance = default_l2_instance()
    p = instance.instance
    te_ds = build_todays_exceptions_dataset(_CFG, instance)
    sql_obj = next(iter(te_ds.PhysicalTableMap.values())).CustomSql
    assert sql_obj is not None
    sql = sql_obj.SqlQuery

    # Every L1 invariant view is referenced.
    assert f"FROM {p}_drift " in sql
    assert f"FROM {p}_ledger_drift " in sql
    assert f"FROM {p}_overdraft " in sql
    assert f"FROM {p}_limit_breach " in sql
    assert f"FROM {p}_expected_eod_balance_breach " in sql
    # Today filter targets the prefix's current_daily_balances.
    assert f"MAX(business_day_start) FROM {p}_current_daily_balances" in sql
    # UNION ALL stitches the 5 branches (4 ALLs join 5 SELECTs).
    assert sql.count("UNION ALL") == 4


def test_todays_exceptions_sql_emits_unified_shape() -> None:
    """Every UNION branch must SELECT into the same column shape so the
    contract validates — check_type discriminator first, magnitude last,
    NULLs where the source view doesn't carry the column."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.apps.l1_dashboard.datasets import (
        build_todays_exceptions_dataset,
    )

    instance = default_l2_instance()
    te_ds = build_todays_exceptions_dataset(_CFG, instance)
    sql_obj = next(iter(te_ds.PhysicalTableMap.values())).CustomSql
    assert sql_obj is not None
    sql = sql_obj.SqlQuery

    # One literal check_type discriminator per branch.
    for label in (
        "'drift' AS check_type",
        "'ledger_drift'",
        "'overdraft'",
        "'limit_breach'",
        "'expected_eod_balance_breach'",
    ):
        assert label in sql


# -- Description-driven prose (M.2a.7) ---------------------------------------


def test_getting_started_coverage_lists_l2_inventory() -> None:
    """M.2a.7: Getting Started gets a second TextBox listing L2-derived
    inventory (account counts, rail counts, etc.) — switching L2
    instance changes the numbers, proving the seam."""
    app = build_l1_dashboard_app(_CFG)
    gs = app.analysis.sheets[0]
    assert len(gs.text_boxes) == 2
    coverage_xml = gs.text_boxes[1].content
    assert "L2 Coverage" in coverage_xml
    # Sasquatch fixture: 8 internal + 5 external accounts (per the M.2.1
    # hand-write). If the fixture changes, this test re-locks.
    assert "internal accounts" in coverage_xml
    assert "external accounts" in coverage_xml
    assert "rails" in coverage_xml
    assert "limit schedules" in coverage_xml


def test_drift_sheet_lists_internal_accounts_from_l2() -> None:
    """M.2a.7: Drift sheet's top TextBox enumerates internal accounts
    + roles from the L2 instance — analysts see the universe drift can
    surface against without leaving the sheet."""
    app = build_l1_dashboard_app(_CFG)
    drift = app.analysis.sheets[1]
    assert len(drift.text_boxes) == 1
    accounts_xml = drift.text_boxes[0].content
    assert "Internal Accounts in Scope" in accounts_xml
    # Sasquatch fixture has at least one GL control + one DDA template;
    # both should appear.
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    instance = default_l2_instance()
    internal_account_ids = [
        a.id for a in instance.accounts if a.scope == "internal"
    ]
    assert len(internal_account_ids) > 0, (
        "fixture must have internal accounts for this test to be meaningful"
    )
    # At least one internal account id appears in the rendered prose.
    assert any(aid in accounts_xml for aid in internal_account_ids)


def test_limit_breach_sheet_lists_l2_caps() -> None:
    """M.2a.7: Limit Breach sheet's top TextBox enumerates each L2
    LimitSchedule with its cap + L2-supplied prose. Analysts see "what's
    configured" before "what got breached"."""
    app = build_l1_dashboard_app(_CFG)
    lb = app.analysis.sheets[3]
    assert len(lb.text_boxes) == 1
    config_xml = lb.text_boxes[0].content
    assert "Configured Caps" in config_xml
    # Each LimitSchedule renders a `parent_role × transfer_type: $cap`
    # line; the multiplication-sign separator is a structural marker
    # the test can key off.
    assert "×" in config_xml
    # Cap renders with $ prefix.
    assert "$" in config_xml


def test_todays_exceptions_footer_carries_l2_description() -> None:
    """M.2a.7: Today's Exceptions ends with a TextBox carrying the L2
    instance's top-level description — same prose as the Getting Started
    welcome, anchored at the bottom of the unified-view landing page."""
    app = build_l1_dashboard_app(_CFG)
    te = app.analysis.sheets[4]
    assert len(te.text_boxes) == 1
    footer_xml = te.text_boxes[0].content
    assert "Institution Context" in footer_xml
    # Same Sasquatch fixture string the Getting Started welcome uses.
    assert "Sasquatch National Bank" in footer_xml


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
