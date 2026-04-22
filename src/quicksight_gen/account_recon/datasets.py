"""QuickSight DataSet definitions for Account Recon.

Nine datasets back the four tabs: two dimension tables (ledger_accounts,
subledger_accounts), one fact table (transactions), and six reconciliation
views (ledger_balance_drift, subledger_balance_drift, transfer_summary,
non_zero_transfers, limit_breach, overdraft).
"""

from __future__ import annotations

from quicksight_gen.account_recon.constants import (
    DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
    DS_AR_DAILY_STATEMENT_SUMMARY,
    DS_AR_DAILY_STATEMENT_TRANSACTIONS,
    DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
    DS_AR_LEDGER_ACCOUNTS,
    DS_AR_LEDGER_BALANCE_DRIFT,
    DS_AR_NON_ZERO_TRANSFERS,
    DS_AR_SUBLEDGER_ACCOUNTS,
    DS_AR_SUBLEDGER_BALANCE_DRIFT,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
    DS_AR_UNIFIED_EXCEPTIONS,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnShape,
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
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("subledger_account_id", "STRING",
               shape=ColumnShape.SUBLEDGER_ACCOUNT_ID),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING",
               shape=ColumnShape.LEDGER_ACCOUNT_ID),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("posting_level", "STRING"),
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("origin", "STRING"),
    ColumnSpec("amount", "DECIMAL"),
    ColumnSpec("posted_at", "DATETIME"),
    ColumnSpec("posted_date", "STRING", shape=ColumnShape.DATE_YYYY_MM_DD_TEXT),
    ColumnSpec("status", "STRING"),
    ColumnSpec("is_failed", "STRING"),
    ColumnSpec("memo", "STRING"),
])

LEDGER_BALANCE_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("ledger_account_id", "STRING",
               shape=ColumnShape.LEDGER_ACCOUNT_ID),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("balance_date", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("computed_balance", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("drift_status", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

SUBLEDGER_BALANCE_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("subledger_account_id", "STRING",
               shape=ColumnShape.SUBLEDGER_ACCOUNT_ID),
    ColumnSpec("subledger_name", "STRING"),
    ColumnSpec("ledger_account_id", "STRING",
               shape=ColumnShape.LEDGER_ACCOUNT_ID),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("scope", "STRING"),
    ColumnSpec("balance_date", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("computed_balance", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("drift_status", "STRING"),
    ColumnSpec("overdraft_status", "STRING"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
])

TRANSFER_SUMMARY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("first_posted_at", "DATETIME"),
    ColumnSpec("net_amount", "DECIMAL"),
    ColumnSpec("total_debit", "DECIMAL"),
    ColumnSpec("total_credit", "DECIMAL"),
    ColumnSpec("leg_count", "INTEGER"),
    ColumnSpec("failed_leg_count", "INTEGER"),
    ColumnSpec("net_zero_status", "STRING"),
    ColumnSpec("expected_net_zero", "STRING"),
    ColumnSpec("scope_type", "STRING"),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("origin", "STRING"),
    ColumnSpec("memo", "STRING"),
])

NON_ZERO_TRANSFERS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
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

BALANCE_DRIFT_TIMELINES_ROLLUP_CONTRACT = DatasetContract(columns=[
    ColumnSpec("drift_date", "DATETIME"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("source_check", "STRING"),
])

DAILY_STATEMENT_SUMMARY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING"),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_level", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("opening_balance", "DECIMAL"),
    ColumnSpec("total_debits", "DECIMAL"),
    ColumnSpec("total_credits", "DECIMAL"),
    ColumnSpec("closing_balance_stored", "DECIMAL"),
    ColumnSpec("closing_balance_recomputed", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
    ColumnSpec("drift_status", "STRING"),
    ColumnSpec("leg_count", "INTEGER"),
])

DAILY_STATEMENT_TRANSACTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("account_id", "STRING"),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("balance_date", "DATETIME"),
    ColumnSpec("posted_at", "DATETIME"),
    ColumnSpec("transfer_id", "STRING"),
    ColumnSpec("transfer_type", "STRING"),
    ColumnSpec("origin", "STRING"),
    ColumnSpec("signed_amount", "DECIMAL"),
    ColumnSpec("direction", "STRING"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("memo", "STRING"),
    ColumnSpec("counter_account_name", "STRING"),
])

UNIFIED_EXCEPTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("check_type", "STRING"),
    ColumnSpec("severity", "STRING"),
    ColumnSpec("severity_rank", "INTEGER"),
    ColumnSpec("exception_date", "DATETIME"),
    # YYYY-MM-DD text rendering of exception_date. Used as the
    # SourceField for the "View Transactions for Account-Day" drill
    # so the destination's posted_date filter (also TO_CHAR-formatted
    # YYYY-MM-DD text) matches. Binding a DATETIME column to a
    # SINGLE_VALUED string parameter produces a full timestamp string
    # ("2026-04-07 00:00:00.000") that never matches.
    ColumnSpec("exception_date_str", "STRING",
               shape=ColumnShape.DATE_YYYY_MM_DD_TEXT),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_level", "STRING"),
    ColumnSpec("ledger_account_id", "STRING",
               shape=ColumnShape.LEDGER_ACCOUNT_ID),
    ColumnSpec("ledger_name", "STRING"),
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("primary_amount", "DECIMAL"),
    ColumnSpec("secondary_amount", "DECIMAL"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_ledger_accounts_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT DISTINCT
    account_id                                                AS ledger_account_id,
    account_name                                              AS name,
    CASE WHEN is_internal THEN 'Internal' ELSE 'External' END AS scope
FROM daily_balances
WHERE control_account_id IS NULL"""
    return build_dataset(
        cfg, cfg.prefixed("ar-ledger-accounts-dataset"),
        "AR Ledger Accounts", "ar-ledger-accounts",
        sql, LEDGER_ACCOUNTS_CONTRACT,
        visual_identifier=DS_AR_LEDGER_ACCOUNTS,
    )


def build_subledger_accounts_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT DISTINCT
    sub.account_id                                                AS subledger_account_id,
    sub.account_name                                              AS name,
    CASE WHEN sub.is_internal THEN 'Internal' ELSE 'External' END AS scope,
    sub.control_account_id                                        AS ledger_account_id,
    led.account_name                                              AS ledger_name
FROM daily_balances sub
JOIN daily_balances led
    ON  led.account_id   = sub.control_account_id
    AND led.balance_date = sub.balance_date
WHERE sub.control_account_id IS NOT NULL
  AND led.control_account_id IS NULL"""
    return build_dataset(
        cfg, cfg.prefixed("ar-subledger-accounts-dataset"),
        "AR Sub-Ledger Accounts", "ar-subledger-accounts",
        sql, SUBLEDGER_ACCOUNTS_CONTRACT,
        visual_identifier=DS_AR_SUBLEDGER_ACCOUNTS,
    )


def build_transactions_dataset(cfg: Config) -> DataSet:
    # Phase G: reads from shared `transactions`. Ledger-name lookup goes
    # via the corresponding ledger row in `daily_balances`; external
    # ledgers (no daily balance rows) return NULL ledger_name — acceptable
    # since the visual still shows ledger_account_id.
    #
    # I.4.B Commit 2: no transfer_type WHERE filter. Under the unified-AR
    # framing AR Transactions surfaces every leg in the base table; the
    # Transfer Type multi-select control on the tab lets analysts narrow
    # to AR-only transfer types if they want.
    sql = """\
SELECT
    t.transaction_id,
    t.account_id                                                 AS account_id,
    CASE WHEN t.control_account_id IS NULL THEN NULL ELSE t.account_id END
                                                                 AS subledger_account_id,
    t.account_name                                               AS subledger_name,
    COALESCE(t.control_account_id, t.account_id)                 AS ledger_account_id,
    CASE WHEN t.control_account_id IS NULL
         THEN t.account_name
         ELSE led.account_name
    END                                                          AS ledger_name,
    CASE
        WHEN t.control_account_id IS NULL THEN 'Ledger'
        WHEN t.is_internal THEN 'Internal'
        ELSE 'External'
    END                                                          AS scope,
    CASE
        WHEN t.control_account_id IS NULL THEN 'Ledger'
        ELSE 'Sub-Ledger'
    END                                                          AS posting_level,
    t.transfer_id,
    t.transfer_type,
    t.origin,
    t.signed_amount                                              AS amount,
    t.posted_at,
    TO_CHAR(t.posted_at, 'YYYY-MM-DD')                           AS posted_date,
    t.status,
    CASE WHEN t.status = 'failed' THEN 'Failed' ELSE 'OK' END    AS is_failed,
    t.memo
FROM transactions t
LEFT JOIN (
    SELECT DISTINCT account_id, account_name
    FROM daily_balances
    WHERE control_account_id IS NULL
) led ON led.account_id = t.control_account_id"""
    return build_dataset(
        cfg, cfg.prefixed("ar-transactions-dataset"),
        "AR Transactions", "ar-transactions",
        sql, TRANSACTIONS_CONTRACT,
        visual_identifier=DS_AR_TRANSACTIONS,
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
        visual_identifier=DS_AR_LEDGER_BALANCE_DRIFT,
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
        visual_identifier=DS_AR_SUBLEDGER_BALANCE_DRIFT,
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
    expected_net_zero,
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
        visual_identifier=DS_AR_TRANSFER_SUMMARY,
    )


def build_non_zero_transfers_dataset(cfg: Config) -> DataSet:
    # I.4.B Commit 3: filter on `expected_net_zero = 'expected'` so the
    # Non-Zero Transfers KPI only counts multi-leg transfers whose
    # non-failed legs don't sum to zero. Single-leg PR types (`sale`,
    # `external_txn`) have non-zero net by shape, not by exception.
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
WHERE net_zero_status = 'not_net_zero'
  AND expected_net_zero = 'expected'"""
    return build_dataset(
        cfg, cfg.prefixed("ar-non-zero-transfers-dataset"),
        "AR Non-Zero Transfers", "ar-non-zero-transfers",
        sql, NON_ZERO_TRANSFERS_CONTRACT,
        visual_identifier=DS_AR_NON_ZERO_TRANSFERS,
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
        visual_identifier=DS_AR_EXPECTED_ZERO_EOD_ROLLUP,
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
        visual_identifier=DS_AR_TWO_SIDED_POST_MISMATCH_ROLLUP,
    )


def build_balance_drift_timelines_rollup_dataset(cfg: Config) -> DataSet:
    sql = """\
SELECT
    drift_date,
    drift,
    source_check
FROM ar_balance_drift_timelines_rollup"""
    return build_dataset(
        cfg, cfg.prefixed("ar-balance-drift-timelines-rollup-dataset"),
        "AR Balance Drift Timelines Rollup",
        "ar-balance-drift-timelines-rollup",
        sql, BALANCE_DRIFT_TIMELINES_ROLLUP_CONTRACT,
        visual_identifier=DS_AR_BALANCE_DRIFT_TIMELINES_ROLLUP,
    )


def build_daily_statement_summary_dataset(cfg: Config) -> DataSet:
    # One row per (account_id, balance_date) across every account in the
    # unified base layer (AR and PR alike — I.4 north star: AR is the
    # superset; a PR merchant DDA surfaces naturally when picked).
    # `opening_balance` = prior day's stored balance (window LAG).
    # `closing_balance_recomputed` = opening + Σ non-failed signed_amount
    # posted on the day. `drift` = stored − recomputed; non-zero drift
    # is the single invariant the handbook sheet surfaces visually.
    sql = """\
WITH account_days AS (
    SELECT
        db.account_id,
        db.account_name,
        db.control_account_id,
        db.balance_date,
        db.balance                                                 AS closing_balance_stored,
        LAG(db.balance) OVER (
            PARTITION BY db.account_id ORDER BY db.balance_date
        )                                                          AS opening_balance
    FROM daily_balances db
),
today_flows AS (
    SELECT
        t.account_id,
        t.balance_date,
        SUM(CASE WHEN t.signed_amount > 0 THEN t.signed_amount ELSE 0 END)
                                                                   AS total_debits,
        SUM(CASE WHEN t.signed_amount < 0 THEN -t.signed_amount ELSE 0 END)
                                                                   AS total_credits,
        SUM(t.signed_amount)                                        AS net_flow,
        COUNT(*)                                                    AS leg_count
    FROM transactions t
    WHERE t.status <> 'failed'
    GROUP BY t.account_id, t.balance_date
)
SELECT
    ad.account_id,
    ad.account_name,
    CASE WHEN ad.control_account_id IS NULL
         THEN 'Ledger' ELSE 'Sub-Ledger' END                       AS account_level,
    ad.balance_date,
    COALESCE(ad.opening_balance, 0)                                AS opening_balance,
    COALESCE(f.total_debits, 0)                                    AS total_debits,
    COALESCE(f.total_credits, 0)                                   AS total_credits,
    ad.closing_balance_stored,
    COALESCE(ad.opening_balance, 0) + COALESCE(f.net_flow, 0)      AS closing_balance_recomputed,
    ad.closing_balance_stored
        - (COALESCE(ad.opening_balance, 0) + COALESCE(f.net_flow, 0)) AS drift,
    CASE WHEN ad.closing_balance_stored
              - (COALESCE(ad.opening_balance, 0) + COALESCE(f.net_flow, 0)) = 0
         THEN 'in_balance' ELSE 'drift' END                        AS drift_status,
    COALESCE(f.leg_count, 0)                                        AS leg_count
FROM account_days ad
LEFT JOIN today_flows f
    ON  f.account_id   = ad.account_id
    AND f.balance_date = ad.balance_date"""
    return build_dataset(
        cfg, cfg.prefixed("ar-daily-statement-summary-dataset"),
        "AR Daily Statement Summary", "ar-daily-statement-summary",
        sql, DAILY_STATEMENT_SUMMARY_CONTRACT,
        visual_identifier=DS_AR_DAILY_STATEMENT_SUMMARY,
    )


def build_daily_statement_transactions_dataset(cfg: Config) -> DataSet:
    # One row per leg, across every account-day in the unified base
    # layer. QS sheet-local filters narrow to the selected
    # (account_id, balance_date) slice.
    # `counter_account_name` aggregates the account_names of the other
    # legs in the same transfer via STRING_AGG (SQL:2008, portable).
    sql = """\
SELECT
    t.transaction_id,
    t.account_id,
    t.account_name,
    t.balance_date,
    t.posted_at,
    t.transfer_id,
    t.transfer_type,
    t.origin,
    t.signed_amount,
    CASE WHEN t.signed_amount > 0 THEN 'Debit' ELSE 'Credit' END   AS direction,
    t.status,
    t.memo,
    (
        SELECT STRING_AGG(DISTINCT other.account_name, ', ')
        FROM transactions other
        WHERE other.transfer_id    = t.transfer_id
          AND other.transaction_id <> t.transaction_id
    )                                                              AS counter_account_name
FROM transactions t"""
    return build_dataset(
        cfg, cfg.prefixed("ar-daily-statement-transactions-dataset"),
        "AR Daily Statement Transactions", "ar-daily-statement-transactions",
        sql, DAILY_STATEMENT_TRANSACTIONS_CONTRACT,
        visual_identifier=DS_AR_DAILY_STATEMENT_TRANSACTIONS,
    )


def build_ar_unified_exceptions_dataset(cfg: Config) -> DataSet:
    # The 14-block UNION ALL that produces these rows lives in schema.sql
    # as the `ar_unified_exceptions` materialized view. The full plan
    # (14 per-check views, each scanning `transactions` and/or
    # `daily_balances`) was too heavy for QuickSight Direct Query — the
    # Today's Exceptions sheet wouldn't render. Materializing makes load
    # instant. Operators must REFRESH MATERIALIZED VIEW after each ETL
    # load (the demo's `quicksight-gen demo apply` does this
    # automatically). See schema.sql for the matview definition.
    sql = (
        "SELECT *, TO_CHAR(exception_date, 'YYYY-MM-DD') AS exception_date_str "
        "FROM ar_unified_exceptions"
    )
    return build_dataset(
        cfg, cfg.prefixed("ar-unified-exceptions-dataset"),
        "AR Unified Exceptions", "ar-unified-exceptions",
        sql, UNIFIED_EXCEPTIONS_CONTRACT,
        visual_identifier=DS_AR_UNIFIED_EXCEPTIONS,
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
        build_expected_zero_eod_rollup_dataset(cfg),
        build_two_sided_post_mismatch_rollup_dataset(cfg),
        build_balance_drift_timelines_rollup_dataset(cfg),
        build_daily_statement_summary_dataset(cfg),
        build_daily_statement_transactions_dataset(cfg),
        build_ar_unified_exceptions_dataset(cfg),
    ]
