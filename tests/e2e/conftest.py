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
        "external-transactions-dataset",
        "payment-recon-dataset",
    ]
    return [f"{resource_prefix}-{s}" for s in suffixes]


@pytest.fixture(scope="session")
def page_timeout() -> int:
    return PAGE_TIMEOUT


@pytest.fixture(scope="session")
def visual_timeout() -> int:
    return VISUAL_TIMEOUT
