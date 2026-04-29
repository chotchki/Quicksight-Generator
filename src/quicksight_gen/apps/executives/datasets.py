"""Custom-SQL datasets for the Executives app (L.6.3).

Two datasets, both reading the shared base tables:

- ``exec_transaction_summary`` — one row per ``(posted_date,
  transfer_type)`` aggregated from ``transactions``. Drives the
  Transaction Volume Over Time + Money Moved sheets.
- ``exec_account_summary`` — one row per ``account_id`` joined
  against an activity rollup over ``transactions``. Drives the
  Account Coverage sheet.

**Aggregation choices.** Both queries aggregate per ``transfer_id``
first, then roll up to (date, type). Aggregating at the leg grain
would double-count multi-leg transfers — e.g. a $100 ACH transfer
posts as a +$100 + a -$100 leg, both with ``amount=100``; raw
``SUM(amount)`` gives $200 of "money moved" when only $100 actually
moved. The per-transfer pre-aggregation collapses each transfer to
one row (``MAX(amount)`` since both legs share the magnitude;
``SUM(signed_amount)`` for the net flow which is 0 for balanced
multi-leg, non-zero for single-leg or unbalanced).

**Status filter.** Both datasets filter to ``status = 'success'``.
Failed legs are recorded but didn't actually move money — including
them would inflate the executive trends with operational noise.
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnShape,
    ColumnSpec,
    DatasetContract,
    build_dataset,
    register_contract,
)
from quicksight_gen.common.models import DataSet
from quicksight_gen.common.sheets.app_info import (
    build_liveness_dataset,
    build_matview_status_dataset,
)


# M.4.4.5 — Executives reads base tables only; no app-specific
# matviews. The App Info sheet still ships with the matview status
# table, which renders a placeholder row when the list is empty.
EXEC_MATVIEW_NAMES: list[str] = []


# Identifier strings used as the DataSetIdentifier in visuals + filters.
DS_EXEC_TRANSACTION_SUMMARY = "exec-transaction-summary-ds"
DS_EXEC_ACCOUNT_SUMMARY = "exec-account-summary-ds"


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

EXEC_TRANSACTION_SUMMARY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("posted_date", "DATETIME"),
    ColumnSpec("transfer_type", "STRING", shape=ColumnShape.TRANSFER_TYPE),
    ColumnSpec("transfer_count", "INTEGER"),
    ColumnSpec("gross_amount", "DECIMAL"),
    ColumnSpec("net_amount", "DECIMAL"),
])


EXEC_ACCOUNT_SUMMARY_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_type", "STRING"),
    ColumnSpec("last_activity_date", "DATETIME"),
    ColumnSpec("activity_count", "INTEGER"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_transaction_summary_dataset(cfg: Config) -> DataSet:
    """Per-(date, transfer_type) aggregates: transfer count, gross + net dollars.

    Aggregates per ``transfer_id`` first so multi-leg transfers are
    counted once, not once per leg. ``gross_amount`` is the per-transfer
    handle; ``net_amount`` is the per-transfer net flow (0 for balanced
    multi-leg, non-zero for single-leg or unbalanced transfers).
    """
    sql = """\
WITH per_transfer AS (
    SELECT
        DATE(MIN(t.posted_at))   AS posted_date,
        t.transfer_id,
        t.transfer_type,
        MAX(t.amount)            AS transfer_amount,
        SUM(t.signed_amount)     AS transfer_net
    FROM transactions t
    WHERE t.status = 'success'
    GROUP BY t.transfer_id, t.transfer_type
)
SELECT
    posted_date,
    transfer_type,
    COUNT(*)                   AS transfer_count,
    SUM(transfer_amount)       AS gross_amount,
    SUM(transfer_net)          AS net_amount
FROM per_transfer
GROUP BY posted_date, transfer_type"""
    return build_dataset(
        cfg,
        cfg.prefixed("exec-transaction-summary-dataset"),
        "Executives Transaction Summary",
        "exec-transaction-summary",
        sql,
        EXEC_TRANSACTION_SUMMARY_CONTRACT,
        visual_identifier=DS_EXEC_TRANSACTION_SUMMARY,
    )


def build_account_summary_dataset(cfg: Config) -> DataSet:
    """One row per account that has ever appeared in ``daily_balances``.

    LEFT JOINs an activity rollup so accounts with zero activity in
    the dataset (just opened, never moved money) still show up with
    ``last_activity_date = NULL``, ``activity_count = 0``. The
    Account Coverage sheet's "active accounts" KPI applies a visual-
    scoped filter on ``activity_count > 0`` to narrow the count.
    """
    sql = """\
WITH activity AS (
    SELECT
        t.account_id,
        MAX(DATE(t.posted_at))  AS last_activity_date,
        COUNT(*)                AS activity_count
    FROM transactions t
    WHERE t.status = 'success'
    GROUP BY t.account_id
),
accounts AS (
    SELECT DISTINCT
        d.account_id,
        d.account_name,
        d.account_type
    FROM daily_balances d
)
SELECT
    a.account_id,
    a.account_name,
    a.account_type,
    act.last_activity_date,
    COALESCE(act.activity_count, 0)  AS activity_count
FROM accounts a
LEFT JOIN activity act USING (account_id)"""
    return build_dataset(
        cfg,
        cfg.prefixed("exec-account-summary-dataset"),
        "Executives Account Summary",
        "exec-account-summary",
        sql,
        EXEC_ACCOUNT_SUMMARY_CONTRACT,
        visual_identifier=DS_EXEC_ACCOUNT_SUMMARY,
    )


def build_all_datasets(cfg: Config) -> list[DataSet]:
    """Return every dataset used by the Executives app."""
    return [
        build_transaction_summary_dataset(cfg),
        build_account_summary_dataset(cfg),
        # M.4.4.5 — App Info ("i") sheet datasets, ALWAYS LAST.
        build_liveness_dataset(cfg),
        build_matview_status_dataset(cfg, view_names=EXEC_MATVIEW_NAMES),
    ]


# Register contracts at module import so the L.1.17 emit-time validator
# can resolve every ds["col"] ref in the visuals below. ``build_dataset()``
# re-registers each contract too — idempotent for the same
# (visual_identifier, contract) pair.
_CONTRACT_REGISTRATIONS: tuple[tuple[str, DatasetContract], ...] = (
    (DS_EXEC_TRANSACTION_SUMMARY, EXEC_TRANSACTION_SUMMARY_CONTRACT),
    (DS_EXEC_ACCOUNT_SUMMARY, EXEC_ACCOUNT_SUMMARY_CONTRACT),
)
for _vid, _contract in _CONTRACT_REGISTRATIONS:
    register_contract(_vid, _contract)
