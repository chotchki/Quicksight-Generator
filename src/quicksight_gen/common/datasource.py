"""Shared QuickSight DataSource builder (M.4.4).

Migrated from ``apps/payment_recon/datasets.py`` when the PR app deleted —
build_datasource is app-agnostic infrastructure that the harness, the
demo CLI, and any future apps all need to construct a DataSource model
from a Postgres URL.

Lives under ``common/`` because it has no PR-specific dependencies and
all callers (harness's per-test datasource, ``quicksight-gen demo apply``,
manual deploy scripts) consume it equally.
"""

from __future__ import annotations

from urllib.parse import urlparse

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    CredentialPair,
    DataSource,
    DataSourceCredentials,
    DataSourceParameters,
    PostgreSqlParameters,
    ResourcePermission,
    SslProperties,
)


_DATASOURCE_ACTIONS = [
    "quicksight:DescribeDataSource",
    "quicksight:DescribeDataSourcePermissions",
    "quicksight:PassDataSource",
    "quicksight:UpdateDataSource",
    "quicksight:DeleteDataSource",
    "quicksight:UpdateDataSourcePermissions",
]


def build_datasource(cfg: Config) -> DataSource:
    """Build a QuickSight DataSource from ``cfg.demo_database_url``.

    The DataSource ID derives from ``cfg.prefixed("demo-datasource")`` so
    when ``cfg.l2_instance_prefix`` is set (per-test harness, multi-tenant
    deploys) each gets its own unique ID. Credentials come from the
    parsed Postgres URL; SSL is enabled by default; principal_arns from
    cfg become QS Permissions.

    Raises ValueError if ``cfg.demo_database_url`` is unset.
    """
    if not cfg.demo_database_url:
        raise ValueError("demo_database_url is required to build a datasource")

    parsed = urlparse(cfg.demo_database_url)
    ds_id = cfg.prefixed("demo-datasource")

    permissions = None
    if cfg.principal_arns:
        permissions = [
            ResourcePermission(Principal=arn, Actions=_DATASOURCE_ACTIONS)
            for arn in cfg.principal_arns
        ]

    return DataSource(
        AwsAccountId=cfg.aws_account_id,
        DataSourceId=ds_id,
        Name=f"{cfg.resource_prefix} Demo DataSource",
        Type="POSTGRESQL",
        DataSourceParameters=DataSourceParameters(
            PostgreSqlParameters=PostgreSqlParameters(
                Host=parsed.hostname or "localhost",
                Port=parsed.port or 5432,
                Database=parsed.path.lstrip("/") if parsed.path else "postgres",
            ),
        ),
        Credentials=DataSourceCredentials(
            CredentialPair=CredentialPair(
                Username=parsed.username or "",
                Password=parsed.password or "",
            ),
        ),
        SslProperties=SslProperties(DisableSsl=False),
        Permissions=permissions,
        Tags=cfg.tags(),
    )
