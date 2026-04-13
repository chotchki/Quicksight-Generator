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
FROM pr_merchants"""

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

# Optional sales metadata columns.
#
# These are sourced from the same ``pr_sales`` table in demo mode. Production
# databases without these columns will generate a SQL error on DIRECT_QUERY —
# if that becomes a problem we can gate them behind a config flag, but SPEC 2.2
# opts for a static declaration rather than runtime introspection.
#
# Each tuple: (sql_column, sql_ddl_type, qs_type, filter_type, control_label)
#  - sql_column     — column name in ``pr_sales``
#  - sql_ddl_type   — PostgreSQL type for the demo schema
#  - qs_type        — QuickSight InputColumn type (STRING|DECIMAL|DATETIME|INTEGER)
#  - filter_type    — auto-generated filter style
#                      (numeric | string | datetime)
#  - control_label  — human-friendly label for the auto-generated filter
OPTIONAL_SALE_METADATA: list[tuple[str, str, str, str, str]] = [
    ("taxes",               "DECIMAL(12,2)", "DECIMAL", "numeric",  "Taxes"),
    ("tips",                "DECIMAL(12,2)", "DECIMAL", "numeric",  "Tips"),
    ("discount_percentage", "DECIMAL(5,2)",  "DECIMAL", "numeric",  "Discount %"),
    ("cashier",             "VARCHAR(100)",  "STRING",  "string",   "Cashier"),
]


def _optional_metadata_columns() -> list[InputColumn]:
    return [
        InputColumn(Name=col, Type=qs_type)
        for col, _ddl, qs_type, _ftype, _label in OPTIONAL_SALE_METADATA
    ]


def _optional_metadata_sql_fields() -> str:
    """Return a SQL fragment listing the optional columns, comma-prefixed."""
    if not OPTIONAL_SALE_METADATA:
        return ""
    return ",\n    " + ",\n    ".join(
        col for col, *_ in OPTIONAL_SALE_METADATA
    )


def build_sales_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("sales-dataset")
    columns = [
        InputColumn(Name="sale_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="location_id", Type="STRING"),
        InputColumn(Name="amount", Type="DECIMAL"),
        InputColumn(Name="sale_type", Type="STRING"),
        InputColumn(Name="payment_method", Type="STRING"),
        InputColumn(Name="sale_timestamp", Type="DATETIME"),
        InputColumn(Name="card_brand", Type="STRING"),
        InputColumn(Name="card_last_four", Type="STRING"),
        InputColumn(Name="reference_id", Type="STRING"),
        InputColumn(Name="metadata", Type="STRING"),
        InputColumn(Name="settlement_id", Type="STRING"),
        InputColumn(Name="days_outstanding", Type="INTEGER"),
        InputColumn(Name="settlement_state", Type="STRING"),
    ] + _optional_metadata_columns()
    # days_outstanding is meaningful only for unsettled sales — settled sales
    # collapse to NULL. settlement_state is derived so filters can toggle
    # unsettled-only without relying on NULL semantics.
    sql = f"""\
SELECT
    sale_id,
    merchant_id,
    location_id,
    amount,
    sale_type,
    payment_method,
    sale_timestamp,
    card_brand,
    card_last_four,
    reference_id,
    metadata,
    settlement_id,
    CASE
        WHEN settlement_id IS NULL
            THEN (CURRENT_DATE - sale_timestamp::date)
        ELSE NULL
    END AS days_outstanding,
    CASE
        WHEN settlement_id IS NULL THEN 'Unsettled'
        ELSE 'Settled'
    END AS settlement_state{_optional_metadata_sql_fields()}
FROM pr_sales"""

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
        InputColumn(Name="days_outstanding", Type="INTEGER"),
        InputColumn(Name="payment_id", Type="STRING"),
        InputColumn(Name="payment_state", Type="STRING"),
    ]
    # LEFT JOIN pr_payments on settlement_id — demo data emits at most one
    # payment per settlement (see demo_data.py `pay_by_stl`), so this does
    # not duplicate settlement rows. payment_state backs the Show-Only-Unpaid
    # toggle on the Settlements sheet.
    sql = """\
SELECT
    s.settlement_id,
    s.merchant_id,
    s.settlement_type,
    s.settlement_amount,
    s.settlement_date,
    s.settlement_status,
    s.sale_count,
    (CURRENT_DATE - s.settlement_date::date) AS days_outstanding,
    p.payment_id,
    CASE
        WHEN p.payment_id IS NULL THEN 'Unpaid'
        ELSE 'Paid'
    END AS payment_state
FROM pr_settlements s
LEFT JOIN pr_payments p ON p.settlement_id = s.settlement_id"""

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
        InputColumn(Name="external_match_state", Type="STRING"),
        InputColumn(Name="payment_method", Type="STRING"),
        InputColumn(Name="days_outstanding", Type="INTEGER"),
    ]
    # external_match_state backs the Show-Only-Unmatched-Externally toggle
    # on the Payments sheet.
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
    external_transaction_id,
    CASE
        WHEN external_transaction_id IS NULL THEN 'Unmatched'
        ELSE 'Matched'
    END AS external_match_state,
    payment_method,
    (CURRENT_DATE - payment_date::date) AS days_outstanding
FROM pr_payments"""

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
        InputColumn(Name="days_outstanding", Type="INTEGER"),
    ]
    sql = """\
SELECT
    s.sale_id,
    s.merchant_id,
    m.merchant_name,
    s.location_id,
    s.amount,
    s.sale_timestamp,
    (CURRENT_DATE - s.sale_timestamp::date) AS days_outstanding
FROM pr_sales s
JOIN pr_merchants m ON m.merchant_id = s.merchant_id
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
FROM pr_payments p
JOIN pr_merchants m ON m.merchant_id = p.merchant_id
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
# 5g — Sale ↔ Settlement amount mismatches (SPEC 2.4)
# ---------------------------------------------------------------------------

def build_sale_settlement_mismatch_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("sale-settlement-mismatch-dataset")
    columns = [
        InputColumn(Name="settlement_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="settlement_amount", Type="DECIMAL"),
        InputColumn(Name="sales_sum", Type="DECIMAL"),
        InputColumn(Name="difference", Type="DECIMAL"),
        InputColumn(Name="sale_count", Type="INTEGER"),
        InputColumn(Name="settlement_date", Type="DATETIME"),
        InputColumn(Name="days_outstanding", Type="INTEGER"),
    ]
    sql = """\
SELECT
    settlement_id,
    merchant_id,
    settlement_amount,
    sales_sum,
    difference,
    sale_count,
    settlement_date,
    days_outstanding
FROM pr_sale_settlement_mismatch"""

    physical, logical = _physical_and_logical(
        cfg, "sale-settlement-mismatch",
        "Sale ↔ Settlement Mismatch", sql, columns,
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Sale ↔ Settlement Mismatch",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5h — Settlement ↔ Payment amount mismatches (SPEC 2.4)
# ---------------------------------------------------------------------------

def build_settlement_payment_mismatch_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("settlement-payment-mismatch-dataset")
    columns = [
        InputColumn(Name="payment_id", Type="STRING"),
        InputColumn(Name="settlement_id", Type="STRING"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="payment_amount", Type="DECIMAL"),
        InputColumn(Name="settlement_amount", Type="DECIMAL"),
        InputColumn(Name="difference", Type="DECIMAL"),
        InputColumn(Name="payment_date", Type="DATETIME"),
        InputColumn(Name="days_outstanding", Type="INTEGER"),
    ]
    sql = """\
SELECT
    payment_id,
    settlement_id,
    merchant_id,
    payment_amount,
    settlement_amount,
    difference,
    payment_date,
    days_outstanding
FROM pr_settlement_payment_mismatch"""

    physical, logical = _physical_and_logical(
        cfg, "settlement-payment-mismatch",
        "Settlement ↔ Payment Mismatch", sql, columns,
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Settlement ↔ Payment Mismatch",
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# 5i — External transactions without a linked payment (SPEC 2.4)
# ---------------------------------------------------------------------------

def build_unmatched_external_txns_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("unmatched-external-txns-dataset")
    columns = [
        InputColumn(Name="transaction_id", Type="STRING"),
        InputColumn(Name="external_system", Type="STRING"),
        InputColumn(Name="external_amount", Type="DECIMAL"),
        InputColumn(Name="merchant_id", Type="STRING"),
        InputColumn(Name="transaction_date", Type="DATETIME"),
        InputColumn(Name="status", Type="STRING"),
        InputColumn(Name="days_outstanding", Type="INTEGER"),
    ]
    sql = """\
SELECT
    transaction_id,
    external_system,
    external_amount,
    merchant_id,
    transaction_date,
    status,
    days_outstanding
FROM pr_unmatched_external_txns"""

    physical, logical = _physical_and_logical(
        cfg, "unmatched-external-txns",
        "Unmatched External Transactions", sql, columns,
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name="Unmatched External Transactions",
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
FROM pr_external_transactions"""

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
FROM pr_external_transactions et
LEFT JOIN pr_payments p ON p.external_transaction_id = et.transaction_id
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
    """Return the pipeline datasets (merchants, sales, settlements, payments,
    plus the exception-only datasets that back the Exceptions tab)."""
    return [
        build_merchants_dataset(cfg),
        build_sales_dataset(cfg),
        build_settlements_dataset(cfg),
        build_payments_dataset(cfg),
        build_settlement_exceptions_dataset(cfg),
        build_payment_returns_dataset(cfg),
        build_sale_settlement_mismatch_dataset(cfg),
        build_settlement_payment_mismatch_dataset(cfg),
        build_unmatched_external_txns_dataset(cfg),
    ]


def build_recon_datasets(cfg: Config) -> list[DataSet]:
    """Return the two reconciliation datasets."""
    return [
        build_external_transactions_dataset(cfg),
        build_payment_recon_dataset(cfg),
    ]


def build_all_datasets(cfg: Config) -> list[DataSet]:
    """Return every dataset used by the Payment Recon analysis."""
    return build_pipeline_datasets(cfg) + build_recon_datasets(cfg)
