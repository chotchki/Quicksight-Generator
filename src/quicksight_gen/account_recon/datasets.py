"""QuickSight DataSet definitions for Account Recon.

Nine datasets back the four tabs: two dimension tables (ledger_accounts,
subledger_accounts), one fact table (transactions), and six reconciliation
views (ledger_balance_drift, subledger_balance_drift, transfer_summary,
non_zero_transfers, limit_breach, overdraft).
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
# Ledger accounts
# ---------------------------------------------------------------------------

def build_ledger_accounts_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-ledger-accounts-dataset")
    columns = [
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
    ]
    sql = """\
SELECT
    ledger_account_id,
    name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope
FROM ar_ledger_accounts"""
    return _dataset(
        cfg, dataset_id, "AR Ledger Accounts",
        "ar-ledger-accounts", sql, columns,
    )


# ---------------------------------------------------------------------------
# Sub-ledger accounts (joined to ledger for display)
# ---------------------------------------------------------------------------

def build_subledger_accounts_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-subledger-accounts-dataset")
    columns = [
        InputColumn(Name="subledger_account_id", Type="STRING"),
        InputColumn(Name="name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="ledger_name", Type="STRING"),
    ]
    sql = """\
SELECT
    s.subledger_account_id,
    s.name,
    CASE WHEN s.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    s.ledger_account_id,
    la.name AS ledger_name
FROM ar_subledger_accounts s
JOIN ar_ledger_accounts la USING (ledger_account_id)"""
    return _dataset(
        cfg, dataset_id, "AR Sub-Ledger Accounts",
        "ar-subledger-accounts", sql, columns,
    )


# ---------------------------------------------------------------------------
# Transactions (with derived is_failed flag for the Transactions tab)
# ---------------------------------------------------------------------------

def build_transactions_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-transactions-dataset")
    columns = [
        InputColumn(Name="transaction_id", Type="STRING"),
        InputColumn(Name="subledger_account_id", Type="STRING"),
        InputColumn(Name="subledger_name", Type="STRING"),
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="ledger_name", Type="STRING"),
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
    t.subledger_account_id,
    s.name          AS subledger_name,
    s.ledger_account_id,
    la.name         AS ledger_name,
    CASE WHEN s.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    t.transfer_id,
    t.transfer_type,
    t.amount,
    t.posted_at,
    TO_CHAR(t.posted_at, 'YYYY-MM-DD') AS posted_date,
    t.status,
    CASE WHEN t.status = 'failed' THEN 'Failed' ELSE 'OK' END AS is_failed,
    t.memo
FROM ar_transactions t
JOIN ar_subledger_accounts s ON s.subledger_account_id = t.subledger_account_id
JOIN ar_ledger_accounts la   ON la.ledger_account_id   = s.ledger_account_id"""
    return _dataset(
        cfg, dataset_id, "AR Transactions",
        "ar-transactions", sql, columns,
    )


# ---------------------------------------------------------------------------
# Ledger balance drift (stored ledger vs Σ sub-ledgers' stored balances)
# ---------------------------------------------------------------------------

def build_ledger_balance_drift_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-ledger-balance-drift-dataset")
    columns = [
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="ledger_name", Type="STRING"),
        InputColumn(Name="scope", Type="STRING"),
        InputColumn(Name="balance_date", Type="DATETIME"),
        InputColumn(Name="stored_balance", Type="DECIMAL"),
        InputColumn(Name="computed_balance", Type="DECIMAL"),
        InputColumn(Name="drift", Type="DECIMAL"),
        InputColumn(Name="drift_status", Type="STRING"),
    ]
    sql = """\
SELECT
    ledger_account_id,
    ledger_name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope,
    balance_date,
    stored_balance,
    computed_balance,
    drift,
    CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END AS drift_status
FROM ar_ledger_balance_drift"""
    return _dataset(
        cfg, dataset_id, "AR Ledger Balance Drift",
        "ar-ledger-balance-drift", sql, columns,
    )


# ---------------------------------------------------------------------------
# Sub-ledger balance drift (stored sub-ledger vs running Σ posted txns)
# ---------------------------------------------------------------------------

def build_subledger_balance_drift_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-subledger-balance-drift-dataset")
    columns = [
        InputColumn(Name="subledger_account_id", Type="STRING"),
        InputColumn(Name="subledger_name", Type="STRING"),
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="ledger_name", Type="STRING"),
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
    subledger_account_id,
    subledger_name,
    ledger_account_id,
    ledger_name,
    scope,
    balance_date,
    stored_balance,
    computed_balance,
    drift,
    CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END AS drift_status,
    CASE WHEN stored_balance < 0 THEN 'overdraft' ELSE 'ok' END
        AS overdraft_status
FROM ar_subledger_balance_drift"""
    return _dataset(
        cfg, dataset_id, "AR Sub-Ledger Balance Drift",
        "ar-subledger-balance-drift", sql, columns,
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
# Sub-ledger limit breach (per-type daily transfer limit)
# ---------------------------------------------------------------------------

def build_limit_breach_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-limit-breach-dataset")
    columns = [
        InputColumn(Name="subledger_account_id", Type="STRING"),
        InputColumn(Name="subledger_name", Type="STRING"),
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="ledger_name", Type="STRING"),
        InputColumn(Name="activity_date", Type="DATETIME"),
        InputColumn(Name="activity_date_str", Type="STRING"),
        InputColumn(Name="transfer_type", Type="STRING"),
        InputColumn(Name="outbound_total", Type="DECIMAL"),
        InputColumn(Name="daily_limit", Type="DECIMAL"),
        InputColumn(Name="overage", Type="DECIMAL"),
    ]
    sql = """\
SELECT
    subledger_account_id,
    subledger_name,
    ledger_account_id,
    ledger_name,
    activity_date,
    TO_CHAR(activity_date, 'YYYY-MM-DD') AS activity_date_str,
    transfer_type,
    outbound_total,
    daily_limit,
    overage
FROM ar_subledger_limit_breach"""
    return _dataset(
        cfg, dataset_id, "AR Sub-Ledger Limit Breach",
        "ar-limit-breach", sql, columns,
    )


# ---------------------------------------------------------------------------
# Sub-ledger overdraft (stored sub-ledger balance < 0)
# ---------------------------------------------------------------------------

def build_overdraft_dataset(cfg: Config) -> DataSet:
    dataset_id = cfg.prefixed("ar-overdraft-dataset")
    columns = [
        InputColumn(Name="subledger_account_id", Type="STRING"),
        InputColumn(Name="subledger_name", Type="STRING"),
        InputColumn(Name="ledger_account_id", Type="STRING"),
        InputColumn(Name="ledger_name", Type="STRING"),
        InputColumn(Name="balance_date", Type="DATETIME"),
        InputColumn(Name="balance_date_str", Type="STRING"),
        InputColumn(Name="stored_balance", Type="DECIMAL"),
    ]
    sql = """\
SELECT
    subledger_account_id,
    subledger_name,
    ledger_account_id,
    ledger_name,
    balance_date,
    TO_CHAR(balance_date, 'YYYY-MM-DD') AS balance_date_str,
    stored_balance
FROM ar_subledger_overdraft"""
    return _dataset(
        cfg, dataset_id, "AR Sub-Ledger Overdraft",
        "ar-overdraft", sql, columns,
    )


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def build_all_datasets(cfg: Config) -> list[DataSet]:
    return [
        build_ledger_accounts_dataset(cfg),
        build_subledger_accounts_dataset(cfg),
        build_transactions_dataset(cfg),
        build_ledger_balance_drift_dataset(cfg),
        build_subledger_balance_drift_dataset(cfg),
        build_transfer_summary_dataset(cfg),
        build_non_zero_transfers_dataset(cfg),
        build_limit_breach_dataset(cfg),
        build_overdraft_dataset(cfg),
    ]
