"""Dataset column contracts and shared dataset-building helpers.

A DatasetContract declares the column interface a dataset produces.
The SQL is one implementation of that contract (against the demo schema);
customers swap in their own SQL. Everything downstream (visuals, filters,
drill-downs) binds to contract columns, not SQL specifics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    CustomSql,
    DataSet,
    DatasetParameter,
    DataSetUsageConfiguration,
    InputColumn,
    LogicalTable,
    LogicalTableSource,
    PhysicalTable,
    ResourcePermission,
)


class ColumnShape(Enum):
    """Application-level value shape of a drill-eligible column.

    Layered above the AWS coarse type (STRING/DATETIME/...) so that two
    columns sharing a wire type but representing different semantic values
    cannot be cross-wired to the same drill parameter. K.2 spike found a
    silent zero-row bug where ``exception_date`` (DATETIME) was bound to
    a SINGLE_VALUED string parameter; QuickSight coerced it to the full
    timestamp text ``"2026-04-07 00:00:00.000"`` which never matched the
    destination's ``posted_date`` column (also STRING but ``YYYY-MM-DD``
    formatted via TO_CHAR). The shape captures both the encoding and the
    semantic, so the typed drill helper can refuse the wiring at code-gen
    time instead of silently producing zero rows.

    Tag a column with a shape only if it's an actual drill source or
    destination — every other column stays ``shape=None`` and is rejected
    by ``DrillSourceField`` resolution.
    """

    # Date encodings ---------------------------------------------------
    # YYYY-MM-DD text, e.g. ``TO_CHAR(posted_at, 'YYYY-MM-DD')``. Compatible
    # with SINGLE_VALUED string params bound to TO_CHAR-formatted columns.
    DATE_YYYY_MM_DD_TEXT = "date_yyyy_mm_dd_text"
    # True DATETIME column, suitable for a DateTimeParameter target. Not
    # interchangeable with the YYYY-MM-DD text shape — different wire type
    # on both ends.
    DATETIME_DAY = "datetime_day"

    # Account identifiers — distinct nominal types so writing an
    # account_id into a parameter expecting a transfer_id fails.
    # SUBLEDGER_ACCOUNT_ID and LEDGER_ACCOUNT_ID are subtypes of
    # ACCOUNT_ID: a sub-ledger or ledger id is always a valid account
    # id, but not vice versa. Assignment compatibility encodes this.
    ACCOUNT_ID = "account_id"
    SUBLEDGER_ACCOUNT_ID = "subledger_account_id"
    LEDGER_ACCOUNT_ID = "ledger_account_id"
    # Concatenated display label, e.g. ``"Sasquatch Sips (gl-1850)"``.
    # Used as a single-string surrogate that is both human-readable
    # AND uniquely keyed (the embedded id disambiguates name
    # collisions). Wired to the K.4.8 Account Network anchor parameter
    # so the Sankey can self-walk: clicking a node delivers the node's
    # display label, the calc field compares displays, the dropdown
    # shows the same labels. Not assignable to ACCOUNT_ID because the
    # id-only consumer can't parse the label back out.
    ACCOUNT_DISPLAY = "account_display"

    # Transfer identifiers
    TRANSFER_ID = "transfer_id"
    TRANSFER_TYPE = "transfer_type"

    # PR identifiers
    SETTLEMENT_ID = "settlement_id"
    PAYMENT_ID = "payment_id"
    EXTERNAL_TXN_ID = "external_txn_id"

    def can_assign_to(self, other: "ColumnShape") -> bool:
        """True iff a value of ``self`` is acceptable into a ``other`` param.

        Identical shapes are always assignable. SUBLEDGER_ACCOUNT_ID and
        LEDGER_ACCOUNT_ID widen to ACCOUNT_ID (the destination
        ``daily_balances.account_id`` column holds both ledger and
        sub-ledger ids). Date encodings do NOT widen — DATETIME and
        YYYY-MM-DD text are different wire types and cross-wiring them
        is the K.2 bug class.
        """
        if self is other:
            return True
        if other is ColumnShape.ACCOUNT_ID and self in (
            ColumnShape.SUBLEDGER_ACCOUNT_ID,
            ColumnShape.LEDGER_ACCOUNT_ID,
        ):
            return True
        return False


@dataclass
class ColumnSpec:
    name: str
    type: str  # STRING | DECIMAL | INTEGER | DATETIME | BIT
    shape: ColumnShape | None = None  # only set for drill-eligible columns

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

    def column(self, name: str) -> ColumnSpec:
        for c in self.columns:
            if c.name == name:
                return c
        raise KeyError(
            f"Column {name!r} not declared on this contract. Known: "
            f"{self.column_names}"
        )


# Module-level registry of visual_identifier -> contract. Populated by
# build_dataset() at construction time so that downstream drill code can
# look up a column's shape from just the visual identifier (the same id
# the visuals pass as ``DataSetIdentifier=`` in field references) and
# the column name. The alternative — threading the contract through
# every visual call site — would fight the existing visual-builder
# shape (which already imports the ``DS_*`` constants).
_CONTRACT_REGISTRY: dict[str, DatasetContract] = {}


def register_contract(
    visual_identifier: str, contract: DatasetContract,
) -> None:
    """Register a visual_identifier -> contract mapping for shape lookup.

    The key is the visual identifier (e.g. ``"ar-ledger-balance-drift-ds"``),
    the same string the visuals use as ``DataSetIdentifier=`` and that the
    analysis maps to a real DataSet ARN via DataSetIdentifierDeclaration.

    Idempotent for the same (visual_identifier, contract) pair; raises if a
    different contract is already registered under the same identifier
    (catches accidental identifier collisions).
    """
    existing = _CONTRACT_REGISTRY.get(visual_identifier)
    if existing is not None and existing is not contract:
        raise ValueError(
            f"visual_identifier {visual_identifier!r} already registered to "
            f"a different contract instance. Two datasets cannot share an "
            f"identifier."
        )
    _CONTRACT_REGISTRY[visual_identifier] = contract


def get_contract(visual_identifier: str) -> DatasetContract:
    """Look up the contract registered under ``visual_identifier``.

    Raises ``KeyError`` if not registered — usually means the dataset
    hasn't been built yet in the current process. Tests / generators
    should call ``build_dataset()`` before reaching code that resolves
    drill source fields.
    """
    try:
        return _CONTRACT_REGISTRY[visual_identifier]
    except KeyError:
        raise KeyError(
            f"No contract registered for visual_identifier "
            f"{visual_identifier!r}. Call build_dataset() for it before "
            f"resolving drill sources."
        )


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
    visual_identifier: str,
    dataset_parameters: list[DatasetParameter] | None = None,
) -> DataSet:
    """Build an AWS-shape DataSet.

    ``dataset_parameters``: optional list of dataset-level parameters
    that get substituted into ``sql`` via the ``<<$paramName>>``
    syntax at QuickSight query time. Bridge to analysis params via
    ``MappedDataSetParameters`` on the analysis ParameterDeclaration.
    """
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
    register_contract(visual_identifier, contract)
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
        DatasetParameters=dataset_parameters,
    )
