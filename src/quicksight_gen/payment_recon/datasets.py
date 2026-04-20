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

# These come from each sale row's JSON ``metadata`` column in demo mode.
# Production databases whose sale rows don't carry these keys will generate
# NULLs (JSON_VALUE returns NULL for missing paths) — if that becomes a
# problem we can gate them behind a config flag, but SPEC 2.2 opts for a
# static declaration rather than runtime introspection.
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


def _optional_metadata_sql_fields(metadata_expr: str = "metadata") -> str:
    """Return a SQL fragment for the optional fields, comma-prefixed.

    Each field is extracted from the JSON metadata column via JSON_VALUE
    and cast to its declared SQL type when numeric. ``metadata_expr`` lets
    callers pass an alias-qualified expression (e.g. ``t.metadata``).
    """
    if not OPTIONAL_SALE_METADATA:
        return ""
    parts: list[str] = []
    for col, ddl_type, _qs, _ftype, _label in OPTIONAL_SALE_METADATA:
        if ddl_type.startswith("DECIMAL"):
            parts.append(
                f"CAST(JSON_VALUE({metadata_expr}, '$.{col}') AS {ddl_type}) AS {col}"
            )
        else:
            parts.append(f"JSON_VALUE({metadata_expr}, '$.{col}') AS {col}")
    return ",\n    " + ",\n    ".join(parts)


def _aging_bucket_case(days_expr: str) -> str:
    """SQL CASE expression for aging_bucket from a days-outstanding expression."""
    return f"""\
    CASE
        WHEN ({days_expr}) <= 1 THEN '1: 0-1 day'
        WHEN ({days_expr}) <= 3 THEN '2: 2-3 days'
        WHEN ({days_expr}) <= 7 THEN '3: 4-7 days'
        WHEN ({days_expr}) <= 30 THEN '4: 8-30 days'
        ELSE '5: >30 days'
    END AS aging_bucket"""


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
    ColumnSpec("aging_bucket", "STRING"),
])

PAYMENT_RETURNS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("payment_id", "STRING"),
    ColumnSpec("settlement_id", "STRING"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("merchant_name", "STRING"),
    ColumnSpec("payment_amount", "DECIMAL"),
    ColumnSpec("payment_date", "DATETIME"),
    ColumnSpec("return_reason", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
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
    ColumnSpec("aging_bucket", "STRING"),
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
    ColumnSpec("aging_bucket", "STRING"),
])

UNMATCHED_EXTERNAL_TXNS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("external_system", "STRING"),
    ColumnSpec("external_amount", "DECIMAL"),
    ColumnSpec("merchant_id", "STRING"),
    ColumnSpec("transaction_date", "DATETIME"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
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
    ColumnSpec("aging_bucket", "STRING"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_merchants_dataset(cfg: Config) -> DataSet:
    # Phase G.9.1: reads from shared `daily_balances`. PR's merchant
    # sub-ledger accounts live under the `pr-merchant-ledger` control
    # account; metadata on each daily row carries the per-merchant
    # attributes (name, type, location, created_at, status) so DISTINCT
    # collapses days into one row per merchant. The control_account_id
    # filter scopes to PR's merchant_dda accounts (AR also has
    # merchant_dda customer DDAs but under a different control).
    sql = """\
SELECT DISTINCT
    JSON_VALUE(metadata, '$.merchant_id')                   AS merchant_id,
    JSON_VALUE(metadata, '$.merchant_name')                 AS merchant_name,
    JSON_VALUE(metadata, '$.merchant_type')                 AS merchant_type,
    JSON_VALUE(metadata, '$.location_id')                   AS location_id,
    CAST(JSON_VALUE(metadata, '$.created_at') AS TIMESTAMP) AS created_at,
    JSON_VALUE(metadata, '$.status')                        AS status
FROM daily_balances
WHERE account_type       = 'merchant_dda'
  AND control_account_id = 'pr-merchant-ledger'"""
    return build_dataset(
        cfg, cfg.prefixed("merchants-dataset"),
        "Merchants", "merchants",
        sql, MERCHANTS_CONTRACT,
    )


def build_sales_dataset(cfg: Config) -> DataSet:
    # Phase G.9.2: reads from shared `transactions`. PR sale transfers
    # carry one row per posting leg; the merchant_dda leg under the
    # `pr-merchant-ledger` control account is the canonical sale-row
    # (one per sale). Under the canonical sign convention
    # (`signed_amount > 0` = money IN to the account), a sale credits
    # the merchant_dda leg, so `signed_amount` is the customer-facing
    # amount: positive for sales, negative for refunds. PR-domain
    # fields (sale_id, card_brand, settlement_id, …) come out of the
    # JSON metadata.
    sql = f"""\
SELECT
    JSON_VALUE(t.metadata, '$.sale_id')                          AS sale_id,
    JSON_VALUE(t.metadata, '$.merchant_id')                      AS merchant_id,
    JSON_VALUE(t.metadata, '$.location_id')                      AS location_id,
    t.signed_amount                                              AS amount,
    JSON_VALUE(t.metadata, '$.sale_type')                        AS sale_type,
    JSON_VALUE(t.metadata, '$.payment_method')                   AS payment_method,
    t.posted_at                                                  AS sale_timestamp,
    JSON_VALUE(t.metadata, '$.card_brand')                       AS card_brand,
    JSON_VALUE(t.metadata, '$.card_last_four')                   AS card_last_four,
    JSON_VALUE(t.metadata, '$.reference_id')                     AS reference_id,
    JSON_VALUE(t.metadata, '$.tags')                             AS metadata,
    JSON_VALUE(t.metadata, '$.settlement_id')                    AS settlement_id,
    CASE
        WHEN JSON_VALUE(t.metadata, '$.settlement_id') IS NULL
            THEN (CURRENT_DATE - t.posted_at::date)
        ELSE NULL
    END AS days_outstanding,
    CASE
        WHEN JSON_VALUE(t.metadata, '$.settlement_id') IS NULL THEN 'Unsettled'
        ELSE 'Settled'
    END AS settlement_state{_optional_metadata_sql_fields('t.metadata')}
FROM transactions t
WHERE t.transfer_type      = 'sale'
  AND t.account_type       = 'merchant_dda'
  AND t.control_account_id = 'pr-merchant-ledger'"""
    return build_dataset(
        cfg, cfg.prefixed("sales-dataset"),
        "Sales", "sales",
        sql, SALES_CONTRACT,
    )


def build_settlements_dataset(cfg: Config) -> DataSet:
    # Phase G.9.3: reads from shared `transactions`. Settlement transfers
    # have two zero-netting postings on the merchant_dda leg; DISTINCT
    # collapses to one row per settlement (both legs carry identical
    # metadata + posted_at). LEFT JOIN to a payment-per-settlement
    # subquery wires payment_id / payment_state.
    sql = """\
SELECT DISTINCT
    JSON_VALUE(t.metadata, '$.settlement_id')                    AS settlement_id,
    JSON_VALUE(t.metadata, '$.merchant_id')                      AS merchant_id,
    JSON_VALUE(t.metadata, '$.settlement_type')                  AS settlement_type,
    CAST(JSON_VALUE(t.metadata, '$.settlement_amount') AS DECIMAL(12,2)) AS settlement_amount,
    t.posted_at                                                  AS settlement_date,
    JSON_VALUE(t.metadata, '$.settlement_status')                AS settlement_status,
    CAST(JSON_VALUE(t.metadata, '$.sale_count') AS INTEGER)      AS sale_count,
    (CURRENT_DATE - t.posted_at::date)                           AS days_outstanding,
    p.payment_id,
    CASE
        WHEN p.payment_id IS NULL THEN 'Unpaid'
        ELSE 'Paid'
    END AS payment_state
FROM transactions t
LEFT JOIN (
    SELECT DISTINCT
        JSON_VALUE(metadata, '$.settlement_id') AS settlement_id,
        JSON_VALUE(metadata, '$.payment_id')    AS payment_id
    FROM transactions
    WHERE transfer_type      = 'payment'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
) p ON p.settlement_id = JSON_VALUE(t.metadata, '$.settlement_id')
WHERE t.transfer_type      = 'settlement'
  AND t.account_type       = 'merchant_dda'
  AND t.control_account_id = 'pr-merchant-ledger'"""
    return build_dataset(
        cfg, cfg.prefixed("settlements-dataset"),
        "Settlements", "settlements",
        sql, SETTLEMENTS_CONTRACT,
    )


def build_payments_dataset(cfg: Config) -> DataSet:
    # Phase G.9.4: reads from shared `transactions`. Payment transfers
    # have two legs (pr-external-rail external_counter + merchant_dda);
    # filtering account_type='merchant_dda' picks one row per payment.
    sql = """\
SELECT
    JSON_VALUE(t.metadata, '$.payment_id')                          AS payment_id,
    JSON_VALUE(t.metadata, '$.settlement_id')                       AS settlement_id,
    JSON_VALUE(t.metadata, '$.merchant_id')                         AS merchant_id,
    CAST(JSON_VALUE(t.metadata, '$.payment_amount') AS DECIMAL(12,2)) AS payment_amount,
    t.posted_at                                                     AS payment_date,
    JSON_VALUE(t.metadata, '$.payment_status')                      AS payment_status,
    JSON_VALUE(t.metadata, '$.is_returned')                         AS is_returned,
    JSON_VALUE(t.metadata, '$.return_reason')                       AS return_reason,
    JSON_VALUE(t.metadata, '$.external_transaction_id')             AS external_transaction_id,
    CASE
        WHEN JSON_VALUE(t.metadata, '$.external_transaction_id') IS NULL THEN 'Unmatched'
        ELSE 'Matched'
    END AS external_match_state,
    JSON_VALUE(t.metadata, '$.payment_method')                      AS payment_method,
    (CURRENT_DATE - t.posted_at::date)                              AS days_outstanding
FROM transactions t
WHERE t.transfer_type      = 'payment'
  AND t.account_type       = 'merchant_dda'
  AND t.control_account_id = 'pr-merchant-ledger'"""
    return build_dataset(
        cfg, cfg.prefixed("payments-dataset"),
        "Payments", "payments",
        sql, PAYMENTS_CONTRACT,
    )


def build_settlement_exceptions_dataset(cfg: Config) -> DataSet:
    # Phase G.9.7: reads from shared `transactions`. Unsettled sales =
    # sale-transfer merchant_dda legs whose metadata.settlement_id is
    # absent (_compact strips None keys). merchant_name lives in sale
    # metadata (added in G.9.1) so no merchant join is needed.
    sql = f"""\
SELECT
    JSON_VALUE(t.metadata, '$.sale_id')                          AS sale_id,
    JSON_VALUE(t.metadata, '$.merchant_id')                      AS merchant_id,
    JSON_VALUE(t.metadata, '$.merchant_name')                    AS merchant_name,
    JSON_VALUE(t.metadata, '$.location_id')                      AS location_id,
    t.signed_amount                                              AS amount,
    t.posted_at                                                  AS sale_timestamp,
    (CURRENT_DATE - t.posted_at::date)                           AS days_outstanding,
{_aging_bucket_case('CURRENT_DATE - t.posted_at::date')}
FROM transactions t
WHERE t.transfer_type      = 'sale'
  AND t.account_type       = 'merchant_dda'
  AND t.control_account_id = 'pr-merchant-ledger'
  AND JSON_VALUE(t.metadata, '$.settlement_id') IS NULL"""
    return build_dataset(
        cfg, cfg.prefixed("settlement-exceptions-dataset"),
        "Settlement Exceptions", "settlement-exceptions",
        sql, SETTLEMENT_EXCEPTIONS_CONTRACT,
    )


def build_payment_returns_dataset(cfg: Config) -> DataSet:
    # Phase G.9.8: reads from shared `transactions`. Returned payments =
    # payment-transfer merchant_dda legs whose metadata.is_returned='true'.
    # merchant_name lives in payment metadata so no merchant join needed.
    sql = f"""\
SELECT
    JSON_VALUE(t.metadata, '$.payment_id')                        AS payment_id,
    JSON_VALUE(t.metadata, '$.settlement_id')                     AS settlement_id,
    JSON_VALUE(t.metadata, '$.merchant_id')                       AS merchant_id,
    JSON_VALUE(t.metadata, '$.merchant_name')                     AS merchant_name,
    CAST(JSON_VALUE(t.metadata, '$.payment_amount') AS DECIMAL(12,2)) AS payment_amount,
    t.posted_at                                                   AS payment_date,
    JSON_VALUE(t.metadata, '$.return_reason')                     AS return_reason,
    (CURRENT_DATE - t.posted_at::date)                            AS days_outstanding,
{_aging_bucket_case('CURRENT_DATE - t.posted_at::date')}
FROM transactions t
WHERE t.transfer_type      = 'payment'
  AND t.account_type       = 'merchant_dda'
  AND t.control_account_id = 'pr-merchant-ledger'
  AND JSON_VALUE(t.metadata, '$.is_returned') = 'true'"""
    return build_dataset(
        cfg, cfg.prefixed("payment-returns-dataset"),
        "Payment Returns", "payment-returns",
        sql, PAYMENT_RETURNS_CONTRACT,
    )


def build_sale_settlement_mismatch_dataset(cfg: Config) -> DataSet:
    # Phase G.9.9: reads from shared `transactions`. CTEs collapse
    # settlements (DISTINCT on metadata + posted_at — two zero-netting
    # legs) and sum the linked sales' merchant_dda legs (signed_amount
    # is the signed sale amount under the canonical convention: +sale,
    # -refund). Mismatch = stored settlement_amount <> sum of linked
    # sale amounts.
    sql = f"""\
WITH settlements AS (
    SELECT DISTINCT
        JSON_VALUE(metadata, '$.settlement_id')                 AS settlement_id,
        JSON_VALUE(metadata, '$.merchant_id')                   AS merchant_id,
        CAST(JSON_VALUE(metadata, '$.settlement_amount') AS DECIMAL(12,2)) AS settlement_amount,
        CAST(JSON_VALUE(metadata, '$.sale_count') AS INTEGER)   AS sale_count,
        posted_at                                               AS settlement_date
    FROM transactions
    WHERE transfer_type      = 'settlement'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
),
sale_sums AS (
    SELECT
        JSON_VALUE(metadata, '$.settlement_id')                 AS settlement_id,
        SUM(signed_amount)                                      AS sales_sum
    FROM transactions
    WHERE transfer_type      = 'sale'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
      AND JSON_VALUE(metadata, '$.settlement_id') IS NOT NULL
    GROUP BY JSON_VALUE(metadata, '$.settlement_id')
)
SELECT
    s.settlement_id,
    s.merchant_id,
    s.settlement_amount,
    COALESCE(ss.sales_sum, 0)                                   AS sales_sum,
    s.settlement_amount - COALESCE(ss.sales_sum, 0)             AS difference,
    s.sale_count,
    s.settlement_date,
    (CURRENT_DATE - s.settlement_date::date)                    AS days_outstanding,
{_aging_bucket_case('CURRENT_DATE - s.settlement_date::date')}
FROM settlements s
LEFT JOIN sale_sums ss ON ss.settlement_id = s.settlement_id
WHERE s.settlement_amount <> COALESCE(ss.sales_sum, 0)"""
    return build_dataset(
        cfg, cfg.prefixed("sale-settlement-mismatch-dataset"),
        "Sale \u2194 Settlement Mismatch", "sale-settlement-mismatch",
        sql, SALE_SETTLEMENT_MISMATCH_CONTRACT,
    )


def build_settlement_payment_mismatch_dataset(cfg: Config) -> DataSet:
    # Phase G.9.10: reads from shared `transactions`. CTEs collapse
    # settlements (DISTINCT — two zero-netting legs carry identical
    # metadata) and project payment merchant_dda legs. Mismatch =
    # payment_amount <> linked settlement_amount.
    sql = f"""\
WITH settlements AS (
    SELECT DISTINCT
        JSON_VALUE(metadata, '$.settlement_id')                         AS settlement_id,
        CAST(JSON_VALUE(metadata, '$.settlement_amount') AS DECIMAL(12,2)) AS settlement_amount
    FROM transactions
    WHERE transfer_type      = 'settlement'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
),
payments AS (
    SELECT
        JSON_VALUE(metadata, '$.payment_id')                            AS payment_id,
        JSON_VALUE(metadata, '$.settlement_id')                         AS settlement_id,
        JSON_VALUE(metadata, '$.merchant_id')                           AS merchant_id,
        CAST(JSON_VALUE(metadata, '$.payment_amount') AS DECIMAL(12,2)) AS payment_amount,
        posted_at                                                       AS payment_date
    FROM transactions
    WHERE transfer_type      = 'payment'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
)
SELECT
    p.payment_id,
    p.settlement_id,
    p.merchant_id,
    p.payment_amount,
    s.settlement_amount,
    p.payment_amount - s.settlement_amount                              AS difference,
    p.payment_date,
    (CURRENT_DATE - p.payment_date::date)                               AS days_outstanding,
{_aging_bucket_case('CURRENT_DATE - p.payment_date::date')}
FROM payments p
JOIN settlements s ON s.settlement_id = p.settlement_id
WHERE p.payment_amount <> s.settlement_amount"""
    return build_dataset(
        cfg, cfg.prefixed("settlement-payment-mismatch-dataset"),
        "Settlement \u2194 Payment Mismatch", "settlement-payment-mismatch",
        sql, SETTLEMENT_PAYMENT_MISMATCH_CONTRACT,
    )


def build_unmatched_external_txns_dataset(cfg: Config) -> DataSet:
    # Phase G.9.11: reads from shared `transactions`. ext_txn legs that
    # have no linked payment (no payment leg whose metadata names this
    # external_transaction_id). LEFT JOIN to a payment-per-ext_txn
    # subquery; WHERE p.ext_txn_id IS NULL surfaces the unmatched.
    sql = f"""\
SELECT
    JSON_VALUE(t.metadata, '$.external_transaction_id')             AS transaction_id,
    t.external_system                                               AS external_system,
    t.amount                                                        AS external_amount,
    JSON_VALUE(t.metadata, '$.merchant_id')                         AS merchant_id,
    t.posted_at                                                     AS transaction_date,
    JSON_VALUE(t.metadata, '$.status')                              AS status,
    (CURRENT_DATE - t.posted_at::date)                              AS days_outstanding,
{_aging_bucket_case('CURRENT_DATE - t.posted_at::date')}
FROM transactions t
LEFT JOIN (
    SELECT DISTINCT
        JSON_VALUE(metadata, '$.external_transaction_id')           AS ext_txn_id
    FROM transactions
    WHERE transfer_type      = 'payment'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
      AND JSON_VALUE(metadata, '$.external_transaction_id') IS NOT NULL
) p ON p.ext_txn_id = JSON_VALUE(t.metadata, '$.external_transaction_id')
WHERE t.transfer_type      = 'external_txn'
  AND t.account_type       = 'external_counter'
  AND t.control_account_id = 'pr-merchant-ledger'
  AND p.ext_txn_id IS NULL"""
    return build_dataset(
        cfg, cfg.prefixed("unmatched-external-txns-dataset"),
        "Unmatched External Transactions", "unmatched-external-txns",
        sql, UNMATCHED_EXTERNAL_TXNS_CONTRACT,
    )


def build_external_transactions_dataset(cfg: Config) -> DataSet:
    # Phase G.9.5: reads from shared `transactions`. ext_txn transfers
    # have one external_counter leg on pr-external-rail; the
    # processor-side status ('processed') lives in metadata, not in the
    # transfer/posting status (which is 'success' / 'failed').
    sql = """\
SELECT
    JSON_VALUE(t.metadata, '$.external_transaction_id')            AS transaction_id,
    t.external_system                                              AS external_system,
    t.amount                                                       AS external_amount,
    CAST(JSON_VALUE(t.metadata, '$.record_count') AS INTEGER)      AS record_count,
    t.posted_at                                                    AS transaction_date,
    JSON_VALUE(t.metadata, '$.status')                             AS status
FROM transactions t
WHERE t.transfer_type      = 'external_txn'
  AND t.account_type       = 'external_counter'
  AND t.control_account_id = 'pr-merchant-ledger'"""
    return build_dataset(
        cfg, cfg.prefixed("external-transactions-dataset"),
        "External Transactions", "external-transactions",
        sql, EXTERNAL_TRANSACTIONS_CONTRACT,
    )


def build_payment_recon_dataset(cfg: Config) -> DataSet:
    # Phase G.9.6: reads from shared `transactions`. Aggregates ext_txn
    # rows joined with their payments by metadata.external_transaction_id.
    # Inner subquery collapses payment legs to one row per payment so SUM
    # totals the same set the legacy SQL did.
    late_days = cfg.late_default_days
    sql = f"""\
SELECT
    JSON_VALUE(et.metadata, '$.external_transaction_id')             AS transaction_id,
    et.external_system,
    et.amount                                                        AS external_amount,
    COALESCE(SUM(p.payment_amount), 0)                               AS internal_total,
    et.amount - COALESCE(SUM(p.payment_amount), 0)                   AS difference,
    CASE
        WHEN et.amount = COALESCE(SUM(p.payment_amount), 0) THEN 'matched'
        WHEN (CURRENT_DATE - et.posted_at::date) > {late_days} THEN 'late'
        ELSE 'not_yet_matched'
    END                                                              AS match_status,
    COUNT(p.payment_id)                                              AS payment_count,
    JSON_VALUE(et.metadata, '$.merchant_id')                         AS merchant_id,
    et.posted_at                                                     AS transaction_date,
    (CURRENT_DATE - et.posted_at::date)                              AS days_outstanding,
{_aging_bucket_case('CURRENT_DATE - et.posted_at::date')}
FROM transactions et
LEFT JOIN (
    SELECT
        JSON_VALUE(metadata, '$.payment_id')                         AS payment_id,
        JSON_VALUE(metadata, '$.external_transaction_id')            AS ext_txn_id,
        CAST(JSON_VALUE(metadata, '$.payment_amount') AS DECIMAL(12,2)) AS payment_amount
    FROM transactions
    WHERE transfer_type      = 'payment'
      AND account_type       = 'merchant_dda'
      AND control_account_id = 'pr-merchant-ledger'
) p ON p.ext_txn_id = JSON_VALUE(et.metadata, '$.external_transaction_id')
WHERE et.transfer_type      = 'external_txn'
  AND et.account_type       = 'external_counter'
  AND et.control_account_id = 'pr-merchant-ledger'
GROUP BY JSON_VALUE(et.metadata, '$.external_transaction_id'),
         et.external_system, et.amount,
         JSON_VALUE(et.metadata, '$.merchant_id'),
         et.posted_at"""
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
