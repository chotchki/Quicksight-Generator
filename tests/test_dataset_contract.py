"""Tests for dataset column contracts.

Validates that every dataset builder produces a DataSet whose InputColumn
list matches its declared DatasetContract. Trimmed to Investigation-only
after M.4.3 + M.4.4 deleted the AR + PR apps.
"""

from __future__ import annotations

import pytest

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import ColumnSpec, DatasetContract
from quicksight_gen.apps.investigation import datasets as inv_datasets


@pytest.fixture()
def cfg() -> Config:
    return Config(
        aws_account_id="111122223333",
        aws_region="us-east-2",
        datasource_arn="arn:aws:quicksight:us-east-2:111122223333:datasource/ds",
        # N.3.f: Investigation builders require an L2 instance prefix.
        l2_instance_prefix="spec_example",
    )


def _extract_column_names(dataset) -> list[str]:
    """Pull the InputColumn names out of a built DataSet."""
    for physical in dataset.PhysicalTableMap.values():
        return [c.Name for c in physical.CustomSql.Columns]
    raise AssertionError("No PhysicalTable found")


# ---------------------------------------------------------------------------
# Investigation contracts
# ---------------------------------------------------------------------------

INV_BUILDERS_AND_CONTRACTS = [
    (inv_datasets.build_recipient_fanout_dataset,
     inv_datasets.RECIPIENT_FANOUT_CONTRACT),
    (inv_datasets.build_volume_anomalies_dataset,
     inv_datasets.VOLUME_ANOMALIES_CONTRACT),
    (inv_datasets.build_money_trail_dataset,
     inv_datasets.MONEY_TRAIL_CONTRACT),
]


class TestInvContracts:
    @pytest.mark.parametrize(
        "builder,contract",
        INV_BUILDERS_AND_CONTRACTS,
        ids=[c.columns[0].name for _, c in INV_BUILDERS_AND_CONTRACTS],
    )
    def test_columns_match_contract(self, cfg, builder, contract):
        ds = builder(cfg)
        actual = _extract_column_names(ds)
        assert actual == contract.column_names


# ---------------------------------------------------------------------------
# Contract basics
# ---------------------------------------------------------------------------

class TestDatasetContract:
    def test_column_names_property(self):
        c = DatasetContract(columns=[
            ColumnSpec("a", "STRING"),
            ColumnSpec("b", "DECIMAL"),
        ])
        assert c.column_names == ["a", "b"]

    def test_to_input_columns_types(self):
        c = DatasetContract(columns=[
            ColumnSpec("x", "INTEGER"),
        ])
        cols = c.to_input_columns()
        assert len(cols) == 1
        assert cols[0].Name == "x"
        assert cols[0].Type == "INTEGER"
