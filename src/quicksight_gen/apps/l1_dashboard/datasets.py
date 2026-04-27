"""QuickSight DataSet builders for the L1 Dashboard app.

Each builder wraps one M.1a.7 L1 invariant view. The SQL is intentionally
trivial (`SELECT * FROM <prefix>_<view>`) — the views already do the
filtering, computation, and shape work. Datasets here are thin façades
that surface columns to QuickSight visuals via the dataset contract.

The visual_identifier convention is ``l1-<viewname>-ds`` so every
dataset's logical name traces back to the underlying L1 invariant.

Substep landmarks:
    M.2a.3 — drift + ledger_drift datasets
    M.2a.4 — overdraft dataset
    M.2a.5 — limit_breach dataset
    M.2a.6 — today's exceptions UNION dataset (this commit)
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnShape,
    ColumnSpec,
    DatasetContract,
    build_dataset,
)
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.models import DataSet


# Visual identifiers — keys for the Dataset registry on App.
DS_DRIFT = "l1-drift-ds"
DS_LEDGER_DRIFT = "l1-ledger-drift-ds"
DS_OVERDRAFT = "l1-overdraft-ds"
DS_LIMIT_BREACH = "l1-limit-breach-ds"
DS_TODAYS_EXCEPTIONS = "l1-todays-exceptions-ds"
DS_DAILY_STATEMENT_SUMMARY = "l1-daily-statement-summary-ds"
DS_DAILY_STATEMENT_TRANSACTIONS = "l1-daily-statement-transactions-ds"
DS_TRANSACTIONS = "l1-transactions-ds"


# Contracts — column shapes the M.1a.7 views project.
DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("business_day_start", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("business_day_end", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("computed_balance", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
])


LEDGER_DRIFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("business_day_start", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("business_day_end", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("computed_balance", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
])


# Overdraft view exposes only the stored balance (no computed/drift) —
# the violation IS the negative stored balance, no comparison needed.
OVERDRAFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("business_day_start", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("business_day_end", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("stored_balance", "DECIMAL"),
])


# Limit breach view groups by (account, day, transfer_type), so each
# row is one (parent-account, day, type) cell where the cumulative
# debit total exceeded the L2-configured cap. `business_day` is the
# truncated day (DATETIME, not the start/end pair the daily-balance
# views carry — the M.1a.7 view uses DATE_TRUNC on transaction posting).
LIMIT_BREACH_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("business_day", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("outbound_total", "DECIMAL"),
    ColumnSpec("cap", "DECIMAL"),
])


# Today's Exceptions UNION across the 5 L1 invariant views. The
# `check_type` discriminator carries the originating constraint name;
# `magnitude` is the per-branch "how bad is it" number normalized to
# absolute value so the bar chart + sort-by-magnitude reads consistently:
#   - drift / ledger_drift / expected_eod_balance_breach: ABS(<delta>)
#   - overdraft: ABS(stored_balance) (always positive — how far below 0)
#   - limit_breach: outbound_total - cap (always positive — overflow over cap)
# `account_parent_role` and `transfer_type` are NULL for branches that
# don't carry them (ledger_drift has no parent; only limit_breach has
# transfer_type).
TODAYS_EXCEPTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("check_type", "STRING"),
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("business_day", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("magnitude", "DECIMAL"),
])


# Daily Statement summary — one row per (account_id, business_day_start)
# across every internal account (and external if scoped). Sheet-level
# filters narrow to a single (account, day) for KPIs + detail; the
# dataset itself is unfiltered so the dropdown can browse all accounts.
# `opening_balance` = LAG(money) from prior business_day; `total_debits`
# / `_credits` from per-day transaction sums on `<prefix>_current_transactions`;
# `closing_balance_recomputed` = opening + signed-net of the day; `drift`
# = stored − recomputed. Drift is the single visual cue that the feed
# is consistent (= 0 on a healthy day).
DAILY_STATEMENT_SUMMARY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("account_scope", "STRING"),
    ColumnSpec("business_day_start", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("business_day_end", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("opening_balance", "DECIMAL"),
    ColumnSpec("total_debits", "DECIMAL"),
    ColumnSpec("total_credits", "DECIMAL"),
    ColumnSpec("net_flow", "DECIMAL"),
    ColumnSpec("leg_count", "INTEGER"),
    ColumnSpec("closing_balance_stored", "DECIMAL"),
    ColumnSpec("closing_balance_recomputed", "DECIMAL"),
    ColumnSpec("drift", "DECIMAL"),
])


# Daily Statement transactions — one row per Money record (leg) across
# every account-day. Same per-account-day filter pattern as the summary;
# detail table on the sheet renders the day's legs once both filters are
# applied. `business_day` = DATE_TRUNC('day', posting) so the
# business_day_start filter on the summary side aligns with this column.
DAILY_STATEMENT_TRANSACTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("business_day", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("posting", "DATETIME"),
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("amount_money", "DECIMAL"),
    ColumnSpec("amount_direction", "STRING"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("origin", "STRING"),
    ColumnSpec("memo", "STRING"),
])


# Transactions sheet — raw posting ledger, every leg in the L2's
# current_transactions matview. Supersession-aware via Current* (no
# superseded entries). Columns are a subset of the matview shape: drop
# entry / account_scope / transfer_completion / metadata / template_name
# / bundle_id / supersedes since they're internal-only and the per-leg
# table doesn't need them. account_id + transfer_id stay for drill
# wiring (M.2b.7).
TRANSACTIONS_CONTRACT = DatasetContract(columns=[
    ColumnSpec("transaction_id", "STRING"),
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("transfer_parent_id", "STRING"),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("rail_name", "STRING"),
    ColumnSpec("amount_money", "DECIMAL"),
    ColumnSpec("amount_direction", "STRING"),
    ColumnSpec("status", "STRING"),
    ColumnSpec("origin", "STRING"),
    ColumnSpec("posting", "DATETIME"),
    ColumnSpec("transfer_completion", "DATETIME"),
])


# -- Builders ----------------------------------------------------------------


def build_drift_dataset(cfg: Config, l2_instance: L2Instance) -> DataSet:
    """Wrap the leaf-account drift view from M.1a.7.

    Rows in this dataset are leaf-account drift violations only — the
    M.1a.7 view pre-filters to ``stored_balance != computed_balance``.
    No `drift_status='in_balance'` rows; if the dashboard wants to show
    "all accounts including no-drift", it queries the underlying
    Current* view directly, not this dataset.
    """
    prefix = l2_instance.instance
    sql = f"SELECT * FROM {prefix}_drift"
    return build_dataset(
        cfg, cfg.prefixed("l1-drift-dataset"),
        "L1 Drift", "l1-drift",
        sql, DRIFT_CONTRACT,
        visual_identifier=DS_DRIFT,
    )


def build_ledger_drift_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap the parent-account drift view from M.1a.7.

    Same shape as ``build_drift_dataset`` minus ``account_parent_role``
    (parent accounts ARE the parents — no parent_role column on this
    view).
    """
    prefix = l2_instance.instance
    sql = f"SELECT * FROM {prefix}_ledger_drift"
    return build_dataset(
        cfg, cfg.prefixed("l1-ledger-drift-dataset"),
        "L1 Ledger Drift", "l1-ledger-drift",
        sql, LEDGER_DRIFT_CONTRACT,
        visual_identifier=DS_LEDGER_DRIFT,
    )


def build_overdraft_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap the internal-account overdraft view from M.1a.7.

    Rows are accounts with negative stored balance — the L1 invariant
    is "no internal account holds negative money." External accounts
    are excluded by the view (filtered to ``account_scope = 'internal'``).
    """
    prefix = l2_instance.instance
    sql = f"SELECT * FROM {prefix}_overdraft"
    return build_dataset(
        cfg, cfg.prefixed("l1-overdraft-dataset"),
        "L1 Overdraft", "l1-overdraft",
        sql, OVERDRAFT_CONTRACT,
        visual_identifier=DS_OVERDRAFT,
    )


def build_limit_breach_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap the per-(account, day, type) limit-breach view from M.1a.7.

    Each row is one cell where the cumulative outbound debit exceeded
    the L2-configured cap. Caps are inlined in the view at emit-time
    from the L2 LimitSchedules — no JSON path lookups in the dataset
    SQL.
    """
    prefix = l2_instance.instance
    sql = f"SELECT * FROM {prefix}_limit_breach"
    return build_dataset(
        cfg, cfg.prefixed("l1-limit-breach-dataset"),
        "L1 Limit Breach", "l1-limit-breach",
        sql, LIMIT_BREACH_CONTRACT,
        visual_identifier=DS_LIMIT_BREACH,
    )


def build_todays_exceptions_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap the `<prefix>_todays_exceptions` matview from M.1a.9.

    M.1a.9 promoted the UNION ALL from inline CustomSql to a per-instance
    MATERIALIZED VIEW so each visual on the Today's Exceptions sheet
    reads a precomputed table instead of re-running the 5-branch UNION.
    Refresh contract: integrators MUST call `refresh_matviews_sql()`
    after every batch insert into the base tables.
    """
    prefix = l2_instance.instance
    sql = f"SELECT * FROM {prefix}_todays_exceptions"
    return build_dataset(
        cfg, cfg.prefixed("l1-todays-exceptions-dataset"),
        "L1 Today's Exceptions", "l1-todays-exceptions",
        sql, TODAYS_EXCEPTIONS_CONTRACT,
        visual_identifier=DS_TODAYS_EXCEPTIONS,
    )


def build_daily_statement_summary_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap the `<prefix>_daily_statement_summary` matview from M.1a.9.

    M.1a.9 promoted the LAG window + LEFT JOIN + GROUP BY CTE from
    inline CustomSql to a per-instance MATERIALIZED VIEW so each KPI
    on the Daily Statement sheet reads a precomputed table instead of
    re-evaluating the multi-CTE per visual (5 KPIs × CTE = 5
    re-evaluations otherwise). Refresh contract via
    `refresh_matviews_sql()` after every batch insert.
    """
    prefix = l2_instance.instance
    sql = f"SELECT * FROM {prefix}_daily_statement_summary"
    return build_dataset(
        cfg, cfg.prefixed("l1-daily-statement-summary-dataset"),
        "L1 Daily Statement Summary", "l1-daily-statement-summary",
        sql, DAILY_STATEMENT_SUMMARY_CONTRACT,
        visual_identifier=DS_DAILY_STATEMENT_SUMMARY,
    )


def _daily_statement_transactions_sql(prefix: str) -> str:
    """Per-leg projection from `<prefix>_current_transactions` carrying
    everything the Daily Statement detail table renders. Sheet-level
    filters narrow to one (account_id, business_day) at render time.
    """
    return (
        f"SELECT tx.id AS transaction_id,"
        f"       tx.account_id, tx.account_name,"
        f"       DATE_TRUNC('day', tx.posting) AS business_day,"
        f"       tx.posting,"
        f"       tx.transfer_id, tx.transfer_type,"
        f"       tx.amount_money, tx.amount_direction,"
        f"       tx.status, tx.origin, tx.memo"
        f" FROM {prefix}_current_transactions tx"
    )


def build_daily_statement_transactions_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap the per-leg ledger feed for Daily Statement detail rows."""
    sql = _daily_statement_transactions_sql(l2_instance.instance)
    return build_dataset(
        cfg, cfg.prefixed("l1-daily-statement-transactions-dataset"),
        "L1 Daily Statement Transactions",
        "l1-daily-statement-transactions",
        sql, DAILY_STATEMENT_TRANSACTIONS_CONTRACT,
        visual_identifier=DS_DAILY_STATEMENT_TRANSACTIONS,
    )


def build_transactions_dataset(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap `<prefix>_current_transactions` matview for the Transactions
    sheet's raw posting ledger.

    Reads from the matview directly (M.1a.9 made it a MATERIALIZED VIEW
    + indexed) so per-account / per-transfer / per-status / per-origin /
    per-transfer_type filter dropdowns hit indexed lookups. Projects
    only the analyst-visible columns; internal columns (entry,
    account_scope, supersedes, bundle_id, template_name, metadata) stay
    in the matview but aren't surfaced.
    """
    prefix = l2_instance.instance
    sql = (
        f"SELECT id AS transaction_id, account_id, account_name,"
        f" account_role, account_parent_role,"
        f" transfer_id, transfer_parent_id, transfer_type, rail_name,"
        f" amount_money, amount_direction, status, origin,"
        f" posting, transfer_completion"
        f" FROM {prefix}_current_transactions"
    )
    return build_dataset(
        cfg, cfg.prefixed("l1-transactions-dataset"),
        "L1 Transactions", "l1-transactions",
        sql, TRANSACTIONS_CONTRACT,
        visual_identifier=DS_TRANSACTIONS,
    )


def build_all_l1_dashboard_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> list[DataSet]:
    """Return every dataset the L1 dashboard's sheets reference.

    `build_l1_dashboard_app` calls this and registers each result on the
    App tree.
    """
    return [
        build_drift_dataset(cfg, l2_instance),
        build_ledger_drift_dataset(cfg, l2_instance),
        build_overdraft_dataset(cfg, l2_instance),
        build_limit_breach_dataset(cfg, l2_instance),
        build_todays_exceptions_dataset(cfg, l2_instance),
        build_daily_statement_summary_dataset(cfg, l2_instance),
        build_daily_statement_transactions_dataset(cfg, l2_instance),
        build_transactions_dataset(cfg, l2_instance),
    ]
