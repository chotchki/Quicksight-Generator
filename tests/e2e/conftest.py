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
    """Load project config from config.yaml or env vars."""
    from quicksight_gen.common.config import load_config

    for candidate in (Path("config.yaml"), Path("run/config.yaml")):
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
def qs_identity_client():
    """Boto3 QuickSight client for the identity region (us-east-1).

    QuickSight user operations and embed URL generation must use
    the identity region, which may differ from the dashboard region.
    """
    import boto3
    return boto3.client("quicksight", region_name=IDENTITY_REGION)


@pytest.fixture(scope="session")
def dashboard_id(resource_prefix) -> str:
    return f"{resource_prefix}-payment-recon-dashboard"


@pytest.fixture(scope="session")
def analysis_id(resource_prefix) -> str:
    return f"{resource_prefix}-payment-recon-analysis"


@pytest.fixture(scope="session")
def theme_id(resource_prefix) -> str:
    return f"{resource_prefix}-theme"


@pytest.fixture(scope="session")
def dataset_ids(resource_prefix) -> list[str]:
    """All expected dataset IDs."""
    suffixes = [
        "merchants-dataset",
        "sales-dataset",
        "settlements-dataset",
        "payments-dataset",
        "settlement-exceptions-dataset",
        "payment-returns-dataset",
        "sale-settlement-mismatch-dataset",
        "settlement-payment-mismatch-dataset",
        "unmatched-external-txns-dataset",
        "external-transactions-dataset",
        "payment-recon-dataset",
    ]
    return [f"{resource_prefix}-{s}" for s in suffixes]


@pytest.fixture(scope="session")
def ar_dashboard_id(resource_prefix) -> str:
    return f"{resource_prefix}-account-recon-dashboard"


@pytest.fixture(scope="session")
def ar_analysis_id(resource_prefix) -> str:
    return f"{resource_prefix}-account-recon-analysis"


@pytest.fixture(scope="session")
def ar_dataset_ids(resource_prefix) -> list[str]:
    """Expected Account Recon dataset IDs.

    Phase K.1.4 collapsed the 14-check exception inventory into a single
    unified-exceptions dataset; the per-check datasets (limit-breach,
    overdraft, 9 CMS-specific checks) were dropped. non-zero-transfers
    survives because the Transfers tab still uses it for the Unhealthy
    KPI.
    """
    suffixes = [
        # Baseline (7)
        "ar-ledger-accounts-dataset",
        "ar-subledger-accounts-dataset",
        "ar-transactions-dataset",
        "ar-ledger-balance-drift-dataset",
        "ar-subledger-balance-drift-dataset",
        "ar-transfer-summary-dataset",
        "ar-non-zero-transfers-dataset",
        # Cross-check rollups (Phase F, 3)
        "ar-expected-zero-eod-rollup-dataset",
        "ar-two-sided-post-mismatch-rollup-dataset",
        "ar-balance-drift-timelines-rollup-dataset",
        # Daily Statement (Phase I.2, 2)
        "ar-daily-statement-summary-dataset",
        "ar-daily-statement-transactions-dataset",
        # Unified exceptions (Phase K.1.1, 1)
        "ar-unified-exceptions-dataset",
    ]
    return [f"{resource_prefix}-{s}" for s in suffixes]


@pytest.fixture(scope="session")
def inv_dashboard_id(resource_prefix) -> str:
    return f"{resource_prefix}-investigation-dashboard"


@pytest.fixture(scope="session")
def inv_analysis_id(resource_prefix) -> str:
    return f"{resource_prefix}-investigation-analysis"


@pytest.fixture(scope="session")
def inv_dataset_ids(resource_prefix) -> list[str]:
    """Expected Investigation dataset IDs.

    K.4.3 ships recipient-fanout. K.4.4 adds volume-anomalies (rolling
    z-score matview). K.4.5 adds money-trail (recursive-CTE matview).
    K.4.8 adds account-network (second wrapper over the K.4.5 matview)
    and a narrow accounts dataset feeding only the anchor dropdown.
    """
    suffixes = [
        "inv-recipient-fanout-dataset",
        "inv-volume-anomalies-dataset",
        "inv-money-trail-dataset",
        "inv-account-network-dataset",
        "inv-anetwork-accounts-dataset",
    ]
    return [f"{resource_prefix}-{s}" for s in suffixes]


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
