"""QuickSight DataSet builders for the L1 Dashboard app.

Each builder wraps one M.1a.7 L1 invariant view. The SQL is intentionally
trivial (`SELECT * FROM <prefix>_<view>`) — the views already do the
filtering, computation, and shape work. Datasets here are thin façades
that surface columns to QuickSight visuals via the dataset contract.

The visual_identifier convention is ``l1-<viewname>-ds`` so every
dataset's logical name traces back to the underlying L1 invariant.

Substep landmarks:
    M.2a.3 — drift + ledger_drift datasets
    M.2a.4 — overdraft dataset (this commit)
    M.2a.5 — limit_breach dataset
    M.2a.6 — today's exceptions UNION dataset (or live SQL on the sheet)
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


def build_all_l1_dashboard_datasets(
    cfg: Config, l2_instance: L2Instance,
) -> list[DataSet]:
    """Return every dataset the L1 dashboard's sheets reference.

    M.2a.5-M.2a.6 add to this list as their per-invariant datasets land.
    `build_l1_dashboard_app` calls this and registers each result on the
    App tree.
    """
    return [
        build_drift_dataset(cfg, l2_instance),
        build_ledger_drift_dataset(cfg, l2_instance),
        build_overdraft_dataset(cfg, l2_instance),
    ]
