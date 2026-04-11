"""QuickSight DataSet definitions with custom SQL.

Each function returns a DataSet model for one domain area. The SQL queries
are placeholders — replace them with real queries against your schema.
"""

from __future__ import annotations

from quicksight_gen.config import Config
from quicksight_gen.models import (
    CustomSql,
    DataSet,
    DataSetUsageConfiguration,
    InputColumn,
    LogicalTable,
    LogicalTableSource,
    PhysicalTable,
    ResourcePermission,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DATASET_ACTIONS = [
    "quicksight:DescribeDataSet",
    "quicksight:DescribeDataSetPermissions",
    "quicksight:PassDataSet",
    "quicksight:DescribeIngestion",
    "quicksight:ListIngestions",
    "quicksight:UpdateDataSet",
    "quicksight:DeleteDataSet",
    "quicksight:UpdateDataSetPermissions",
]


def _permissions(cfg: Config) -> list[ResourcePermission] | None:
    if cfg.principal_arn is None:
        return None
    return [ResourcePermission(Principal=cfg.principal_arn, Actions=_DATASET_ACTIONS)]


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
    metadata
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
    return_reason
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
    DATEDIFF(day, s.sale_timestamp, CURRENT_DATE) AS days_unsettled
FROM sales s
JOIN merchants m ON m.merchant_id = s.merchant_id
LEFT JOIN settlements st ON st.settlement_id = s.sale_id
WHERE st.settlement_id IS NULL"""

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
    )


# ---------------------------------------------------------------------------
# Convenience: build all datasets
# ---------------------------------------------------------------------------

def build_all_datasets(cfg: Config) -> list[DataSet]:
    """Return all six datasets in dependency order."""
    return [
        build_merchants_dataset(cfg),
        build_sales_dataset(cfg),
        build_settlements_dataset(cfg),
        build_payments_dataset(cfg),
        build_settlement_exceptions_dataset(cfg),
        build_payment_returns_dataset(cfg),
    ]
