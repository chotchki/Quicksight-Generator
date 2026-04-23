"""Typed analysis-level calculated fields (L.1.8).

A ``CalcField`` is the typed wrapper around the existing per-app
``CalculatedField`` dict (``{Name, DataSetIdentifier, Expression}``).
Visuals and filters reference calc fields the same way they reference
real dataset columns — by passing the column to ``Dim`` / ``Measure``
/ ``CategoryFilter`` / ``NumericRangeFilter``. The column slot accepts
either a bare ``str`` (a real column or a calc-field name) OR a
``CalcField`` object reference; the typed ref carries the validated
calc-field identity through the type checker.

Validation (L.1.8):

- ``Analysis.add_calc_field`` rejects duplicate calc-field names
  within an analysis.
- ``App._validate_calc_field_references`` (added in L.1.8) raises if
  any tree-referenced ``CalcField`` isn't registered on the Analysis.
  Catches "filter references calc field that doesn't exist" and
  "calc field declared but never used".

Dependency graph (L.1.7 + L.1.8):

- Each ``CalcField`` carries a ``Dataset`` ref. The CalcField's
  dataset participates in ``App.dataset_dependencies()`` so
  declaring a calc field on dataset D establishes D as a dep even
  when no visual directly references D's columns.
"""

from __future__ import annotations

from dataclasses import dataclass

from quicksight_gen.common.tree.datasets import Dataset


@dataclass(frozen=True)
class CalcField:
    """Tree node for one analysis-level calculated field.

    ``name`` is the column-style identifier visuals/filters reference
    (e.g. ``"is_anchor_edge"`` — the existing ``CF_INV_*`` constant
    string values). ``dataset`` is the ``Dataset`` object ref the
    expression evaluates against. ``expression`` is the QuickSight
    calc expression (e.g. ``"ifelse({source} = ${pAnchor}, 'yes', 'no')"``).

    Frozen because CalcField is referenced by object identity from
    Dim/Measure/Filter column slots and used as a registry key —
    must be hashable.

    Emits a plain dict that drops straight into
    ``AnalysisDefinition.CalculatedFields`` — same shape the existing
    builders write today.
    """
    name: str
    dataset: Dataset
    expression: str

    def emit(self) -> dict:
        return {
            "Name": self.name,
            "DataSetIdentifier": self.dataset.identifier,
            "Expression": self.expression,
        }


# Type alias used everywhere a tree node accepts a column reference.
# Bare strings (real dataset columns) and CalcField object refs are
# both valid; the resolver below pulls the column name out at emit
# time. CalcField refs let the type checker carry the calc-field
# identity through the wiring + the dependency-graph walk pick up
# the calc field's dataset.
ColumnRef = str | CalcField


def _resolve_column(column: ColumnRef) -> str:
    """Read the column-name string off a ``ColumnRef``."""
    if isinstance(column, CalcField):
        return column.name
    return column


def _calc_field_in(column: ColumnRef) -> CalcField | None:
    """Return the CalcField if ``column`` is one, else ``None``.

    Used by the dependency-graph walk to harvest CalcField refs from
    Dim / Measure / Filter column slots.
    """
    if isinstance(column, CalcField):
        return column
    return None
