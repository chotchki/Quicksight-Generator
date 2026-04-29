"""Custom-SQL datasets for the Investigation app.

K.4.3 ships the recipient-fanout dataset. K.4.4 adds the rolling-window
anomaly dataset (read from the ``inv_pair_rolling_anomalies`` matview).
K.4.5 adds the money-trail dataset (read from the
``inv_money_trail_edges`` matview, which precomputes the
``WITH RECURSIVE`` walk over ``parent_transfer_id``). K.4.8 wraps the
same matview as a second dataset so the account-centric filters
(anchor account, min amount) don't cross-contaminate K.4.5's
chain-rooted filters.

All datasets read the shared `transactions` + `daily_balances` base
tables — Investigation has no app-specific schema. The K.4.4 + K.4.5
matviews are computed at refresh time, not dataset time, because the
rolling-window z-score and the recursive chain walk were both too heavy
for QuickSight Direct Query at realistic transaction volumes.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    DS_INV_ACCOUNT_NETWORK,
    DS_INV_ANETWORK_ACCOUNTS,
    DS_INV_MONEY_TRAIL,
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
from quicksight_gen.common.sheets.app_info import (
    build_liveness_dataset,
    build_matview_status_dataset,
)


# M.4.4.5 — matviews the Investigation app reads, surfaced on the
# App Info ("i") sheet's matview-status table.
INV_MATVIEW_NAMES = [
    "inv_pair_rolling_anomalies",
    "inv_money_trail_edges",
]


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


# One row per (chain root, transfer, source-leg × target-leg) edge in the
# precomputed money-trail matview. ``root_transfer_id`` is the chain's
# top-most transfer (no parent); ``transfer_id`` is the transfer this
# edge belongs to; ``depth`` is the hop's distance from the root (0 =
# root). Edges include only multi-leg transfers — single-leg sales /
# external arrivals appear as chain members in the recursive walk but
# don't surface as visible edges. See ``schema.sql`` for the recursive
# CTE shape and the multi-leg-only rationale.
MONEY_TRAIL_CONTRACT = DatasetContract(columns=[
    ColumnSpec("root_transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("transfer_id", "STRING", shape=ColumnShape.TRANSFER_ID),
    ColumnSpec("depth", "INTEGER"),
    ColumnSpec("source_account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("source_account_name", "STRING"),
    ColumnSpec("source_account_type", "STRING"),
    ColumnSpec("target_account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("target_account_name", "STRING"),
    ColumnSpec("target_account_type", "STRING"),
    ColumnSpec("hop_amount", "DECIMAL"),
    ColumnSpec("posted_at", "DATETIME"),
    ColumnSpec("transfer_type", "STRING"),
    # Concatenated display labels, computed in the dataset SQL (see
    # MONEY_TRAIL_BASE_SQL). Used by the Account Network sheet as the
    # walk-the-flow anchor — they're both human-readable AND uniquely
    # keyed (embedded account_id disambiguates name collisions). Money
    # Trail doesn't read these but they project cleanly through its
    # own dataset wrapper and stay zero-cost at query time.
    ColumnSpec("source_display", "STRING", shape=ColumnShape.ACCOUNT_DISPLAY),
    ColumnSpec("target_display", "STRING", shape=ColumnShape.ACCOUNT_DISPLAY),
])


# Both money-trail-shaped datasets project the same matview; the
# wrapper computes the display columns inline so the matview stays a
# pure shape over base tables.
MONEY_TRAIL_BASE_SQL = """\
SELECT
    *,
    source_account_name || ' (' || source_account_id || ')' AS source_display,
    target_account_name || ' (' || target_account_id || ')' AS target_display
FROM inv_money_trail_edges
"""


# K.4.8k — narrow dataset feeding only the anchor-account dropdown.
# Single column ``source_display`` (the same concatenated label the
# Account Network dataset uses) so the anchor parameter, the calc
# fields, and the dropdown population all speak the same string. The
# DISTINCT happens INSIDE the SELECT so PG dedupes the (id, name) pairs
# before computing the per-row concat — O(distinct accounts) instead
# of O(matview rows). At dataset-load time the planner gets one column
# of ~tens of values; the dropdown loads instantly.
ANETWORK_ACCOUNTS_CONTRACT = DatasetContract(columns=[
    ColumnSpec(
        "source_display", "STRING", shape=ColumnShape.ACCOUNT_DISPLAY,
    ),
])

ANETWORK_ACCOUNTS_SQL = """\
SELECT DISTINCT
    source_account_name || ' (' || source_account_id || ')' AS source_display
FROM inv_money_trail_edges
"""


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


def build_money_trail_dataset(cfg: Config) -> DataSet:
    """Per-edge money trail rows sourced from the recursive-CTE matview.

    The dataset is a thin SELECT over ``inv_money_trail_edges``; the
    recursive walk happens at refresh time. Visuals filter via:

    - ``CategoryFilter`` on ``root_transfer_id`` bound to
      ``pInvMoneyTrailRoot`` — narrows to a single chain.
    - ``NumericRangeFilter`` on ``depth`` bound to
      ``pInvMoneyTrailMaxHops`` — caps chain depth.
    - ``NumericRangeFilter`` on ``hop_amount`` bound to
      ``pInvMoneyTrailMinAmount`` — drops noise edges.
    """
    sql = MONEY_TRAIL_BASE_SQL
    return build_dataset(
        cfg,
        cfg.prefixed("inv-money-trail-dataset"),
        "Investigation Money Trail",
        "inv-money-trail",
        sql,
        MONEY_TRAIL_CONTRACT,
        visual_identifier=DS_INV_MONEY_TRAIL,
    )


def build_account_network_dataset(cfg: Config) -> DataSet:
    """Per-edge account-network rows — same matview as money trail.

    Reuses ``inv_money_trail_edges``; a second dataset registration so
    the account-centric calc field (``is_anchor_edge``) and filters
    (anchor account, min amount) live independently of the K.4.5
    chain-root filters. Contract is identical because the underlying
    rows are.
    """
    sql = MONEY_TRAIL_BASE_SQL
    return build_dataset(
        cfg,
        cfg.prefixed("inv-account-network-dataset"),
        "Investigation Account Network",
        "inv-account-network",
        sql,
        MONEY_TRAIL_CONTRACT,
        visual_identifier=DS_INV_ACCOUNT_NETWORK,
    )


def build_account_network_accounts_dataset(cfg: Config) -> DataSet:
    """Narrow accounts dataset feeding the K.4.8 anchor dropdown only.

    Single column ``source_display`` distinct'd over the matview so
    QuickSight's dropdown can ``SELECT DISTINCT source_display FROM ...``
    in O(distinct accounts) work instead of O(matview rows). Originally
    the dropdown pointed at the full Account Network dataset; that
    dataset wraps the matview with a per-row concat that the dropdown's
    DISTINCT couldn't push past, so the dropdown started timing out as
    the matview grew. This dataset puts the DISTINCT inside the SELECT
    so PG dedupes the (id, name) pairs before concatenating.

    Reuses ``inv_money_trail_edges`` — no new matview needed.
    """
    return build_dataset(
        cfg,
        cfg.prefixed("inv-anetwork-accounts-dataset"),
        "Investigation Account Network — Accounts",
        "inv-anetwork-accounts",
        ANETWORK_ACCOUNTS_SQL,
        ANETWORK_ACCOUNTS_CONTRACT,
        visual_identifier=DS_INV_ANETWORK_ACCOUNTS,
    )


def build_all_datasets(cfg: Config) -> list[DataSet]:
    return [
        build_recipient_fanout_dataset(cfg),
        build_volume_anomalies_dataset(cfg),
        build_money_trail_dataset(cfg),
        build_account_network_dataset(cfg),
        build_account_network_accounts_dataset(cfg),
        # M.4.4.5 — App Info ("i") sheet datasets, ALWAYS LAST.
        build_liveness_dataset(cfg),
        build_matview_status_dataset(cfg, view_names=INV_MATVIEW_NAMES),
    ]


# Register contracts at module import so visuals built later resolve
# drill source-field shapes without depending on dataset construction
# order.
_CONTRACT_REGISTRATIONS: tuple[tuple[str, DatasetContract], ...] = (
    (DS_INV_RECIPIENT_FANOUT, RECIPIENT_FANOUT_CONTRACT),
    (DS_INV_VOLUME_ANOMALIES, VOLUME_ANOMALIES_CONTRACT),
    (DS_INV_MONEY_TRAIL, MONEY_TRAIL_CONTRACT),
    (DS_INV_ACCOUNT_NETWORK, MONEY_TRAIL_CONTRACT),
    (DS_INV_ANETWORK_ACCOUNTS, ANETWORK_ACCOUNTS_CONTRACT),
)
for _vid, _contract in _CONTRACT_REGISTRATIONS:
    register_contract(_vid, _contract)
