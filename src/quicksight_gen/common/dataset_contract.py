"""Dataset column contracts and shared dataset-building helpers.

A DatasetContract declares the column interface a dataset produces.
The SQL is one implementation of that contract (against the demo schema);
customers swap in their own SQL. Everything downstream (visuals, filters,
drill-downs) binds to contract columns, not SQL specifics.
"""

from __future__ import annotations

from dataclasses import dataclass

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    CustomSql,
    DataSet,
    DataSetUsageConfiguration,
    InputColumn,
    LogicalTable,
    LogicalTableSource,
    PhysicalTable,
    ResourcePermission,
)


@dataclass
class ColumnSpec:
    name: str
    type: str  # STRING | DECIMAL | INTEGER | DATETIME | BIT

    def to_input_column(self) -> InputColumn:
        return InputColumn(Name=self.name, Type=self.type)


@dataclass
class DatasetContract:
    columns: list[ColumnSpec]

    def to_input_columns(self) -> list[InputColumn]:
        return [c.to_input_column() for c in self.columns]

    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


DATASET_ACTIONS = [
    "quicksight:DescribeDataSet",
    "quicksight:DescribeDataSetPermissions",
    "quicksight:PassDataSet",
    "quicksight:DescribeIngestion",
    "quicksight:ListIngestions",
    "quicksight:UpdateDataSet",
    "quicksight:DeleteDataSet",
    "quicksight:CreateIngestion",
    "quicksight:CancelIngestion",
    "quicksight:UpdateDataSetPermissions",
]


def dataset_permissions(cfg: Config) -> list[ResourcePermission] | None:
    if not cfg.principal_arns:
        return None
    return [
        ResourcePermission(Principal=arn, Actions=DATASET_ACTIONS)
        for arn in cfg.principal_arns
    ]


def build_dataset(
    cfg: Config,
    dataset_id: str,
    name: str,
    table_key: str,
    sql: str,
    contract: DatasetContract,
) -> DataSet:
    columns = contract.to_input_columns()
    physical = {
        table_key: PhysicalTable(
            CustomSql=CustomSql(
                Name=name,
                DataSourceArn=cfg.datasource_arn,
                SqlQuery=sql,
                Columns=columns,
            )
        )
    }
    logical = {
        f"{table_key}-logical": LogicalTable(
            Alias=name,
            Source=LogicalTableSource(PhysicalTableId=table_key),
        )
    }
    return DataSet(
        AwsAccountId=cfg.aws_account_id,
        DataSetId=dataset_id,
        Name=name,
        PhysicalTableMap=physical,
        LogicalTableMap=logical,
        ImportMode="DIRECT_QUERY",
        DataSetUsageConfiguration=DataSetUsageConfiguration(),
        Permissions=dataset_permissions(cfg),
        Tags=cfg.tags(),
    )
