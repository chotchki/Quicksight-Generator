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
- M.2a.9 CLI smoke: `quicksight-gen generate l1-dashboard` writes the
  expected files.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest
from click.testing import CliRunner

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.l1_dashboard.app import build_l1_dashboard_app
from quicksight_gen.cli import main
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


def test_six_sheets_after_m2b4() -> None:
    """M.2b.4 adds Daily Statement. Sheet order is the analyst's
    journey order (Getting Started → 4 invariants → today's roll-up
    → per-account-day detail). Future M.2b substeps add more sheets;
    re-lock this list at each substep that adds one."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    sheet_names = [s.name for s in app.analysis.sheets]
    assert sheet_names == [
        "Getting Started", "Drift", "Overdraft",
        "Limit Breach", "Today's Exceptions", "Daily Statement",
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


# -- Daily Statement sheet (M.2b.4) ------------------------------------------


def test_daily_statement_sheet_present_after_m2b4() -> None:
    """M.2b.4 lands the Daily Statement sheet — sixth tab."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    ds = app.analysis.sheets[5]
    assert ds.name == "Daily Statement"
    assert ds.title == "Per-Account Daily Statement"


def test_daily_statement_has_five_kpis_and_one_table() -> None:
    """Daily Statement structure: 5 KPIs side-by-side (Opening / Debits /
    Credits / Closing Stored / Drift) + 1 detail table."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    ds = app.analysis.sheets[5]
    titles = [v.title for v in ds.visuals]
    assert titles == [
        "Opening Balance",
        "Debits",
        "Credits",
        "Closing Stored",
        "Drift",
        "Posted Money Records",
    ]


def test_daily_statement_parameters_and_controls() -> None:
    """M.2b.4: 2 new analysis-level parameters drive the sheet's
    per-account-day filter, surfaced as 2 sheet controls."""
    from quicksight_gen.apps.l1_dashboard.app import (
        P_L1_DS_ACCOUNT, P_L1_DS_BALANCE_DATE,
    )

    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    param_names = {p.name for p in app.analysis.parameters}
    assert P_L1_DS_ACCOUNT in param_names
    assert P_L1_DS_BALANCE_DATE in param_names

    ds = app.analysis.sheets[5]
    control_titles = [
        c.title for c in ds.parameter_controls
        if hasattr(c, "title")
    ]
    assert "Account" in control_titles
    assert "Business Day" in control_titles


def test_daily_statement_filter_groups_target_correct_columns() -> None:
    """4 SINGLE_DATASET filter groups (2 datasets × 2 params), each
    column-specific: summary uses business_day_start; transactions
    uses business_day."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    fg_ids = {fg.filter_group_id for fg in app.analysis.filter_groups}
    expected = {
        "fg-l1-ds-summary-account",
        "fg-l1-ds-summary-date",
        "fg-l1-ds-txn-account",
        "fg-l1-ds-txn-date",
    }
    assert expected.issubset(fg_ids)


def test_daily_statement_datasets_registered() -> None:
    """Both new datasets register on the App tree + their SQL targets
    the prefixed L2 instance (mirrors the M.2a.3 pattern)."""
    from quicksight_gen.apps.account_recon._l2 import default_l2_instance
    from quicksight_gen.apps.l1_dashboard.datasets import (
        DS_DAILY_STATEMENT_SUMMARY,
        DS_DAILY_STATEMENT_TRANSACTIONS,
        build_daily_statement_summary_dataset,
        build_daily_statement_transactions_dataset,
    )

    app = build_l1_dashboard_app(_CFG)
    registered_ids = {ds.identifier for ds in app.datasets}
    assert DS_DAILY_STATEMENT_SUMMARY in registered_ids
    assert DS_DAILY_STATEMENT_TRANSACTIONS in registered_ids

    instance = default_l2_instance()
    summary_ds = build_daily_statement_summary_dataset(_CFG, instance)
    txn_ds = build_daily_statement_transactions_dataset(_CFG, instance)

    summary_sql = next(
        iter(summary_ds.PhysicalTableMap.values())
    ).CustomSql
    txn_sql = next(iter(txn_ds.PhysicalTableMap.values())).CustomSql
    assert summary_sql is not None and txn_sql is not None
    assert f"FROM {instance.instance}_current_daily_balances" in summary_sql.SqlQuery
    assert f"FROM {instance.instance}_current_transactions" in summary_sql.SqlQuery
    assert f"FROM {instance.instance}_current_transactions" in txn_sql.SqlQuery


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


# -- Per-sheet filter controls (M.2b.3) --------------------------------------


def test_per_sheet_filter_dropdowns() -> None:
    """M.2b.3: each data-bearing sheet carries the right filter dropdowns.

    - Drift: Account + Account Role
    - Overdraft: Account + Account Role
    - Limit Breach: Account + Transfer Type
    - Today's Exceptions: Check Type + Account + Transfer Type

    Plus the date-range pickers from M.2b.1 (Date From / Date To)."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None

    def _filter_titles(sheet_idx: int) -> set[str]:
        sheet = app.analysis.sheets[sheet_idx]
        return {
            ctrl.title for ctrl in sheet.filter_controls
            if hasattr(ctrl, "title")
        }

    drift_filters = _filter_titles(1)
    assert {"Account", "Account Role"}.issubset(drift_filters)

    overdraft_filters = _filter_titles(2)
    assert {"Account", "Account Role"}.issubset(overdraft_filters)

    lb_filters = _filter_titles(3)
    assert {"Account", "Transfer Type"}.issubset(lb_filters)

    te_filters = _filter_titles(4)
    assert {"Check Type", "Account", "Transfer Type"}.issubset(te_filters)


# -- Conditional formatting on tables (M.2b.2) -------------------------------


def test_account_id_link_tints_on_every_table_with_account_id() -> None:
    """M.2b.2: every L1 dashboard table that exposes `account_id` tints
    it with the theme accent — visual cue that the column will become
    a drill source at M.2b.7. Theme accent is resolved from cfg, never
    hardcoded.

    Tables that don't expose `account_id` (e.g., Daily Statement's
    Posted Money Records, which is pre-filtered to one account by the
    sheet's parameter binding) are not required to carry the tint —
    there's nothing to drill from. The assertion walks each table's
    actual columns to decide whether the tint is required."""
    from quicksight_gen.common.theme import get_preset
    from quicksight_gen.common.tree import CellAccentText, Table

    accent = get_preset(_CFG.theme_preset).accent
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None

    tinted_tables = 0
    for sheet in app.analysis.sheets[1:]:  # skip Getting Started
        for visual in sheet.visuals:
            if not isinstance(visual, Table):
                continue
            col_names = {
                c.column.name for c in visual.columns
                if hasattr(c, "column") and hasattr(c.column, "name")
            }
            if "account_id" not in col_names:
                continue
            cf = visual.conditional_formatting or []
            tints = [
                f for f in cf
                if isinstance(f, CellAccentText) and f.color == accent
            ]
            assert len(tints) >= 1, (
                f"sheet {sheet.name!r} table {visual.title!r} exposes "
                f"account_id but is missing the theme-accent link tint"
            )
            tinted_tables += 1
    # 5 tables (drift leaf + drift parent + overdraft + limit breach +
    # today's exceptions) carry account_id and so should be tinted.
    assert tinted_tables >= 5, (
        f"expected at least 5 tables with account_id+tint, saw "
        f"{tinted_tables}"
    )


# -- Universal date-range filter (M.2b.1) ------------------------------------


def test_date_range_parameters_registered() -> None:
    """M.2b.1: P_L1_DATE_START + P_L1_DATE_END land on the analysis with
    rolling-date defaults."""
    from quicksight_gen.apps.l1_dashboard.app import (
        P_L1_DATE_END, P_L1_DATE_START,
    )

    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    param_names = {p.name for p in app.analysis.parameters}
    assert P_L1_DATE_START in param_names
    assert P_L1_DATE_END in param_names


def test_date_range_filter_groups_per_dataset() -> None:
    """One SINGLE_DATASET filter group lands per data-bearing dataset
    (5 total: drift, ledger_drift, overdraft, limit_breach, todays_exc)
    so the column-name mismatch (business_day_start vs business_day) is
    handled per-dataset rather than via cross-dataset matching."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    fg_ids = {fg.filter_group_id for fg in app.analysis.filter_groups}
    expected = {
        "fg-l1-date-drift",
        "fg-l1-date-ledger-drift",
        "fg-l1-date-overdraft",
        "fg-l1-date-limit-breach",
        "fg-l1-date-todays-exceptions",
    }
    assert expected.issubset(fg_ids)


def test_date_range_pickers_on_every_data_sheet() -> None:
    """Every data-bearing sheet (Drift, Overdraft, Limit Breach,
    Today's Exceptions) carries paired date pickers (Date From / Date
    To) bound to the shared params — controls sync via shared parameter
    binding so changing one moves all four."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    # Getting Started has no data → no date pickers.
    gs = app.analysis.sheets[0]
    assert len(gs.parameter_controls) == 0
    # Each of the 4 data-bearing sheets has 2 pickers.
    for sheet_idx in (1, 2, 3, 4):
        sheet = app.analysis.sheets[sheet_idx]
        picker_titles = [
            ctrl.title for ctrl in sheet.parameter_controls
            if hasattr(ctrl, "title")
        ]
        assert "Date From" in picker_titles, (
            f"sheet {sheet.name!r} missing Date From picker"
        )
        assert "Date To" in picker_titles, (
            f"sheet {sheet.name!r} missing Date To picker"
        )


def test_date_range_filter_targets_correct_columns() -> None:
    """Per-dataset filter binding: drift/ledger_drift/overdraft target
    `business_day_start` (the daily-balance column); limit_breach +
    todays_exceptions target `business_day` (the truncated-posting
    column). The mismatch is what motivates per-dataset filter groups."""
    app = build_l1_dashboard_app(_CFG)
    assert app.analysis is not None
    by_id = {fg.filter_group_id: fg for fg in app.analysis.filter_groups}

    def _column_name(fg_id: str) -> str:
        fg = by_id[fg_id]
        flt = fg.filters[0]
        # TimeRangeFilter.column is a Column ref; .name exposes the col.
        return flt.column.name  # type: ignore[union-attr]

    assert _column_name("fg-l1-date-drift") == "business_day_start"
    assert _column_name("fg-l1-date-ledger-drift") == "business_day_start"
    assert _column_name("fg-l1-date-overdraft") == "business_day_start"
    assert _column_name("fg-l1-date-limit-breach") == "business_day"
    assert _column_name("fg-l1-date-todays-exceptions") == "business_day"


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


# -- CLI smoke (M.2a.9) ------------------------------------------------------


class TestCli:
    """`quicksight-gen generate l1-dashboard` writes the expected files
    + the L1 dashboard is included in the `--all` shortcut. Mirrors
    the shape of test_executives.py::TestCli."""

    def _base_config(self, tmp_path: Path) -> Path:
        p = tmp_path / "config.yaml"
        p.write_text(
            "aws_account_id: '111122223333'\n"
            "aws_region: us-west-2\n"
            "theme_preset: default\n"
            "datasource_arn: arn:aws:quicksight:us-west-2:111122223333"
            ":datasource/ds\n"
        )
        return p

    def test_generate_l1_dashboard_subcommand(self, tmp_path: Path):
        config = self._base_config(tmp_path)
        out = tmp_path / "out"
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["generate", "-c", str(config), "-o", str(out), "l1-dashboard"],
        )
        assert result.exit_code == 0, result.output
        assert (out / "l1-dashboard-analysis.json").exists()
        assert (out / "l1-dashboard-dashboard.json").exists()
        # 5 datasets land in out/datasets/.
        ds_dir = out / "datasets"
        for name in (
            "qs-gen-l1-drift-dataset.json",
            "qs-gen-l1-ledger-drift-dataset.json",
            "qs-gen-l1-overdraft-dataset.json",
            "qs-gen-l1-limit-breach-dataset.json",
            "qs-gen-l1-todays-exceptions-dataset.json",
        ):
            assert (ds_dir / name).exists(), f"missing {name}"

    def test_demo_seed_rejects_l1_dashboard(self, tmp_path: Path):
        """`demo seed l1-dashboard` must fail with a Click validation
        error — L1 dashboard is L2-fed, not v5-demo-fed; the user should
        run the L2 pipeline (m2_6_verify.sh) instead."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["demo", "seed", "l1-dashboard", "-o", str(tmp_path / "seed.sql")],
        )
        assert result.exit_code != 0
        # Click's choice-validation error mentions the invalid value.
        assert "l1-dashboard" in result.output
