"""QuickSight DataSet definitions with custom SQL.

Each function returns a DataSet model for one domain area. The SQL queries
are placeholders — replace them with real queries against your schema.
"""

from __future__ import annotations

from urllib.parse import urlparse

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    CredentialPair,
    CustomSql,
    DataSet,
    DataSetUsageConfiguration,
    DataSource,
    DataSourceCredentials,
    DataSourceParameters,
    InputColumn,
    LogicalTable,
    LogicalTableSource,
    PhysicalTable,
    PostgreSqlParameters,
    ResourcePermission,
    SslProperties,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATASOURCE_ACTIONS = [
    "quicksight:DescribeDataSource",
    "quicksight:DescribeDataSourcePermissions",
    "quicksight:PassDataSource",
    "quicksight:UpdateDataSource",
    "quicksight:DeleteDataSource",
    "quicksight:UpdateDataSourcePermissions",
]


def build_datasource(cfg: Config) -> DataSource:
    """Build a QuickSight DataSource from demo_database_url in config."""
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


_DATASET_ACTIONS = [
    "quicksight:DescribeDataSet",
    "quicksight:DescribeDataSetPermissions",
    "quicksight:PassDataSet",
    "quicksight:DescribeIngestion",
    "quicksight:ListIngestions",
    "quicksight:UpdateDataSet",
    "quicksight:DeleteDataSet",
    "quicksight:CreateIngestion",
    "quicksight:CancelIngestion",
    "quicksight:UpdateDataSetPermissions",
]


def _permissions(cfg: Config) -> list[ResourcePermission] | None:
    if not cfg.principal_arns:
        return None
    return [
        ResourcePermission(Principal=arn, Actions=_DATASET_ACTIONS)
        for arn in cfg.principal_arns
    ]


def _physical_and_logical(
    cfg: Config,
    table_key: str,
    sql_name: str,
    sql_query: str,
    columns: list[InputColumn],
) -> tuple[dict[str, PhysicalTable], dict[str, LogicalTable]]:
    """Build the standard PhysicalTableMap + LogicalTableMap pair."""
    physical = {
        table_key: PhysicalTable(
            CustomSql=CustomSql(
                Name=sql_name,
                DataSourceArn=cfg.datasource_arn,
                SqlQuery=sql_query,
                Columns=columns,
            )
        )
    }
    logical = {
        f"{table_key}-logical": LogicalTable(
            Alias=sql_name,
            Source=LogicalTableSource(PhysicalTableId=table_key),
        )
    }
    return physical, logical


# ---------------------------------------------------------------------------
# 5a — Merchants
# ---------------------------------------------------------------------------

def build_merchants_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("merchants-dataset")
    columns = [
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="merchant_name", Type="STRING"),
        InputColumn(Name="merchant_type", Type="STRING"),
        InputColumn(Name="location_id", Type="STRING"),
        InputColumn(Name="created_at", Type="DATETIME"),
        InputColumn(Name="status", Type="STRING"),
    ]
    sql = """\
SELECT
    merchant_id,
    merchant_name,
    merchant_type,
    location_id,
    created_at,
    status
FROM merchants"""

    physical, logical = _physical_and_logical(
        cfg, "merchants", "Merchants", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Merchants",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5b — Sales
# ---------------------------------------------------------------------------

def build_sales_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("sales-dataset")
    columns = [
        InputColumn(Name="sale_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="location_id", Type="STRING"),
        InputColumn(Name="amount", Type="DECIMAL"),
        InputColumn(Name="sale_timestamp", Type="DATETIME"),
        InputColumn(Name="card_brand", Type="STRING"),
        InputColumn(Name="card_last_four", Type="STRING"),
        InputColumn(Name="reference_id", Type="STRING"),
        InputColumn(Name="metadata", Type="STRING"),
        InputColumn(Name="settlement_id", Type="STRING"),
    ]
    sql = """\
SELECT
    sale_id,
    merchant_id,
    location_id,
    amount,
    sale_timestamp,
    card_brand,
    card_last_four,
    reference_id,
    metadata,
    settlement_id
FROM sales"""

    physical, logical = _physical_and_logical(
        cfg, "sales", "Sales", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Sales",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5c — Settlements
# ---------------------------------------------------------------------------

def build_settlements_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("settlements-dataset")
    columns = [
        InputColumn(Name="settlement_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="settlement_type", Type="STRING"),
        InputColumn(Name="settlement_amount", Type="DECIMAL"),
        InputColumn(Name="settlement_date", Type="DATETIME"),
        InputColumn(Name="settlement_status", Type="STRING"),
        InputColumn(Name="sale_count", Type="INTEGER"),
    ]
    sql = """\
SELECT
    settlement_id,
    merchant_id,
    settlement_type,
    settlement_amount,
    settlement_date,
    settlement_status,
    sale_count
FROM settlements"""

    physical, logical = _physical_and_logical(
        cfg, "settlements", "Settlements", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Settlements",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5d — Payments
# ---------------------------------------------------------------------------

def build_payments_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("payments-dataset")
    columns = [
        InputColumn(Name="payment_id", Type="STRING"),
        InputColumn(Name="settlement_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="payment_amount", Type="DECIMAL"),
        InputColumn(Name="payment_date", Type="DATETIME"),
        InputColumn(Name="payment_status", Type="STRING"),
        InputColumn(Name="is_returned", Type="STRING"),
        InputColumn(Name="return_reason", Type="STRING"),
        InputColumn(Name="external_transaction_id", Type="STRING"),
    ]
    sql = """\
SELECT
    payment_id,
    settlement_id,
    merchant_id,
    payment_amount,
    payment_date,
    payment_status,
    is_returned,
    return_reason,
    external_transaction_id
FROM payments"""

    physical, logical = _physical_and_logical(
        cfg, "payments", "Payments", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Payments",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5e — Settlement exceptions (unsettled sales)
# ---------------------------------------------------------------------------

def build_settlement_exceptions_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("settlement-exceptions-dataset")
    columns = [
        InputColumn(Name="sale_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="merchant_name", Type="STRING"),
        InputColumn(Name="location_id", Type="STRING"),
        InputColumn(Name="amount", Type="DECIMAL"),
        InputColumn(Name="sale_timestamp", Type="DATETIME"),
        InputColumn(Name="days_unsettled", Type="INTEGER"),
    ]
    sql = """\
SELECT
    s.sale_id,
    s.merchant_id,
    m.merchant_name,
    s.location_id,
    s.amount,
    s.sale_timestamp,
    (CURRENT_DATE - s.sale_timestamp::date) AS days_unsettled
FROM sales s
JOIN merchants m ON m.merchant_id = s.merchant_id
WHERE s.settlement_id IS NULL"""

    physical, logical = _physical_and_logical(
        cfg, "settlement-exceptions", "Settlement Exceptions", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Settlement Exceptions",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5f — Payment returns
# ---------------------------------------------------------------------------

def build_payment_returns_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("payment-returns-dataset")
    columns = [
        InputColumn(Name="payment_id", Type="STRING"),
        InputColumn(Name="settlement_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="merchant_name", Type="STRING"),
        InputColumn(Name="payment_amount", Type="DECIMAL"),
        InputColumn(Name="payment_date", Type="DATETIME"),
        InputColumn(Name="return_reason", Type="STRING"),
    ]
    sql = """\
SELECT
    p.payment_id,
    p.settlement_id,
    p.merchant_id,
    m.merchant_name,
    p.payment_amount,
    p.payment_date,
    p.return_reason
FROM payments p
JOIN merchants m ON m.merchant_id = p.merchant_id
WHERE p.is_returned = 'true'"""

    physical, logical = _physical_and_logical(
        cfg, "payment-returns", "Payment Returns", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Payment Returns",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# Reconciliation: External transactions
# ---------------------------------------------------------------------------

def build_external_transactions_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("external-transactions-dataset")
    columns = [
        InputColumn(Name="transaction_id", Type="STRING"),
        InputColumn(Name="external_system", Type="STRING"),
        InputColumn(Name="external_amount", Type="DECIMAL"),
        InputColumn(Name="record_count", Type="INTEGER"),
        InputColumn(Name="transaction_date", Type="DATETIME"),
        InputColumn(Name="status", Type="STRING"),
    ]
    sql = """\
SELECT
    transaction_id,
    external_system,
    external_amount,
    record_count,
    transaction_date,
    status
FROM external_transactions"""

    physical, logical = _physical_and_logical(
        cfg, "external-transactions", "External Transactions", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="External Transactions",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# Reconciliation: Payment reconciliation
# ---------------------------------------------------------------------------

def build_payment_recon_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("payment-recon-dataset")
    late_days = cfg.late_default_days
    columns = [
        InputColumn(Name="transaction_id", Type="STRING"),
        InputColumn(Name="external_system", Type="STRING"),
        InputColumn(Name="external_amount", Type="DECIMAL"),
        InputColumn(Name="internal_total", Type="DECIMAL"),
        InputColumn(Name="difference", Type="DECIMAL"),
        InputColumn(Name="match_status", Type="STRING"),
        InputColumn(Name="payment_count", Type="INTEGER"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="transaction_date", Type="DATETIME"),
        InputColumn(Name="days_outstanding", Type="INTEGER"),
    ]
    sql = f"""\
SELECT
    et.transaction_id,
    et.external_system,
    et.external_amount,
    COALESCE(SUM(p.payment_amount), 0) AS internal_total,
    et.external_amount - COALESCE(SUM(p.payment_amount), 0) AS difference,
    CASE
        WHEN et.external_amount = COALESCE(SUM(p.payment_amount), 0) THEN 'matched'
        WHEN (CURRENT_DATE - et.transaction_date::date) > {late_days} THEN 'late'
        ELSE 'not_yet_matched'
    END AS match_status,
    COUNT(p.payment_id) AS payment_count,
    et.merchant_id,
    et.transaction_date,
    (CURRENT_DATE - et.transaction_date::date) AS days_outstanding
FROM external_transactions et
LEFT JOIN payments p ON p.external_transaction_id = et.transaction_id
GROUP BY et.transaction_id, et.external_system, et.external_amount,
         et.merchant_id, et.transaction_date"""

    physical, logical = _physical_and_logical(
        cfg, "payment-recon", "Payment Reconciliation", sql, columns
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Payment Reconciliation",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# Convenience: build dataset groups
# ---------------------------------------------------------------------------

def build_pipeline_datasets(cfg: Config) -> list[DataSet]:
    """Return the six Payment Recon pipeline datasets."""
    return [
        build_merchants_dataset(cfg),
        build_sales_dataset(cfg),
        build_settlements_dataset(cfg),
        build_payments_dataset(cfg),
        build_settlement_exceptions_dataset(cfg),
        build_payment_returns_dataset(cfg),
    ]


def build_recon_datasets(cfg: Config) -> list[DataSet]:
    """Return the two reconciliation datasets."""
    return [
        build_external_transactions_dataset(cfg),
        build_payment_recon_dataset(cfg),
    ]


def build_all_datasets(cfg: Config) -> list[DataSet]:
    """Return all eleven datasets (financial + reconciliation)."""
    return build_pipeline_datasets(cfg) + build_recon_datasets(cfg)
