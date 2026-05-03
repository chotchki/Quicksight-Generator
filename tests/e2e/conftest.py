"""Shared fixtures for end-to-end tests.

All e2e tests are skipped unless QS_GEN_E2E=1 is set. This keeps
`pytest` fast and free of AWS dependencies by default.

Required env vars (or config.yaml):
    QS_GEN_AWS_ACCOUNT_ID
    QS_GEN_AWS_REGION
    QS_GEN_DATASOURCE_ARN (or QS_GEN_DEMO_DATABASE_URL)

Optional env vars for tuning:
    QS_E2E_PAGE_TIMEOUT   — page load timeout in ms (default 30000)
    QS_E2E_VISUAL_TIMEOUT — per-visual render timeout in ms (default 10000)
    QS_E2E_IDENTITY_REGION — QuickSight identity region (default us-east-1)
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_collection_modifyitems(config, items):
    """Skip all e2e tests unless QS_GEN_E2E=1."""
    if os.environ.get("QS_GEN_E2E"):
        return
    skip = pytest.mark.skip(reason="e2e tests disabled (set QS_GEN_E2E=1)")
    for item in items:
        if "e2e" in str(item.fspath):
            item.add_marker(skip)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Expose per-phase test outcome to fixtures via item.rep_<phase>.

    M.4.1.f's harness fixtures consult ``item.rep_call.failed`` during
    teardown to decide whether to dump the failure triage manifest.
    Standard pytest idiom.
    """
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


# ---------------------------------------------------------------------------
# Timeout configuration
# ---------------------------------------------------------------------------

PAGE_TIMEOUT = int(os.environ.get("QS_E2E_PAGE_TIMEOUT", "30000"))
VISUAL_TIMEOUT = int(os.environ.get("QS_E2E_VISUAL_TIMEOUT", "10000"))
IDENTITY_REGION = os.environ.get("QS_E2E_IDENTITY_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def cfg():
    """Load project config — checks the legacy single-file location, then
    the per-dialect copies (Phase P), then env vars.

    The candidate order favors the explicit single-file config before
    falling back to the dialect-specific files. Override with the
    ``QS_GEN_CONFIG`` env var when both per-dialect files exist and
    you need to pin to one.
    """
    from quicksight_gen.common.config import load_config

    explicit = os.environ.get("QS_GEN_CONFIG")
    if explicit:
        return load_config(explicit)

    candidates = (
        Path("config.yaml"),
        Path("run/config.yaml"),
        Path("run/config.postgres.yaml"),
        Path("run/config.oracle.yaml"),
    )
    for candidate in candidates:
        if candidate.exists():
            return load_config(str(candidate))
    return load_config(None)


@pytest.fixture(scope="session")
def account_id(cfg) -> str:
    return cfg.aws_account_id


@pytest.fixture(scope="session")
def region(cfg) -> str:
    return cfg.aws_region


@pytest.fixture(scope="session")
def resource_prefix(cfg) -> str:
    return cfg.resource_prefix


@pytest.fixture(scope="session")
def qs_client(region):
    """Boto3 QuickSight client for the dashboard region."""
    import boto3
    return boto3.client("quicksight", region_name=region)


@pytest.fixture(scope="session")
def inv_l2_prefix() -> str:
    """The default L2 instance's prefix — the middle segment of every
    Investigation resource ID under N.3.f (Investigation became L2-fed,
    same default-institution YAML the L1 dashboard uses)."""
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    override = os.environ.get("QS_GEN_TEST_L2_INSTANCE")
    if override:
        return str(load_instance(Path(override)).instance)
    return str(default_l2_instance().instance)


@pytest.fixture(scope="session")
def inv_dashboard_id(resource_prefix, inv_l2_prefix) -> str:
    return f"{resource_prefix}-{inv_l2_prefix}-investigation-dashboard"


@pytest.fixture(scope="session")
def inv_analysis_id(resource_prefix, inv_l2_prefix) -> str:
    return f"{resource_prefix}-{inv_l2_prefix}-investigation-analysis"


@pytest.fixture(scope="session")
def inv_dataset_ids(resource_prefix, inv_l2_prefix) -> list[str]:
    """Expected Investigation dataset IDs.

    K.4.3 ships recipient-fanout. K.4.4 adds volume-anomalies (rolling
    z-score matview). K.4.5 adds money-trail (recursive-CTE matview).
    K.4.8 adds account-network (second wrapper over the K.4.5 matview)
    and a narrow accounts dataset feeding only the anchor dropdown.
    N.3.f added the L2 instance prefix as the middle segment.
    """
    suffixes = [
        "inv-recipient-fanout-dataset",
        "inv-volume-anomalies-dataset",
        "inv-money-trail-dataset",
        "inv-account-network-dataset",
        "inv-anetwork-accounts-dataset",
    ]
    return [f"{resource_prefix}-{inv_l2_prefix}-{s}" for s in suffixes]


@pytest.fixture(scope="session")
def exec_l2_prefix() -> str:
    """The default L2 instance's prefix — the middle segment of every
    Executives resource ID under N.4.b (Executives became L2-fed,
    same default-institution YAML the L1 dashboard uses)."""
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    override = os.environ.get("QS_GEN_TEST_L2_INSTANCE")
    if override:
        return str(load_instance(Path(override)).instance)
    return str(default_l2_instance().instance)


@pytest.fixture(scope="session")
def exec_dashboard_id(resource_prefix, exec_l2_prefix) -> str:
    return f"{resource_prefix}-{exec_l2_prefix}-executives-dashboard"


@pytest.fixture(scope="session")
def exec_analysis_id(resource_prefix, exec_l2_prefix) -> str:
    return f"{resource_prefix}-{exec_l2_prefix}-executives-analysis"


@pytest.fixture(scope="session")
def exec_dataset_ids(resource_prefix, exec_l2_prefix) -> list[str]:
    """Expected Executives dataset IDs (L.6.3).

    N.4.b added the L2 instance prefix as the middle segment.
    """
    suffixes = [
        "exec-transaction-summary-dataset",
        "exec-account-summary-dataset",
    ]
    return [f"{resource_prefix}-{exec_l2_prefix}-{s}" for s in suffixes]


# -- L1 dashboard fixtures (M.2c) --------------------------------------------
#
# IDs derive from the resource_prefix + the L2 instance's prefix per the
# M.2d.3 convention: `<resource_prefix>-<l2_prefix>-l1-<thing>`. The L2
# prefix is queried from the same default L2 instance the
# CLI/build_l1_dashboard_app uses, so no hardcoded "sasquatch_ar"
# string lives in the e2e fixtures.


@pytest.fixture(scope="session")
def l1_l2_prefix() -> str:
    """The default L2 instance's prefix — the middle segment of every
    L1 resource ID per M.2d.3."""
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    override = os.environ.get("QS_GEN_TEST_L2_INSTANCE")
    if override:
        return str(load_instance(Path(override)).instance)
    return str(default_l2_instance().instance)


@pytest.fixture(scope="session")
def l1_dashboard_id(resource_prefix, l1_l2_prefix) -> str:
    return f"{resource_prefix}-{l1_l2_prefix}-l1-dashboard"


@pytest.fixture(scope="session")
def l1_analysis_id(resource_prefix, l1_l2_prefix) -> str:
    return f"{resource_prefix}-{l1_l2_prefix}-l1-dashboard-analysis"


@pytest.fixture(scope="session")
def l1_dataset_ids(resource_prefix, l1_l2_prefix) -> list[str]:
    """Expected L1 dashboard dataset IDs.

    M.2a.3 shipped drift + ledger_drift; M.2a.4 added overdraft;
    M.2a.5 added limit_breach; M.2a.6 added the unified
    todays_exceptions UNION dataset; M.2b.4 added daily_statement
    summary + transactions for the per-account-day walk; M.2b.6 added
    the 2 timeline pre-aggregations for the LineChart sheet.
    M.2d.3 added the L2 prefix as the middle segment.
    """
    suffixes = [
        "l1-drift-dataset",
        "l1-ledger-drift-dataset",
        "l1-overdraft-dataset",
        "l1-limit-breach-dataset",
        "l1-todays-exceptions-dataset",
        "l1-daily-statement-summary-dataset",
        "l1-daily-statement-transactions-dataset",
        "l1-transactions-dataset",
        "l1-drift-timeline-dataset",
        "l1-ledger-drift-timeline-dataset",
        "l1-stuck-pending-dataset",
        "l1-stuck-unbundled-dataset",
        "l1-supersession-transactions-dataset",
        "l1-supersession-daily-balances-dataset",
        # M.4.4.5 / M.4.4.7 — App Info canary sheet datasets, per-app prefix.
        "l1-app-info-liveness-dataset",
        "l1-app-info-matviews-dataset",
    ]
    return [f"{resource_prefix}-{l1_l2_prefix}-{s}" for s in suffixes]


# -- L2 Flow Tracing dashboard fixtures --------------------------------------
#
# IDs derive from the resource_prefix + the L2 instance's prefix per the
# M.2d.3 convention. L2FT's dashboard ID lacks the trailing ``-dashboard``
# segment that L1 / Inv / Exec carry — the App's name is the suffix.


@pytest.fixture(scope="session")
def l2ft_l2_prefix() -> str:
    """The default L2 instance's prefix — the middle segment of every
    L2FT resource ID. Matches the same default the L2FT CLI uses
    (``spec_example``)."""
    from quicksight_gen.apps.l1_dashboard._l2 import default_l2_instance
    from quicksight_gen.common.l2 import load_instance

    override = os.environ.get("QS_GEN_TEST_L2_INSTANCE")
    if override:
        return str(load_instance(Path(override)).instance)
    return str(default_l2_instance().instance)


@pytest.fixture(scope="session")
def l2ft_dashboard_id(resource_prefix, l2ft_l2_prefix) -> str:
    return f"{resource_prefix}-{l2ft_l2_prefix}-l2-flow-tracing"


@pytest.fixture(scope="session")
def l2ft_analysis_id(resource_prefix, l2ft_l2_prefix) -> str:
    return f"{resource_prefix}-{l2ft_l2_prefix}-l2-flow-tracing-analysis"


# ---------------------------------------------------------------------------
# Tree-built App fixtures (L.11)
#
# Session-scoped because the tree is pure, in-memory, and identical for
# every test that consumes it. Tests walk these to derive expected sheet
# names / visual titles / filter group ids / parameter names — the tree
# is the source of truth, not a parallel hand-maintained list.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def inv_app(cfg):
    """Tree-built Investigation App (post-emit, auto-IDs resolved)."""
    from quicksight_gen.apps.investigation.app import build_investigation_app

    app = build_investigation_app(cfg)
    app.emit_analysis()
    return app


@pytest.fixture(scope="session")
def exec_app(cfg):
    """Tree-built Executives App (post-emit, auto-IDs resolved)."""
    from quicksight_gen.apps.executives.app import build_executives_app

    app = build_executives_app(cfg)
    app.emit_analysis()
    return app


@pytest.fixture(scope="session")
def l1_app(cfg):
    """Tree-built L1 Reconciliation Dashboard App.

    Auto-loads `default_l2_instance()` (the canonical Sasquatch AR
    fixture) — same default the CLI's `generate l1-dashboard` uses,
    so the tree shape here matches the deployed dashboard's shape.
    Post-emit so auto-IDs are resolved.
    """
    from quicksight_gen.apps.l1_dashboard.app import build_l1_dashboard_app

    app = build_l1_dashboard_app(cfg)
    app.emit_analysis()
    return app


@pytest.fixture(scope="session")
def page_timeout() -> int:
    return PAGE_TIMEOUT


@pytest.fixture(scope="session")
def visual_timeout() -> int:
    return VISUAL_TIMEOUT


# Aurora Serverless v2 scales to zero when idle. The first SELECT after
# a cold start can take 20-30s while the cluster warms up — long enough
# that browser e2e helpers that wait ~30s for visuals to hydrate will
# time out on the first sheet they touch. Warm the cluster once at session
# start by issuing the heaviest queries directly via psycopg2, so the
# subsequent dashboard renders hit a hot cluster. Pairs with the retry
# wrapper in browser_helpers.py for ad-hoc reruns where this fixture
# isn't covering us.
_WARMUP_QUERIES = (
    "SELECT 1",
    "SELECT COUNT(*) FROM transactions",
    "SELECT COUNT(*) FROM daily_balances",
    "SELECT COUNT(*) FROM ar_subledger_balance_drift",
    "SELECT COUNT(*) FROM ar_ledger_balance_drift",
    "SELECT COUNT(*) FROM ar_transfer_summary",
    "SELECT COUNT(*) FROM ar_subledger_overdraft",
    "SELECT COUNT(*) FROM ar_subledger_limit_breach",
    "SELECT COUNT(*) FROM ar_expected_zero_eod_rollup",
    "SELECT COUNT(*) FROM ar_two_sided_post_mismatch_rollup",
    "SELECT COUNT(*) FROM ar_balance_drift_timelines_rollup",
    "SELECT COUNT(*) FROM ar_unified_exceptions",
    # Investigation matviews — heavier to refresh than to read but the
    # first SELECT after Aurora cold-starts still pays the warm-up tax.
    "SELECT COUNT(*) FROM inv_pair_rolling_anomalies",
    "SELECT COUNT(*) FROM inv_money_trail_edges",
    # M.2c.1 — L1 invariant views per the M.1a.7 schema, prefixed by
    # the canonical Sasquatch AR L2 instance the L1 dashboard targets
    # by default. F12 cold-start tax applies to the first SELECT against
    # each prefixed table; warm them up here so the dashboard's first
    # render hits a hot cluster.
    "SELECT COUNT(*) FROM sasquatch_ar_current_transactions",
    "SELECT COUNT(*) FROM sasquatch_ar_current_daily_balances",
    "SELECT COUNT(*) FROM sasquatch_ar_drift",
    "SELECT COUNT(*) FROM sasquatch_ar_ledger_drift",
    "SELECT COUNT(*) FROM sasquatch_ar_overdraft",
    "SELECT COUNT(*) FROM sasquatch_ar_expected_eod_balance_breach",
    "SELECT COUNT(*) FROM sasquatch_ar_limit_breach",
)


@pytest.fixture(scope="session", autouse=True)
def warm_aurora(cfg):
    """Pre-warm Aurora before any e2e visual hits the dashboard."""
    if not cfg.demo_database_url:
        return
    try:
        import psycopg2
    except ImportError:
        return
    try:
        conn = psycopg2.connect(cfg.demo_database_url, connect_timeout=60)
    except Exception:
        return
    try:
        with conn.cursor() as cur:
            for sql in _WARMUP_QUERIES:
                try:
                    cur.execute(sql)
                    cur.fetchall()
                except Exception:
                    pass
    finally:
        conn.close()
