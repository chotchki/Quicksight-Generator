"""QuickSight DataSet definitions for Account Recon.

Seven datasets back the four tabs: two dimension tables (parent_accounts,
accounts), one fact table (transactions), and four reconciliation views
(parent_balance_drift, account_balance_drift, transfer_summary,
non_zero_transfers).
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    CustomSql,
    DataSet,
    DataSetUsageConfiguration,
    InputColumn,
    LogicalTable,
    LogicalTableSource,
    PhysicalTable,
    ResourcePermission,
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


def _dataset(
    cfg: Config,
    dataset_id: str,
    name: str,
    table_key: str,
    sql: str,
    columns: list[InputColumn],
) -> DataSet:
    physical, logical = _physical_and_logical(
        cfg, table_key, name, sql, columns,
    )
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name=name,
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=_permissions(cfg),
        Tags=cfg.tags(),
    )


# ---------------------------------------------------------------------------
# Parent accounts
# ---------------------------------------------------------------------------

def build_parent_accounts_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-parent-accounts-dataset")
    columns = [
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
    ]
    sql = """\
SELECT
    parent_account_id,
    name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope
FROM ar_parent_accounts"""
    return _dataset(
        cfg, dataset_id, "AR Parent Accounts",
        "ar-parent-accounts", sql, columns,
    )


# ---------------------------------------------------------------------------
# Accounts (child accounts joined to parent for display)
# ---------------------------------------------------------------------------

def build_accounts_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-accounts-dataset")
    columns = [
        InputColumn(Name="account_id", Type="STRING"),
        InputColumn(Name="name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="parent_name", Type="STRING"),
    ]
    sql = """\
SELECT
    a.account_id,
    a.name,
    CASE WHEN a.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    a.parent_account_id,
    p.name AS parent_name
FROM ar_accounts a
JOIN ar_parent_accounts p USING (parent_account_id)"""
    return _dataset(
        cfg, dataset_id, "AR Accounts",
        "ar-accounts", sql, columns,
    )


# ---------------------------------------------------------------------------
# Transactions (with derived is_failed flag for the Transactions tab)
# ---------------------------------------------------------------------------

def build_transactions_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-transactions-dataset")
    columns = [
        InputColumn(Name="transaction_id", Type="STRING"),
        InputColumn(Name="account_id", Type="STRING"),
        InputColumn(Name="account_name", Type="STRING"),
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="parent_name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
        InputColumn(Name="transfer_id", Type="STRING"),
        InputColumn(Name="transfer_type", Type="STRING"),
        InputColumn(Name="amount", Type="DECIMAL"),
        InputColumn(Name="posted_at", Type="DATETIME"),
        InputColumn(Name="posted_date", Type="STRING"),
        InputColumn(Name="status", Type="STRING"),
        InputColumn(Name="is_failed", Type="STRING"),
        InputColumn(Name="memo", Type="STRING"),
    ]
    sql = """\
SELECT
    t.transaction_id,
    t.account_id,
    a.name          AS account_name,
    a.parent_account_id,
    p.name          AS parent_name,
    CASE WHEN a.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    t.transfer_id,
    t.transfer_type,
    t.amount,
    t.posted_at,
    TO_CHAR(t.posted_at, 'YYYY-MM-DD') AS posted_date,
    t.status,
    CASE WHEN t.status = 'failed' THEN 'Failed' ELSE 'OK' END AS is_failed,
    t.memo
FROM ar_transactions t
JOIN ar_accounts a        ON a.account_id = t.account_id
JOIN ar_parent_accounts p ON p.parent_account_id = a.parent_account_id"""
    return _dataset(
        cfg, dataset_id, "AR Transactions",
        "ar-transactions", sql, columns,
    )


# ---------------------------------------------------------------------------
# Parent balance drift (stored parent vs Σ children's stored balances)
# ---------------------------------------------------------------------------

def build_parent_balance_drift_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-parent-balance-drift-dataset")
    columns = [
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="parent_name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
        InputColumn(Name="balance_date", Type="DATETIME"),
        InputColumn(Name="stored_balance", Type="DECIMAL"),
        InputColumn(Name="computed_balance", Type="DECIMAL"),
        InputColumn(Name="drift", Type="DECIMAL"),
        InputColumn(Name="drift_status", Type="STRING"),
    ]
    sql = """\
SELECT
    parent_account_id,
    parent_name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope,
    balance_date,
    stored_balance,
    computed_balance,
    drift,
    CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END AS drift_status
FROM ar_parent_balance_drift"""
    return _dataset(
        cfg, dataset_id, "AR Parent Balance Drift",
        "ar-parent-balance-drift", sql, columns,
    )


# ---------------------------------------------------------------------------
# Child-account balance drift (stored child vs running Σ posted txns)
# ---------------------------------------------------------------------------

def build_account_balance_drift_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-account-balance-drift-dataset")
    columns = [
        InputColumn(Name="account_id", Type="STRING"),
        InputColumn(Name="account_name", Type="STRING"),
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="parent_name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
        InputColumn(Name="balance_date", Type="DATETIME"),
        InputColumn(Name="stored_balance", Type="DECIMAL"),
        InputColumn(Name="computed_balance", Type="DECIMAL"),
        InputColumn(Name="drift", Type="DECIMAL"),
        InputColumn(Name="drift_status", Type="STRING"),
        InputColumn(Name="overdraft_status", Type="STRING"),
    ]
    sql = """\
SELECT
    account_id,
    account_name,
    parent_account_id,
    parent_name,
    scope,
    balance_date,
    stored_balance,
    computed_balance,
    drift,
    CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END AS drift_status,
    CASE WHEN stored_balance < 0 THEN 'overdraft' ELSE 'ok' END
        AS overdraft_status
FROM ar_account_balance_drift"""
    return _dataset(
        cfg, dataset_id, "AR Account Balance Drift",
        "ar-account-balance-drift", sql, columns,
    )


# ---------------------------------------------------------------------------
# Transfer summary (all transfers, with net-zero status + memo)
# ---------------------------------------------------------------------------

def build_transfer_summary_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-transfer-summary-dataset")
    columns = [
        InputColumn(Name="transfer_id", Type="STRING"),
        InputColumn(Name="first_posted_at", Type="DATETIME"),
        InputColumn(Name="net_amount", Type="DECIMAL"),
        InputColumn(Name="total_debit", Type="DECIMAL"),
        InputColumn(Name="total_credit", Type="DECIMAL"),
        InputColumn(Name="leg_count", Type="INTEGER"),
        InputColumn(Name="failed_leg_count", Type="INTEGER"),
        InputColumn(Name="net_zero_status", Type="STRING"),
        InputColumn(Name="scope_type", Type="STRING"),
        InputColumn(Name="transfer_type", Type="STRING"),
        InputColumn(Name="memo", Type="STRING"),
    ]
    sql = """\
SELECT
    transfer_id,
    first_posted_at,
    net_amount,
    total_debit,
    total_credit,
    leg_count,
    failed_leg_count,
    net_zero_status,
    CASE WHEN has_external_leg THEN 'cross_scope' ELSE 'internal_only' END
        AS scope_type,
    transfer_type,
    memo
FROM ar_transfer_summary"""
    return _dataset(
        cfg, dataset_id, "AR Transfer Summary",
        "ar-transfer-summary", sql, columns,
    )


# ---------------------------------------------------------------------------
# Non-zero transfers (exceptions view — only the unhealthy ones)
# ---------------------------------------------------------------------------

def build_non_zero_transfers_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-non-zero-transfers-dataset")
    columns = [
        InputColumn(Name="transfer_id", Type="STRING"),
        InputColumn(Name="first_posted_at", Type="DATETIME"),
        InputColumn(Name="net_amount", Type="DECIMAL"),
        InputColumn(Name="total_debit", Type="DECIMAL"),
        InputColumn(Name="total_credit", Type="DECIMAL"),
        InputColumn(Name="leg_count", Type="INTEGER"),
        InputColumn(Name="failed_leg_count", Type="INTEGER"),
        InputColumn(Name="memo", Type="STRING"),
    ]
    sql = """\
SELECT
    transfer_id,
    first_posted_at,
    net_amount,
    total_debit,
    total_credit,
    leg_count,
    failed_leg_count,
    memo
FROM ar_transfer_summary
WHERE net_zero_status = 'not_net_zero'"""
    return _dataset(
        cfg, dataset_id, "AR Non-Zero Transfers",
        "ar-non-zero-transfers", sql, columns,
    )


# ---------------------------------------------------------------------------
# Child limit breach (Phase 5 — per-type daily transfer limit)
# ---------------------------------------------------------------------------

def build_limit_breach_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-limit-breach-dataset")
    columns = [
        InputColumn(Name="account_id", Type="STRING"),
        InputColumn(Name="account_name", Type="STRING"),
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="parent_name", Type="STRING"),
        InputColumn(Name="activity_date", Type="DATETIME"),
        InputColumn(Name="activity_date_str", Type="STRING"),
        InputColumn(Name="transfer_type", Type="STRING"),
        InputColumn(Name="outbound_total", Type="DECIMAL"),
        InputColumn(Name="daily_limit", Type="DECIMAL"),
        InputColumn(Name="overage", Type="DECIMAL"),
    ]
    sql = """\
SELECT
    account_id,
    account_name,
    parent_account_id,
    parent_name,
    activity_date,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS activity_date_str,
    transfer_type,
    outbound_total,
    daily_limit,
    overage
FROM ar_child_limit_breach"""
    return _dataset(
        cfg, dataset_id, "AR Child Limit Breach",
        "ar-limit-breach", sql, columns,
    )


# ---------------------------------------------------------------------------
# Child overdraft (Phase 5 — stored child balance < 0)
# ---------------------------------------------------------------------------

def build_overdraft_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-overdraft-dataset")
    columns = [
        InputColumn(Name="account_id", Type="STRING"),
        InputColumn(Name="account_name", Type="STRING"),
        InputColumn(Name="parent_account_id", Type="STRING"),
        InputColumn(Name="parent_name", Type="STRING"),
        InputColumn(Name="balance_date", Type="DATETIME"),
        InputColumn(Name="balance_date_str", Type="STRING"),
        InputColumn(Name="stored_balance", Type="DECIMAL"),
    ]
    sql = """\
SELECT
    account_id,
    account_name,
    parent_account_id,
    parent_name,
    balance_date,
    TO_CHAR(balance_date, 'YYYY-MM-DD') AS balance_date_str,
    stored_balance
FROM ar_child_overdraft"""
    return _dataset(
        cfg, dataset_id, "AR Child Overdraft",
        "ar-overdraft", sql, columns,
    )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def build_all_datasets(cfg: Config) -> list[DataSet]:
    return [
        build_parent_accounts_dataset(cfg),
        build_accounts_dataset(cfg),
        build_transactions_dataset(cfg),
        build_parent_balance_drift_dataset(cfg),
        build_account_balance_drift_dataset(cfg),
        build_transfer_summary_dataset(cfg),
        build_non_zero_transfers_dataset(cfg),
        build_limit_breach_dataset(cfg),
        build_overdraft_dataset(cfg),
    ]
