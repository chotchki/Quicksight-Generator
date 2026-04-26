"""v6 dataset builders for the AR app — phase M.2.4a.

These build QuickSight DataSets whose CUSTOM_SQL targets the v6 prefixed
schema (``<prefix>_transactions`` / ``<prefix>_daily_balances`` / Current*
views) and the M.1a.7 L1 invariant views (``<prefix>_drift`` /
``<prefix>_ledger_drift`` / ``<prefix>_overdraft`` / etc.). They preserve
the v5 column-projection shape so the existing AR dashboard tree code
in ``app.py`` consumes them without per-visual changes.

This module exists in parallel with ``datasets.py`` (which still targets
the v5 schema). M.2.4b will wire ``build_account_recon_app`` to use these
builders instead of the v5 ones; the v5 module stays around as a
fallback until M.2.6 deploys + verifies the v6 stack against real
Postgres. M.2.10 (the M.2 iteration gate) decides whether to delete
the v5 module outright or keep it as a `--legacy` flag for transition.

Each builder takes both ``cfg`` (for the QuickSight prefix +
datasource_arn) and ``l2_instance`` (for the SQL prefix and any L2-derived
predicates). The L1 invariant views from M.1a.7 carry the heavy lifting;
these builders are mostly column-aliasing + aging-bucket projection on
top.

Datasets landed in M.2.4a (this commit):
- build_subledger_balance_drift_dataset_v2 — wraps ``<prefix>_drift``
- build_ledger_balance_drift_dataset_v2   — wraps ``<prefix>_ledger_drift``
- build_overdraft_dataset_v2              — wraps ``<prefix>_overdraft``

Datasets deferred to M.2.4b/c:
- transactions, ledger_accounts, subledger_accounts (column-name shifts)
- transfer_summary + non_zero_transfers (need Conservation view)
- daily_statement_summary, daily_statement_transactions (complex aggs)
- expected_zero_eod_rollup, two_sided_post_mismatch_rollup,
  balance_drift_timelines_rollup (AR-specific aggregations on top of
  the L1 invariant views)
- ar_unified_exceptions (UNION across the L1 views)
"""

from __future__ import annotations

from quicksight_gen.apps.account_recon.constants import (
    DS_AR_LEDGER_BALANCE_DRIFT,
    DS_AR_SUBLEDGER_BALANCE_DRIFT,
)
from quicksight_gen.apps.account_recon.datasets import (
    LEDGER_BALANCE_DRIFT_CONTRACT,
    SUBLEDGER_BALANCE_DRIFT_CONTRACT,
    _aging_columns,
    _lateness_columns,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import (
    ColumnShape,
    ColumnSpec,
    DatasetContract,
    build_dataset,
)
from quicksight_gen.common.l2 import L2Instance
from quicksight_gen.common.models import DataSet


# ---------------------------------------------------------------------------
# v6 contracts (additive — overdraft has no v5 standalone equivalent)
# ---------------------------------------------------------------------------

OVERDRAFT_CONTRACT = DatasetContract(columns=[
    ColumnSpec("account_id", "STRING", shape=ColumnShape.ACCOUNT_ID),
    ColumnSpec("account_name", "STRING"),
    ColumnSpec("account_role", "STRING"),
    ColumnSpec("account_parent_role", "STRING"),
    ColumnSpec("balance_date", "DATETIME", shape=ColumnShape.DATETIME_DAY),
    ColumnSpec("stored_balance", "DECIMAL"),
    ColumnSpec("days_outstanding", "INTEGER"),
    ColumnSpec("aging_bucket", "STRING"),
    ColumnSpec("expected_complete_at", "DATETIME"),
    ColumnSpec("is_late", "STRING"),
])


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def build_subledger_balance_drift_dataset_v2(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap M.1a.7's ``<prefix>_drift`` view with v5-compatible column aliases.

    The view returns ONLY violation rows (stored ≠ computed). v5's
    `drift_status` column distinguished 'in_balance' vs 'drift' rows;
    under v6 the dataset is pre-filtered so every row has
    drift_status='drift'. The column survives for backward-compat —
    M.2a's L1-dashboard reframe will drop it as a no-op.
    """
    prefix = l2_instance.instance
    sql = f"""\
SELECT
    account_id                                                 AS subledger_account_id,
    account_name                                               AS subledger_name,
    -- v5 surfaced ledger_account_id (parent's ID); v6 carries the
    -- parent ROLE on the row. Until M.2a's L1 reframe lands, keep the
    -- v5-shaped column name pointing at the parent role string.
    account_parent_role                                        AS ledger_account_id,
    account_parent_role                                        AS ledger_name,
    'Internal'                                                 AS scope,
    business_day_start::DATE                                   AS balance_date,
    stored_balance,
    computed_balance,
    drift,
    'drift'                                                    AS drift_status,
    -- The view doesn't carry overdraft semantics (those live in
    -- <prefix>_overdraft instead). For column-shape parity,
    -- project a constant 'unknown' so existing visuals don't break;
    -- M.2a will drop this column entirely.
    'unknown'                                                  AS overdraft_status,
{_aging_columns('business_day_start')},
{_lateness_columns('business_day_start')}
FROM {prefix}_drift"""
    return build_dataset(
        cfg, cfg.prefixed("ar-subledger-balance-drift-dataset"),
        "AR Sub-Ledger Balance Drift", "ar-subledger-balance-drift",
        sql, SUBLEDGER_BALANCE_DRIFT_CONTRACT,
        visual_identifier=DS_AR_SUBLEDGER_BALANCE_DRIFT,
    )


def build_ledger_balance_drift_dataset_v2(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """Wrap M.1a.7's ``<prefix>_ledger_drift`` view with v5-compatible column aliases."""
    prefix = l2_instance.instance
    sql = f"""\
SELECT
    account_id                                                 AS ledger_account_id,
    account_name                                               AS ledger_name,
    'Internal'                                                 AS scope,
    business_day_start::DATE                                   AS balance_date,
    stored_balance,
    computed_balance,
    drift,
    'drift'                                                    AS drift_status,
{_aging_columns('business_day_start')},
{_lateness_columns('business_day_start')}
FROM {prefix}_ledger_drift"""
    return build_dataset(
        cfg, cfg.prefixed("ar-ledger-balance-drift-dataset"),
        "AR Ledger Balance Drift", "ar-ledger-balance-drift",
        sql, LEDGER_BALANCE_DRIFT_CONTRACT,
        visual_identifier=DS_AR_LEDGER_BALANCE_DRIFT,
    )


def build_overdraft_dataset_v2(
    cfg: Config, l2_instance: L2Instance,
) -> DataSet:
    """New v6 dataset wrapping ``<prefix>_overdraft``.

    No v5 equivalent — under v5 overdrafts surfaced via
    `ar_subledger_balance_drift.overdraft_status`. M.2a (L1 dashboard
    reframe) will give this its own visual; for now the dataset exists
    so M.2.4b can wire it into the build pipeline without inventing
    SQL on the fly.
    """
    prefix = l2_instance.instance
    sql = f"""\
SELECT
    account_id,
    account_name,
    account_role,
    account_parent_role,
    business_day_start::DATE                                   AS balance_date,
    stored_balance,
{_aging_columns('business_day_start')},
{_lateness_columns('business_day_start')}
FROM {prefix}_overdraft"""
    return build_dataset(
        cfg, cfg.prefixed("ar-overdraft-dataset"),
        "AR Overdraft", "ar-overdraft",
        sql, OVERDRAFT_CONTRACT,
        visual_identifier="ar-overdraft-ds",
    )
