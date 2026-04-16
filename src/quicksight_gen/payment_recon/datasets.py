"""QuickSight DataSet definitions with custom SQL.

Each function returns a DataSet model for one domain area. The SQL queries
are placeholders — replace them with real queries against your schema.
"""

from __future__ import annotations

from urllib.parse import urlparse

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnSpec,
    DatasetContract,
    build_dataset,
    dataset_permissions,
    DATASET_ACTIONS,
)
from quicksight_gen.common.models import (
    CredentialPair,
    DataSource,
    DataSourceCredentials,
    DataSourceParameters,
    DataSet,
    PostgreSqlParameters,
    ResourcePermission,
    SslProperties,
)

# ---------------------------------------------------------------------------
# DataSource builder (PR-specific — datasource is shared but built here)
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


# ---------------------------------------------------------------------------
# Optional sales metadata
# ---------------------------------------------------------------------------

# These are sourced from the same ``pr_sales`` table in demo mode. Production
# databases without these columns will generate a SQL error on DIRECT_QUERY —
# if that becomes a problem we can gate them behind a config flag, but SPEC 2.2
# opts for a static declaration rather than runtime introspection.
#
# Each tuple: (sql_column, sql_ddl_type, qs_type, filter_type, control_label)
OPTIONAL_SALE_METADATA: list[tuple[str, str, str, str, str]] = [
    ("taxes",               "DECIMAL(12,2)", "DECIMAL", "numeric",  "Taxes"),
    ("tips",                "DECIMAL(12,2)", "DECIMAL", "numeric",  "Tips"),
    ("discount_percentage", "DECIMAL(5,2)",  "DECIMAL", "numeric",  "Discount %"),
    ("cashier",             "VARCHAR(100)",  "STRING",  "string",   "Cashier"),
]


def _optional_metadata_columns() -> list[ColumnSpec]:
    return [
        ColumnSpec(col, qs_type)
        for col, _ddl, qs_type, _ftype, _label in OPTIONAL_SALE_METADATA
    ]


def _optional_metadata_sql_fields() -> str:
    """Return a SQL fragment listing the optional columns, comma-prefixed."""
    if not OPTIONAL_SALE_METADATA:
        return ""
    return ",\n    " + ",\n    ".join(
        col for col, *_ in OPTIONAL_SALE_METADATA
    )


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

MERCHANTS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("merchant_name", "STRING"),
    ColumnSpec("merchant_type", "STRING"),
    ColumnSpec("location_id", "STRING"),
    ColumnSpec("created_at", "DATETIME"),
    ColumnSpec("status", "STRING"),
])

SALES_CONTRACT = DatasetContract(columns=[
    ColumnSpec("sale_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("location_id", "STRING"),
    ColumnSpec("amount", "DECIMAL"),
    ColumnSpec("sale_type", "STRING"),
    ColumnSpec("payment_method", "STRING"),
    ColumnSpec("sale_timestamp", "DATETIME"),
    ColumnSpec("card_brand", "STRING"),
    ColumnSpec("card_last_four", "STRING"),
    ColumnSpec("reference_id", "STRING"),
    ColumnSpec("metadata", "STRING"),
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("settlement_state", "STRING"),
] + _optional_metadata_columns())

SETTLEMENTS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("settlement_type", "STRING"),
    ColumnSpec("settlement_amount", "DECIMAL"),
    ColumnSpec("settlement_date", "DATETIME"),
    ColumnSpec("settlement_status", "STRING"),
    ColumnSpec("sale_count", "INTEGER"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("payment_id", "STRING"),
    ColumnSpec("payment_state", "STRING"),
])

PAYMENTS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("payment_id", "STRING"),
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("payment_amount", "DECIMAL"),
    ColumnSpec("payment_date", "DATETIME"),
    ColumnSpec("payment_status", "STRING"),
    ColumnSpec("is_returned", "STRING"),
    ColumnSpec("return_reason", "STRING"),
    ColumnSpec("external_transaction_id", "STRING"),
    ColumnSpec("external_match_state", "STRING"),
    ColumnSpec("payment_method", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
])

SETTLEMENT_EXCEPTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("sale_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("merchant_name", "STRING"),
    ColumnSpec("location_id", "STRING"),
    ColumnSpec("amount", "DECIMAL"),
    ColumnSpec("sale_timestamp", "DATETIME"),
    ColumnSpec("days_outstanding", "INTEGER"),
])

PAYMENT_RETURNS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("payment_id", "STRING"),
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("merchant_name", "STRING"),
    ColumnSpec("payment_amount", "DECIMAL"),
    ColumnSpec("payment_date", "DATETIME"),
    ColumnSpec("return_reason", "STRING"),
])

SALE_SETTLEMENT_MISMATCH_CONTRACT = DatasetContract(columns=[
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("settlement_amount", "DECIMAL"),
    ColumnSpec("sales_sum", "DECIMAL"),
    ColumnSpec("difference", "DECIMAL"),
    ColumnSpec("sale_count", "INTEGER"),
    ColumnSpec("settlement_date", "DATETIME"),
    ColumnSpec("days_outstanding", "INTEGER"),
])

SETTLEMENT_PAYMENT_MISMATCH_CONTRACT = DatasetContract(columns=[
    ColumnSpec("payment_id", "STRING"),
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("payment_amount", "DECIMAL"),
    ColumnSpec("settlement_amount", "DECIMAL"),
    ColumnSpec("difference", "DECIMAL"),
    ColumnSpec("payment_date", "DATETIME"),
    ColumnSpec("days_outstanding", "INTEGER"),
])

UNMATCHED_EXTERNAL_TXNS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("external_system", "STRING"),
    ColumnSpec("external_amount", "DECIMAL"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("transaction_date", "DATETIME"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
])

EXTERNAL_TRANSACTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("external_system", "STRING"),
    ColumnSpec("external_amount", "DECIMAL"),
    ColumnSpec("record_count", "INTEGER"),
    ColumnSpec("transaction_date", "DATETIME"),
    ColumnSpec("status", "STRING"),
])

PAYMENT_RECON_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("external_system", "STRING"),
    ColumnSpec("external_amount", "DECIMAL"),
    ColumnSpec("internal_total", "DECIMAL"),
    ColumnSpec("difference", "DECIMAL"),
    ColumnSpec("match_status", "STRING"),
    ColumnSpec("payment_count", "INTEGER"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("transaction_date", "DATETIME"),
    ColumnSpec("days_outstanding", "INTEGER"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_merchants_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    merchant_id,
    merchant_name,
    merchant_type,
    location_id,
    created_at,
    status
FROM pr_merchants"""
    return build_dataset(
        cfg, cfg.prefixed("merchants-dataset"),
        "Merchants", "merchants",
        sql, MERCHANTS_CONTRACT,
    )


def build_sales_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("sales-dataset"),
        "Sales", "sales",
        sql, SALES_CONTRACT,
    )


def build_settlements_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("settlements-dataset"),
        "Settlements", "settlements",
        sql, SETTLEMENTS_CONTRACT,
    )


def build_payments_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("payments-dataset"),
        "Payments", "payments",
        sql, PAYMENTS_CONTRACT,
    )


def build_settlement_exceptions_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("settlement-exceptions-dataset"),
        "Settlement Exceptions", "settlement-exceptions",
        sql, SETTLEMENT_EXCEPTIONS_CONTRACT,
    )


def build_payment_returns_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("payment-returns-dataset"),
        "Payment Returns", "payment-returns",
        sql, PAYMENT_RETURNS_CONTRACT,
    )


def build_sale_settlement_mismatch_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("sale-settlement-mismatch-dataset"),
        "Sale \u2194 Settlement Mismatch", "sale-settlement-mismatch",
        sql, SALE_SETTLEMENT_MISMATCH_CONTRACT,
    )


def build_settlement_payment_mismatch_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("settlement-payment-mismatch-dataset"),
        "Settlement \u2194 Payment Mismatch", "settlement-payment-mismatch",
        sql, SETTLEMENT_PAYMENT_MISMATCH_CONTRACT,
    )


def build_unmatched_external_txns_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("unmatched-external-txns-dataset"),
        "Unmatched External Transactions", "unmatched-external-txns",
        sql, UNMATCHED_EXTERNAL_TXNS_CONTRACT,
    )


def build_external_transactions_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    transaction_id,
    external_system,
    external_amount,
    record_count,
    transaction_date,
    status
FROM pr_external_transactions"""
    return build_dataset(
        cfg, cfg.prefixed("external-transactions-dataset"),
        "External Transactions", "external-transactions",
        sql, EXTERNAL_TRANSACTIONS_CONTRACT,
    )


def build_payment_recon_dataset(cfg: Config) -> DataSet:
    late_days = cfg.late_default_days
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
    return build_dataset(
        cfg, cfg.prefixed("payment-recon-dataset"),
        "Payment Reconciliation", "payment-recon",
        sql, PAYMENT_RECON_CONTRACT,
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
