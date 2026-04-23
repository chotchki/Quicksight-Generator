"""Field-well leaf nodes — ``Dim`` + ``Measure`` typed wrappers.

Every visual's field wells contain a mix of ``DimensionField`` and
``MeasureField`` entries (source / target columns, group-by fields,
aggregated values). These tree nodes wrap them with typed factories
(``Dim.date(...)``, ``Measure.sum(...)``) so construction-time typing
drives what the visual gets, rather than hand-wiring the underlying
models every time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from quicksight_gen.common.models import (
    CategoricalDimensionField,
    CategoricalMeasureField,
    ColumnIdentifier,
    DateDimensionField,
    DimensionField,
    MeasureField,
    NumericalAggregationFunction,
    NumericalDimensionField,
    NumericalMeasureField,
)
from quicksight_gen.common.tree.calc_fields import (
    CalcField,
    ColumnRef,
    _calc_field_in,
    _resolve_column,
)
from quicksight_gen.common.tree.datasets import Dataset


DimKind = Literal["categorical", "date", "numerical"]


@dataclass
class Dim:
    """One dimension field-well entry — typed wrapper that emits a
    ``DimensionField`` of the appropriate kind.

    ``dataset`` is a ``Dataset`` object ref — the locked L.1.7 hard
    switch. The dataset must be registered on the parent ``App`` (via
    ``app.add_dataset()``) for the analysis to emit.

    ``column`` accepts either a bare ``str`` (a real column on the
    dataset) or a ``CalcField`` object ref (an analysis-level
    calculated field). The CalcField ref carries the calc-field
    identity through the type checker — the App's emit-time
    validation catches references to unregistered calc fields.

    Default kind is ``categorical`` (the most common); use the
    ``date()`` / ``numerical()`` classmethods for the other variants.
    """
    dataset: Dataset
    field_id: str
    column: ColumnRef
    kind: DimKind = "categorical"

    @classmethod
    def date(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Dim:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="date")

    @classmethod
    def numerical(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Dim:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="numerical")

    def calc_field(self) -> CalcField | None:
        """The CalcField this Dim references, or None if it points at
        a real dataset column. Used by the dependency-graph walk."""
        return _calc_field_in(self.column)

    def emit(self) -> DimensionField:
        col = ColumnIdentifier(
            DataSetIdentifier=self.dataset.identifier,
            ColumnName=_resolve_column(self.column),
        )
        if self.kind == "date":
            return DimensionField(
                DateDimensionField=DateDimensionField(
                    FieldId=self.field_id, Column=col,
                ),
            )
        if self.kind == "numerical":
            return DimensionField(
                NumericalDimensionField=NumericalDimensionField(
                    FieldId=self.field_id, Column=col,
                ),
            )
        return DimensionField(
            CategoricalDimensionField=CategoricalDimensionField(
                FieldId=self.field_id, Column=col,
            ),
        )


# Aggregation kinds split into "categorical" (COUNT, DISTINCT_COUNT —
# read off any column type) and "numerical" (SUM, MAX, MIN, AVERAGE —
# require a numeric column). The split mirrors the underlying
# ``CategoricalMeasureField`` vs ``NumericalMeasureField`` distinction.
MeasureKind = Literal[
    "sum", "max", "min", "average",          # → NumericalMeasureField
    "count", "distinct_count",               # → CategoricalMeasureField
]


_NUMERICAL_AGG = {
    "sum": "SUM", "max": "MAX", "min": "MIN", "average": "AVERAGE",
}
_CATEGORICAL_AGG = {
    "count": "COUNT", "distinct_count": "DISTINCT_COUNT",
}


@dataclass
class Measure:
    """One value field-well entry — typed wrapper that emits a
    ``MeasureField`` with the appropriate aggregation shape.

    ``dataset`` is a ``Dataset`` object ref (L.1.7 hard switch). The
    dataset must be registered on the parent ``App`` for the analysis
    to emit.

    Use the classmethod factories for ergonomic construction:
    ``Measure.sum(...)``, ``Measure.distinct_count(...)``, etc.
    Aggregation kind determines which underlying model class is
    emitted (numerical aggregations on numeric columns,
    categorical on count-style aggregations).
    """
    dataset: Dataset
    field_id: str
    column: ColumnRef
    kind: MeasureKind

    @classmethod
    def sum(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="sum")

    @classmethod
    def max(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="max")

    @classmethod
    def min(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="min")

    @classmethod
    def average(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="average")

    @classmethod
    def count(cls, dataset: Dataset, field_id: str, column: ColumnRef) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="count")

    @classmethod
    def distinct_count(
        cls, dataset: Dataset, field_id: str, column: ColumnRef,
    ) -> Measure:
        return cls(
            dataset=dataset, field_id=field_id, column=column,
            kind="distinct_count",
        )

    def calc_field(self) -> CalcField | None:
        """The CalcField this Measure references, or None if it points
        at a real dataset column."""
        return _calc_field_in(self.column)

    def emit(self) -> MeasureField:
        col = ColumnIdentifier(
            DataSetIdentifier=self.dataset.identifier,
            ColumnName=_resolve_column(self.column),
        )
        if self.kind in _CATEGORICAL_AGG:
            return MeasureField(
                CategoricalMeasureField=CategoricalMeasureField(
                    FieldId=self.field_id,
                    Column=col,
                    AggregationFunction=_CATEGORICAL_AGG[self.kind],
                ),
            )
        return MeasureField(
            NumericalMeasureField=NumericalMeasureField(
                FieldId=self.field_id,
                Column=col,
                AggregationFunction=NumericalAggregationFunction(
                    SimpleNumericalAggregation=_NUMERICAL_AGG[self.kind],
                ),
            ),
        )
