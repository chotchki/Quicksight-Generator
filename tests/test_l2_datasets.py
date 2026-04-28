"""Tests for the M.2.4a v6 dataset builders.

Each v6 builder targets the prefixed L1 invariant views from M.1a.7 and
preserves the v5 column-projection shape so `apps/account_recon/app.py`
consumes the new datasets without per-visual changes (the M.2.4b switchover
is mechanical: replace the v5 builder calls with v6 builder calls in
`_datasets()`).

Tests assert: the SQL references the right L2 prefix + L1 view; the
column projection matches the v5 contract; the builder returns the
right DatasetId / identifier shape so the AR app's tree wiring works
unchanged.
"""

from __future__ import annotations

import pytest

from quicksight_gen.apps.account_recon._l2 import default_l2_instance
from quicksight_gen.apps.account_recon._l2_datasets import (
    OVERDRAFT_CONTRACT,
    build_ledger_balance_drift_dataset_v2,
    build_overdraft_dataset_v2,
    build_subledger_balance_drift_dataset_v2,
)
from quicksight_gen.apps.account_recon.datasets import (
    LEDGER_BALANCE_DRIFT_CONTRACT,
    SUBLEDGER_BALANCE_DRIFT_CONTRACT,
)
from quicksight_gen.common.config import Config


_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


@pytest.fixture(scope="module")
def instance():
    return default_l2_instance()


def _custom_sql(ds) -> str:
    """Pull the CUSTOM_SQL string out of a DataSet."""
    table = list(ds.PhysicalTableMap.values())[0]
    return table.CustomSql.SqlQuery


# -- Subledger drift dataset ------------------------------------------------


def test_subledger_drift_v2_targets_l1_drift_view(instance) -> None:
    """SQL references the prefixed M.1a.7 drift view, not the v5
    `ar_subledger_balance_drift` view."""
    ds = build_subledger_balance_drift_dataset_v2(_CFG, instance)
    sql = _custom_sql(ds)
    assert "FROM spec_example_drift" in sql
    assert "ar_subledger_balance_drift" not in sql


def test_subledger_drift_v2_preserves_v5_column_contract(instance) -> None:
    """Column projection matches the v5 contract — AR app tree code that
    binds to these column names continues to work after the switchover."""
    ds = build_subledger_balance_drift_dataset_v2(_CFG, instance)
    cols = {c.Name for c in list(ds.PhysicalTableMap.values())[0].CustomSql.Columns}
    expected = {c.name for c in SUBLEDGER_BALANCE_DRIFT_CONTRACT.columns}
    assert cols == expected


def test_subledger_drift_v2_dataset_id_matches_v5(instance) -> None:
    """Same QuickSight DataSetId as v5 — the deployed AR app's
    DataSetIdentifierDeclarations don't need to change."""
    ds = build_subledger_balance_drift_dataset_v2(_CFG, instance)
    assert ds.DataSetId == "qs-gen-ar-subledger-balance-drift-dataset"


def test_subledger_drift_v2_dataset_table_key_matches_v5(instance) -> None:
    """The PhysicalTableMap table_key matches v5 (`ar-subledger-balance-drift`).
    The contract registry is keyed by `visual_identifier` separately."""
    from quicksight_gen.apps.account_recon.datasets import (
        build_subledger_balance_drift_dataset,
    )
    v5 = build_subledger_balance_drift_dataset(_CFG)
    v6 = build_subledger_balance_drift_dataset_v2(_CFG, instance)
    assert (
        list(v5.PhysicalTableMap.keys())[0]
        == list(v6.PhysicalTableMap.keys())[0]
    )


def test_subledger_drift_v2_drift_status_is_constant(instance) -> None:
    """The M.1a.7 view returns ONLY violation rows, so drift_status is
    pre-projected as 'drift'. v5's 'in_balance' rows aren't reachable
    via this dataset under v6 (they don't exist in the view)."""
    ds = build_subledger_balance_drift_dataset_v2(_CFG, instance)
    sql = _custom_sql(ds)
    assert "'drift'" in sql and "AS drift_status" in sql


# -- Ledger drift dataset ---------------------------------------------------


def test_ledger_drift_v2_targets_l1_ledger_drift_view(instance) -> None:
    ds = build_ledger_balance_drift_dataset_v2(_CFG, instance)
    sql = _custom_sql(ds)
    assert "FROM spec_example_ledger_drift" in sql
    assert "ar_ledger_balance_drift" not in sql


def test_ledger_drift_v2_preserves_v5_column_contract(instance) -> None:
    ds = build_ledger_balance_drift_dataset_v2(_CFG, instance)
    cols = {c.Name for c in list(ds.PhysicalTableMap.values())[0].CustomSql.Columns}
    expected = {c.name for c in LEDGER_BALANCE_DRIFT_CONTRACT.columns}
    assert cols == expected


def test_ledger_drift_v2_dataset_id_matches_v5(instance) -> None:
    ds = build_ledger_balance_drift_dataset_v2(_CFG, instance)
    assert ds.DataSetId == "qs-gen-ar-ledger-balance-drift-dataset"


def test_ledger_drift_v2_dataset_table_key_matches_v5(instance) -> None:
    """The PhysicalTableMap table_key matches v5; v5/v6 are substitutable
    in the AR app's `_datasets()` helper."""
    from quicksight_gen.apps.account_recon.datasets import (
        build_ledger_balance_drift_dataset,
    )
    v5 = build_ledger_balance_drift_dataset(_CFG)
    v6 = build_ledger_balance_drift_dataset_v2(_CFG, instance)
    assert (
        list(v5.PhysicalTableMap.keys())[0]
        == list(v6.PhysicalTableMap.keys())[0]
    )


# -- Overdraft dataset (no v5 equivalent) -----------------------------------


def test_overdraft_v2_targets_l1_overdraft_view(instance) -> None:
    """New v6 dataset; no v5 standalone equivalent."""
    ds = build_overdraft_dataset_v2(_CFG, instance)
    sql = _custom_sql(ds)
    assert "FROM spec_example_overdraft" in sql


def test_overdraft_v2_contract_columns_match_builder(instance) -> None:
    ds = build_overdraft_dataset_v2(_CFG, instance)
    cols = {c.Name for c in list(ds.PhysicalTableMap.values())[0].CustomSql.Columns}
    expected = {c.name for c in OVERDRAFT_CONTRACT.columns}
    assert cols == expected


# -- L2 prefix flows through (M.2.3 + M.1a.7 contract) ----------------------


def test_all_v6_builders_use_l2_instance_prefix(instance) -> None:
    """Each builder pulls the prefix from `l2_instance.instance` rather
    than hardcoding — the seam M.2.3 plumbed in IS what M.2.4 consumes."""
    builders = (
        build_subledger_balance_drift_dataset_v2,
        build_ledger_balance_drift_dataset_v2,
        build_overdraft_dataset_v2,
    )
    for builder in builders:
        ds = builder(_CFG, instance)
        sql = _custom_sql(ds)
        # The Sasquatch instance prefix appears in every dataset's SQL.
        assert f"FROM spec_example_" in sql, (
            f"{builder.__name__}: SQL doesn't reference the L2 prefix"
        )


def test_aging_columns_present_on_drift_datasets(instance) -> None:
    """Both drift datasets project the AR aging-bucket + lateness columns
    that the existing tree visuals depend on."""
    for builder in (
        build_subledger_balance_drift_dataset_v2,
        build_ledger_balance_drift_dataset_v2,
    ):
        ds = builder(_CFG, instance)
        sql = _custom_sql(ds)
        assert "days_outstanding" in sql
        assert "aging_bucket" in sql
        assert "expected_complete_at" in sql
        assert "is_late" in sql
