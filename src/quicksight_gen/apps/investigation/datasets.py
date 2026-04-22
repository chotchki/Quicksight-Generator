"""Custom-SQL datasets for the Investigation app.

K.4.3 ships the recipient-fanout dataset. K.4.4 adds the rolling-window
anomaly dataset (read from the ``inv_pair_rolling_anomalies`` matview).
K.4.5 will add the money-trail recursive-CTE dataset.

All datasets read the shared `transactions` + `daily_balances` base
tables — Investigation has no app-specific schema. The K.4.4 matview
is computed at refresh time, not dataset time, because the rolling
window + population z-score were too heavy for QuickSight Direct Query
at realistic transaction volumes.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    DS_INV_RECIPIENT_FANOUT,
    DS_INV_VOLUME_ANOMALIES,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnShape,
    ColumnSpec,
    DatasetContract,
    build_dataset,
    register_contract,
)
from quicksight_gen.common.models import DataSet


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

# One row per (recipient leg, sender leg) pair sharing a transfer_id.
# Visuals aggregate to one row per recipient via COUNT_DISTINCT(sender_id)
# + SUM(amount), so the dataset stays at the legs grain to support both
# the fanout count and the per-row drill into AR Transactions in K.4.7.
RECIPIENT_FANOUT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("recipient_account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("recipient_account_name", "STRING"),
    ColumnSpec("recipient_account_type", "STRING"),
    ColumnSpec("sender_account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("sender_account_name", "STRING"),
    ColumnSpec("sender_account_type", "STRING"),
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("posted_at", "DATETIME"),
    ColumnSpec("amount", "DECIMAL"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

# One row per (sender, recipient, posted_day) with that day's rolling
# 2-day SUM, transfer count, and z-score against the population of all
# pair-windows. Computed by the ``inv_pair_rolling_anomalies`` matview;
# see ``schema.sql`` for the windowing CTE.
VOLUME_ANOMALIES_CONTRACT = DatasetContract(columns=[
    ColumnSpec("recipient_account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("recipient_account_name", "STRING"),
    ColumnSpec("recipient_account_type", "STRING"),
    ColumnSpec("sender_account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("sender_account_name", "STRING"),
    ColumnSpec("sender_account_type", "STRING"),
    ColumnSpec("window_start", "DATETIME"),
    ColumnSpec("window_end", "DATETIME"),
    ColumnSpec("window_sum", "DECIMAL"),
    ColumnSpec("transfer_count", "INTEGER"),
    ColumnSpec("pop_mean", "DECIMAL"),
    ColumnSpec("pop_stddev", "DECIMAL"),
    ColumnSpec("z_score", "DECIMAL"),
    ColumnSpec("z_bucket", "STRING"),
])


def build_recipient_fanout_dataset(cfg: Config) -> DataSet:
    """Recipient × sender × transfer rows, one per (recipient leg, sender leg).

    Filters to recipient ``account_type IN ('dda', 'merchant_dda')`` so
    administrative sweeps into ``gl_control`` / ``concentration_master``
    don't dominate the fanout ranking — those always pull from many
    accounts by design and would crowd out genuine AML signal.
    """
    sql = """\
WITH inflows AS (
    SELECT
        t.transfer_id,
        t.account_id            AS recipient_account_id,
        t.account_name          AS recipient_account_name,
        t.account_type          AS recipient_account_type,
        t.signed_amount         AS amount,
        t.posted_at             AS posted_at
    FROM transactions t
    WHERE t.signed_amount > 0
      AND t.status = 'success'
      AND t.account_type IN ('dda', 'merchant_dda')
),
outflows AS (
    SELECT
        t.transfer_id,
        t.account_id            AS sender_account_id,
        t.account_name          AS sender_account_name,
        t.account_type          AS sender_account_type
    FROM transactions t
    WHERE t.signed_amount < 0
      AND t.status = 'success'
)
SELECT
    i.recipient_account_id,
    i.recipient_account_name,
    i.recipient_account_type,
    o.sender_account_id,
    o.sender_account_name,
    o.sender_account_type,
    i.transfer_id,
    i.posted_at,
    i.amount
FROM inflows i
JOIN outflows o USING (transfer_id)"""
    return build_dataset(
        cfg,
        cfg.prefixed("inv-recipient-fanout-dataset"),
        "Investigation Recipient Fanout",
        "inv-recipient-fanout",
        sql,
        RECIPIENT_FANOUT_CONTRACT,
        visual_identifier=DS_INV_RECIPIENT_FANOUT,
    )


def build_volume_anomalies_dataset(cfg: Config) -> DataSet:
    """Pair-grain rolling-window anomalies sourced from the matview.

    The dataset is a thin SELECT over ``inv_pair_rolling_anomalies`` —
    every column is computed at refresh time. Visuals filter via a
    NumericRangeFilter on ``z_score`` bound to the σ-threshold parameter.
    """
    sql = "SELECT * FROM inv_pair_rolling_anomalies"
    return build_dataset(
        cfg,
        cfg.prefixed("inv-volume-anomalies-dataset"),
        "Investigation Volume Anomalies",
        "inv-volume-anomalies",
        sql,
        VOLUME_ANOMALIES_CONTRACT,
        visual_identifier=DS_INV_VOLUME_ANOMALIES,
    )


def build_all_datasets(cfg: Config) -> list[DataSet]:
    return [
        build_recipient_fanout_dataset(cfg),
        build_volume_anomalies_dataset(cfg),
    ]


# Register contracts at module import so visuals built later resolve
# drill source-field shapes without depending on dataset construction
# order.
_CONTRACT_REGISTRATIONS: tuple[tuple[str, DatasetContract], ...] = (
    (DS_INV_RECIPIENT_FANOUT, RECIPIENT_FANOUT_CONTRACT),
    (DS_INV_VOLUME_ANOMALIES, VOLUME_ANOMALIES_CONTRACT),
)
for _vid, _contract in _CONTRACT_REGISTRATIONS:
    register_contract(_vid, _contract)
