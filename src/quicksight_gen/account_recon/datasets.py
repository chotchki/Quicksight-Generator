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


def _aging_columns(date_expr: str) -> str:
    """SQL fragment for days_outstanding + aging_bucket from a date expression."""
    return f"""\
    (CURRENT_DATE - {date_expr}::date) AS days_outstanding,
    CASE
        WHEN (CURRENT_DATE - {date_expr}::date) <= 1 THEN '1: 0-1 day'
        WHEN (CURRENT_DATE - {date_expr}::date) <= 3 THEN '2: 2-3 days'
        WHEN (CURRENT_DATE - {date_expr}::date) <= 7 THEN '3: 4-7 days'
        WHEN (CURRENT_DATE - {date_expr}::date) <= 30 THEN '4: 8-30 days'
        ELSE '5: >30 days'
    END AS aging_bucket"""


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
    ColumnSpec("posting_level", "STRING"),
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
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
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
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
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
    ColumnSpec("origin", "STRING"),
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
    ColumnSpec("origin", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
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
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

OVERDRAFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("balance_date_str", "STRING"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

SWEEP_TARGET_NONZERO_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING"),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("balance_date_str", "STRING"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

CONCENTRATION_MASTER_SWEEP_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("sweep_date", "DATETIME"),
    ColumnSpec("master_total", "DECIMAL"),
    ColumnSpec("subaccount_total", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("abs_drift", "DECIMAL"),
])

ACH_ORIG_SETTLEMENT_NONZERO_CONTRACT = DatasetContract(columns=[
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("balance_date_str", "STRING"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

ACH_SWEEP_NO_FED_CONFIRMATION_CONTRACT = DatasetContract(columns=[
    ColumnSpec("sweep_transfer_id", "STRING"),
    ColumnSpec("sweep_at", "DATETIME"),
    ColumnSpec("sweep_at_str", "STRING"),
    ColumnSpec("sweep_amount", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

FED_CARD_NO_INTERNAL_CATCHUP_CONTRACT = DatasetContract(columns=[
    ColumnSpec("fed_transfer_id", "STRING"),
    ColumnSpec("fed_at", "DATETIME"),
    ColumnSpec("fed_at_str", "STRING"),
    ColumnSpec("fed_amount", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

GL_VS_FED_MASTER_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("movement_date", "DATETIME"),
    ColumnSpec("fed_total", "DECIMAL"),
    ColumnSpec("internal_total", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("abs_drift", "DECIMAL"),
])

INTERNAL_TRANSFER_STUCK_CONTRACT = DatasetContract(columns=[
    ColumnSpec("originate_transfer_id", "STRING"),
    ColumnSpec("originated_at", "DATETIME"),
    ColumnSpec("originated_at_str", "STRING"),
    ColumnSpec("originate_amount", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

INTERNAL_TRANSFER_SUSPENSE_NONZERO_CONTRACT = DatasetContract(columns=[
    ColumnSpec("ledger_account_id", "STRING"),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("balance_date_str", "STRING"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

INTERNAL_REVERSAL_UNCREDITED_CONTRACT = DatasetContract(columns=[
    ColumnSpec("originate_transfer_id", "STRING"),
    ColumnSpec("originated_at", "DATETIME"),
    ColumnSpec("originated_at_str", "STRING"),
    ColumnSpec("originate_amount", "DECIMAL"),
    ColumnSpec("reversal_transfer_id", "STRING"),
    ColumnSpec("reversal_at", "DATETIME"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

EXPECTED_ZERO_EOD_ROLLUP_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING"),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_level", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("source_check", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

TWO_SIDED_POST_MISMATCH_ROLLUP_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("observed_at", "DATETIME"),
    ColumnSpec("amount", "DECIMAL"),
    ColumnSpec("side_present", "STRING"),
    ColumnSpec("side_missing", "STRING"),
    ColumnSpec("source_check", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
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
    p.posting_id                                                         AS transaction_id,
    p.subledger_account_id,
    COALESCE(s.name, la.name)                                            AS subledger_name,
    p.ledger_account_id,
    la.name                                                              AS ledger_name,
    CASE
        WHEN s.subledger_account_id IS NULL THEN 'Ledger'
        WHEN s.is_internal THEN 'Internal'
        ELSE 'External'
    END                                                                  AS scope,
    CASE
        WHEN p.subledger_account_id IS NULL THEN 'Ledger'
        ELSE 'Sub-Ledger'
    END                                                                  AS posting_level,
    p.transfer_id,
    xfer.transfer_type,
    xfer.origin,
    p.signed_amount                                                      AS amount,
    p.posted_at,
    TO_CHAR(p.posted_at, 'YYYY-MM-DD')                                  AS posted_date,
    p.status,
    CASE WHEN p.status = 'failed' THEN 'Failed' ELSE 'OK' END           AS is_failed,
    xfer.memo
FROM posting p
JOIN transfer xfer               ON xfer.transfer_id          = p.transfer_id
JOIN ar_ledger_accounts la       ON la.ledger_account_id      = p.ledger_account_id
LEFT JOIN ar_subledger_accounts s ON s.subledger_account_id   = p.subledger_account_id
WHERE xfer.transfer_type IN ('ach', 'wire', 'internal', 'cash', 'funding_batch', 'fee', 'clearing_sweep')"""
    return build_dataset(
        cfg, cfg.prefixed("ar-transactions-dataset"),
        "AR Transactions", "ar-transactions",
        sql, TRANSACTIONS_CONTRACT,
    )


def build_ledger_balance_drift_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    ledger_account_id,
    ledger_name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope,
    balance_date,
    stored_balance,
    computed_balance,
    drift,
    CASE WHEN drift = 0 THEN 'in_balance' ELSE 'drift' END AS drift_status,
{_aging_columns('balance_date')}
FROM ar_ledger_balance_drift"""
    return build_dataset(
        cfg, cfg.prefixed("ar-ledger-balance-drift-dataset"),
        "AR Ledger Balance Drift", "ar-ledger-balance-drift",
        sql, LEDGER_BALANCE_DRIFT_CONTRACT,
    )


def build_subledger_balance_drift_dataset(cfg: Config) -> DataSet:
    sql = f"""\
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
        AS overdraft_status,
{_aging_columns('balance_date')}
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
    origin,
    memo
FROM ar_transfer_summary"""
    return build_dataset(
        cfg, cfg.prefixed("ar-transfer-summary-dataset"),
        "AR Transfer Summary", "ar-transfer-summary",
        sql, TRANSFER_SUMMARY_CONTRACT,
    )


def build_non_zero_transfers_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    transfer_id,
    first_posted_at,
    net_amount,
    total_debit,
    total_credit,
    leg_count,
    failed_leg_count,
    origin,
{_aging_columns('first_posted_at')},
    memo
FROM ar_transfer_summary
WHERE net_zero_status = 'not_net_zero'"""
    return build_dataset(
        cfg, cfg.prefixed("ar-non-zero-transfers-dataset"),
        "AR Non-Zero Transfers", "ar-non-zero-transfers",
        sql, NON_ZERO_TRANSFERS_CONTRACT,
    )


def build_limit_breach_dataset(cfg: Config) -> DataSet:
    sql = f"""\
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
    overage,
{_aging_columns('activity_date')}
FROM ar_subledger_limit_breach"""
    return build_dataset(
        cfg, cfg.prefixed("ar-limit-breach-dataset"),
        "AR Sub-Ledger Limit Breach", "ar-limit-breach",
        sql, LIMIT_BREACH_CONTRACT,
    )


def build_overdraft_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    subledger_account_id,
    subledger_name,
    ledger_account_id,
    ledger_name,
    balance_date,
    TO_CHAR(balance_date, 'YYYY-MM-DD') AS balance_date_str,
    stored_balance,
{_aging_columns('balance_date')}
FROM ar_subledger_overdraft"""
    return build_dataset(
        cfg, cfg.prefixed("ar-overdraft-dataset"),
        "AR Sub-Ledger Overdraft", "ar-overdraft",
        sql, OVERDRAFT_CONTRACT,
    )


def build_sweep_target_nonzero_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    subledger_account_id,
    subledger_name,
    ledger_account_id,
    ledger_name,
    balance_date,
    TO_CHAR(balance_date, 'YYYY-MM-DD') AS balance_date_str,
    stored_balance,
{_aging_columns('balance_date')}
FROM ar_sweep_target_nonzero"""
    return build_dataset(
        cfg, cfg.prefixed("ar-sweep-target-nonzero-dataset"),
        "AR Sweep Target Non-Zero EOD", "ar-sweep-target-nonzero",
        sql, SWEEP_TARGET_NONZERO_CONTRACT,
    )


def build_concentration_master_sweep_drift_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    sweep_date,
    master_total,
    subaccount_total,
    drift,
    ABS(drift) AS abs_drift
FROM ar_concentration_master_sweep_drift"""
    return build_dataset(
        cfg, cfg.prefixed("ar-concentration-master-sweep-drift-dataset"),
        "AR Concentration Master Sweep Drift",
        "ar-concentration-master-sweep-drift",
        sql, CONCENTRATION_MASTER_SWEEP_DRIFT_CONTRACT,
    )


def build_ach_orig_settlement_nonzero_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    ledger_account_id,
    ledger_name,
    balance_date,
    TO_CHAR(balance_date, 'YYYY-MM-DD') AS balance_date_str,
    stored_balance,
{_aging_columns('balance_date')}
FROM ar_ach_orig_settlement_nonzero"""
    return build_dataset(
        cfg, cfg.prefixed("ar-ach-orig-settlement-nonzero-dataset"),
        "AR ACH Origination Settlement Non-Zero EOD",
        "ar-ach-orig-settlement-nonzero",
        sql, ACH_ORIG_SETTLEMENT_NONZERO_CONTRACT,
    )


def build_ach_sweep_no_fed_confirmation_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    sweep_transfer_id,
    sweep_at,
    TO_CHAR(sweep_at, 'YYYY-MM-DD') AS sweep_at_str,
    sweep_amount,
{_aging_columns('sweep_at')}
FROM ar_ach_sweep_no_fed_confirmation"""
    return build_dataset(
        cfg, cfg.prefixed("ar-ach-sweep-no-fed-confirmation-dataset"),
        "AR ACH Internal Sweep Without Fed Confirmation",
        "ar-ach-sweep-no-fed-confirmation",
        sql, ACH_SWEEP_NO_FED_CONFIRMATION_CONTRACT,
    )


def build_fed_card_no_internal_catchup_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    fed_transfer_id,
    fed_at,
    TO_CHAR(fed_at, 'YYYY-MM-DD') AS fed_at_str,
    fed_amount,
{_aging_columns('fed_at')}
FROM ar_fed_card_no_internal_catchup"""
    return build_dataset(
        cfg, cfg.prefixed("ar-fed-card-no-internal-catchup-dataset"),
        "AR Fed Activity Without Internal Catch-Up",
        "ar-fed-card-no-internal-catchup",
        sql, FED_CARD_NO_INTERNAL_CATCHUP_CONTRACT,
    )


def build_gl_vs_fed_master_drift_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    movement_date,
    fed_total,
    internal_total,
    drift,
    ABS(drift) AS abs_drift
FROM ar_gl_vs_fed_master_drift"""
    return build_dataset(
        cfg, cfg.prefixed("ar-gl-vs-fed-master-drift-dataset"),
        "AR GL vs Fed Master Drift", "ar-gl-vs-fed-master-drift",
        sql, GL_VS_FED_MASTER_DRIFT_CONTRACT,
    )


def build_internal_transfer_stuck_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    originate_transfer_id,
    originated_at,
    TO_CHAR(originated_at, 'YYYY-MM-DD') AS originated_at_str,
    originate_amount,
{_aging_columns('originated_at')}
FROM ar_internal_transfer_stuck"""
    return build_dataset(
        cfg, cfg.prefixed("ar-internal-transfer-stuck-dataset"),
        "AR Internal Transfer Stuck in Suspense",
        "ar-internal-transfer-stuck",
        sql, INTERNAL_TRANSFER_STUCK_CONTRACT,
    )


def build_internal_transfer_suspense_nonzero_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    ledger_account_id,
    ledger_name,
    balance_date,
    TO_CHAR(balance_date, 'YYYY-MM-DD') AS balance_date_str,
    stored_balance,
{_aging_columns('balance_date')}
FROM ar_internal_transfer_suspense_nonzero"""
    return build_dataset(
        cfg, cfg.prefixed("ar-internal-transfer-suspense-nonzero-dataset"),
        "AR Internal Transfer Suspense Non-Zero EOD",
        "ar-internal-transfer-suspense-nonzero",
        sql, INTERNAL_TRANSFER_SUSPENSE_NONZERO_CONTRACT,
    )


def build_internal_reversal_uncredited_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    originate_transfer_id,
    originated_at,
    TO_CHAR(originated_at, 'YYYY-MM-DD') AS originated_at_str,
    originate_amount,
    reversal_transfer_id,
    reversal_at,
{_aging_columns('originated_at')}
FROM ar_internal_reversal_uncredited"""
    return build_dataset(
        cfg, cfg.prefixed("ar-internal-reversal-uncredited-dataset"),
        "AR Internal Reversal Uncredited",
        "ar-internal-reversal-uncredited",
        sql, INTERNAL_REVERSAL_UNCREDITED_CONTRACT,
    )


def build_expected_zero_eod_rollup_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    account_id,
    account_name,
    account_level,
    balance_date,
    stored_balance,
    source_check,
{_aging_columns('balance_date')}
FROM ar_expected_zero_eod_rollup"""
    return build_dataset(
        cfg, cfg.prefixed("ar-expected-zero-eod-rollup-dataset"),
        "AR Expected-Zero EOD Rollup", "ar-expected-zero-eod-rollup",
        sql, EXPECTED_ZERO_EOD_ROLLUP_CONTRACT,
    )


def build_two_sided_post_mismatch_rollup_dataset(cfg: Config) -> DataSet:
    sql = f"""\
SELECT
    transfer_id,
    observed_at,
    amount,
    side_present,
    side_missing,
    source_check,
{_aging_columns('observed_at')}
FROM ar_two_sided_post_mismatch_rollup"""
    return build_dataset(
        cfg, cfg.prefixed("ar-two-sided-post-mismatch-rollup-dataset"),
        "AR Two-Sided Post Mismatch Rollup",
        "ar-two-sided-post-mismatch-rollup",
        sql, TWO_SIDED_POST_MISMATCH_ROLLUP_CONTRACT,
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
        build_sweep_target_nonzero_dataset(cfg),
        build_concentration_master_sweep_drift_dataset(cfg),
        build_ach_orig_settlement_nonzero_dataset(cfg),
        build_ach_sweep_no_fed_confirmation_dataset(cfg),
        build_fed_card_no_internal_catchup_dataset(cfg),
        build_gl_vs_fed_master_drift_dataset(cfg),
        build_internal_transfer_stuck_dataset(cfg),
        build_internal_transfer_suspense_nonzero_dataset(cfg),
        build_internal_reversal_uncredited_dataset(cfg),
        build_expected_zero_eod_rollup_dataset(cfg),
        build_two_sided_post_mismatch_rollup_dataset(cfg),
    ]
