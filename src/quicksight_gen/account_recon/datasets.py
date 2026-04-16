"""QuickSight DataSet definitions for Account Recon.

Nine datasets back the four tabs: two dimension tables (ledger_accounts,
subledger_accounts), one fact table (transactions), and six reconciliation
views (ledger_balance_drift, subledger_balance_drift, transfer_summary,
non_zero_transfers, limit_breach, overdraft).
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnSpec,
    DatasetContract,
    build_dataset,
)
from quicksight_gen.common.models import DataSet


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

LEDGER_ACCOUNTS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("name", "STRING"),
    ColumnSpec("scope", "STRING"),
])

SUBLEDGER_ACCOUNTS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
])

TRANSACTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("origin", "STRING"),
    ColumnSpec("amount", "DECIMAL"),
    ColumnSpec("posted_at", "DATETIME"),
    ColumnSpec("posted_date", "STRING"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("is_failed", "STRING"),
    ColumnSpec("memo", "STRING"),
])

LEDGER_BALANCE_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("computed_balance", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("drift_status", "STRING"),
])

SUBLEDGER_BALANCE_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("computed_balance", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("drift_status", "STRING"),
    ColumnSpec("overdraft_status", "STRING"),
])

TRANSFER_SUMMARY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("first_posted_at", "DATETIME"),
    ColumnSpec("net_amount", "DECIMAL"),
    ColumnSpec("total_debit", "DECIMAL"),
    ColumnSpec("total_credit", "DECIMAL"),
    ColumnSpec("leg_count", "INTEGER"),
    ColumnSpec("failed_leg_count", "INTEGER"),
    ColumnSpec("net_zero_status", "STRING"),
    ColumnSpec("scope_type", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("memo", "STRING"),
])

NON_ZERO_TRANSFERS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("first_posted_at", "DATETIME"),
    ColumnSpec("net_amount", "DECIMAL"),
    ColumnSpec("total_debit", "DECIMAL"),
    ColumnSpec("total_credit", "DECIMAL"),
    ColumnSpec("leg_count", "INTEGER"),
    ColumnSpec("failed_leg_count", "INTEGER"),
    ColumnSpec("memo", "STRING"),
])

LIMIT_BREACH_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("activity_date", "DATETIME"),
    ColumnSpec("activity_date_str", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("outbound_total", "DECIMAL"),
    ColumnSpec("daily_limit", "DECIMAL"),
    ColumnSpec("overage", "DECIMAL"),
])

OVERDRAFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("balance_date_str", "STRING"),
    ColumnSpec("stored_balance", "DECIMAL"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_ledger_accounts_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    ledger_account_id,
    name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope
FROM ar_ledger_accounts"""
    return build_dataset(
        cfg, cfg.prefixed("ar-ledger-accounts-dataset"),
        "AR Ledger Accounts", "ar-ledger-accounts",
        sql, LEDGER_ACCOUNTS_CONTRACT,
    )


def build_subledger_accounts_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    s.subledger_account_id,
    s.name,
    CASE WHEN s.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    s.ledger_account_id,
    la.name AS ledger_name
FROM ar_subledger_accounts s
JOIN ar_ledger_accounts la USING (ledger_account_id)"""
    return build_dataset(
        cfg, cfg.prefixed("ar-subledger-accounts-dataset"),
        "AR Sub-Ledger Accounts", "ar-subledger-accounts",
        sql, SUBLEDGER_ACCOUNTS_CONTRACT,
    )


def build_transactions_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    p.posting_id                                                AS transaction_id,
    p.subledger_account_id,
    s.name                                                      AS subledger_name,
    s.ledger_account_id,
    la.name                                                     AS ledger_name,
    CASE WHEN s.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    p.transfer_id,
    xfer.transfer_type,
    xfer.origin,
    p.signed_amount                                             AS amount,
    p.posted_at,
    TO_CHAR(p.posted_at, 'YYYY-MM-DD')                         AS posted_date,
    p.status,
    CASE WHEN p.status = 'failed' THEN 'Failed' ELSE 'OK' END  AS is_failed,
    xfer.memo
FROM posting p
JOIN transfer xfer               ON xfer.transfer_id          = p.transfer_id
JOIN ar_subledger_accounts s     ON s.subledger_account_id    = p.subledger_account_id
JOIN ar_ledger_accounts la       ON la.ledger_account_id      = s.ledger_account_id
WHERE xfer.transfer_type IN ('ach', 'wire', 'internal', 'cash')"""
    return build_dataset(
        cfg, cfg.prefixed("ar-transactions-dataset"),
        "AR Transactions", "ar-transactions",
        sql, TRANSACTIONS_CONTRACT,
    )


def build_ledger_balance_drift_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("ar-ledger-balance-drift-dataset"),
        "AR Ledger Balance Drift", "ar-ledger-balance-drift",
        sql, LEDGER_BALANCE_DRIFT_CONTRACT,
    )


def build_subledger_balance_drift_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("ar-subledger-balance-drift-dataset"),
        "AR Sub-Ledger Balance Drift", "ar-subledger-balance-drift",
        sql, SUBLEDGER_BALANCE_DRIFT_CONTRACT,
    )


def build_transfer_summary_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("ar-transfer-summary-dataset"),
        "AR Transfer Summary", "ar-transfer-summary",
        sql, TRANSFER_SUMMARY_CONTRACT,
    )


def build_non_zero_transfers_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("ar-non-zero-transfers-dataset"),
        "AR Non-Zero Transfers", "ar-non-zero-transfers",
        sql, NON_ZERO_TRANSFERS_CONTRACT,
    )


def build_limit_breach_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("ar-limit-breach-dataset"),
        "AR Sub-Ledger Limit Breach", "ar-limit-breach",
        sql, LIMIT_BREACH_CONTRACT,
    )


def build_overdraft_dataset(cfg: Config) -> DataSet:
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
    return build_dataset(
        cfg, cfg.prefixed("ar-overdraft-dataset"),
        "AR Sub-Ledger Overdraft", "ar-overdraft",
        sql, OVERDRAFT_CONTRACT,
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
