"""Typed ``ParameterDecl`` subtypes — one per ``models.py`` declaration variant.

``StringParam`` / ``IntegerParam`` / ``DateTimeParam`` map to the
three declaration types in ``models.py``. Each carries its own
``ParameterName`` at the constructor (single construction site);
controls and filter parameter bindings reference the parameter by
object ref.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from quicksight_gen.common.ids import ParameterName
from quicksight_gen.common.models import (
    DateTimeDefaultValues,
    DateTimeParameterDeclaration,
    IntegerParameterDeclaration,
    ParameterDeclaration,
    StringParameterDeclaration,
)
from quicksight_gen.common.tree._helpers import (
    TimeGranularity,
    _validate_literal,
)


@runtime_checkable
class ParameterDeclLike(Protocol):
    """Structural type for parameter declaration tree nodes."""
    name: ParameterName

    def emit(self) -> ParameterDeclaration: ...


@dataclass(eq=False)
class StringParam:
    """String-valued parameter declaration.

    Default values are passed as a list — single-valued parameters
    use ``[]`` for "no default" or ``["value"]`` for one default;
    multi-valued use ``["a", "b", "c"]``.
    """
    name: ParameterName
    default: list[str] = field(default_factory=list)
    multi_valued: bool = False

    def emit(self) -> ParameterDeclaration:
        return ParameterDeclaration(
            StringParameterDeclaration=StringParameterDeclaration(
                ParameterValueType=(
                    "MULTI_VALUED" if self.multi_valued else "SINGLE_VALUED"
                ),
                Name=self.name,
                DefaultValues={"StaticValues": self.default},
            ),
        )


@dataclass(eq=False)
class IntegerParam:
    """Integer-valued parameter declaration."""
    name: ParameterName
    default: list[int] = field(default_factory=list)
    multi_valued: bool = False

    def emit(self) -> ParameterDeclaration:
        return ParameterDeclaration(
            IntegerParameterDeclaration=IntegerParameterDeclaration(
                ParameterValueType=(
                    "MULTI_VALUED" if self.multi_valued else "SINGLE_VALUED"
                ),
                Name=self.name,
                DefaultValues={"StaticValues": self.default},
            ),
        )


@dataclass(eq=False)
class DateTimeParam:
    """DateTime parameter declaration.

    Pass ``time_granularity="DAY" | "HOUR" | "MINUTE" | …`` to bound
    the picker's resolution. Defaults take a ``DateTimeDefaultValues``
    so callers can pick between ``StaticValues`` (literal date),
    ``DynamicValue`` (data-driven), or ``RollingDate`` (e.g.
    ``{"Expression": "truncDate('DD', now())"}`` for "today").
    """
    name: ParameterName
    time_granularity: TimeGranularity | None = None
    default: DateTimeDefaultValues | None = None

    def __post_init__(self) -> None:
        _validate_literal(
            self.time_granularity, TimeGranularity,
            field_name="time_granularity",
        )

    def emit(self) -> ParameterDeclaration:
        return ParameterDeclaration(
            DateTimeParameterDeclaration=DateTimeParameterDeclaration(
                Name=self.name,
                TimeGranularity=self.time_granularity,
                DefaultValues=self.default,
            ),
        )
