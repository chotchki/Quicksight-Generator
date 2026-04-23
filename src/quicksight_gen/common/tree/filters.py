"""Filter primitives — typed Filter wrappers + ``FilterGroup``.

Filter groups carry their scope as object refs (``Sheet`` + ``[VisualLike]``)
and validate at the call site that scoped visuals belong to the
referenced sheet. Catches the wrong-sheet bug class — the type
checker carries the wiring; raise at construction confirms.

Typed Filter wrappers (``CategoryFilter`` / ``NumericRangeFilter`` /
``TimeRangeFilter``) sit alongside the FilterGroup. They share names
with the underlying ``models.py`` classes — models are aliased on
import so user-facing code reads cleanly:

    from quicksight_gen.common.tree import CategoryFilter, FilterGroup

The ``NumericRangeFilter``'s ``minimum_parameter`` /
``maximum_parameter`` fields take a ``ParameterDeclLike`` object ref —
the type checker catches "filter bound to undeclared parameter" at
the wiring site, where the existing string-keyed ``Parameter=name``
pattern lets typos through to deploy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from quicksight_gen.common.ids import FilterGroupId
from quicksight_gen.common.models import (
    CategoryFilterConfiguration,
    ColumnIdentifier,
    Filter,
    FilterScopeConfiguration,
    NumericRangeFilterValue,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
)
from quicksight_gen.common.models import CategoryFilter as ModelCategoryFilter
from quicksight_gen.common.models import FilterGroup as ModelFilterGroup
from quicksight_gen.common.models import NumericRangeFilter as ModelNumericRangeFilter
from quicksight_gen.common.models import TimeRangeFilter as ModelTimeRangeFilter

from quicksight_gen.common.tree.calc_fields import (
    CalcField,
    ColumnRef,
    _calc_field_in,
    _resolve_column,
)
from quicksight_gen.common.tree.datasets import Dataset
from quicksight_gen.common.tree.parameters import ParameterDeclLike
from quicksight_gen.common.tree.visuals import VisualLike

if TYPE_CHECKING:
    from quicksight_gen.common.tree.structure import Sheet


# ---------------------------------------------------------------------------
# FilterLike Protocol — the type FilterGroup.filters accepts.
# ---------------------------------------------------------------------------

@runtime_checkable
class FilterLike(Protocol):
    """Structural type for tree-level filter nodes.

    Each typed wrapper (``CategoryFilter`` / ``NumericRangeFilter`` /
    ``TimeRangeFilter``) satisfies this Protocol — exposes a
    ``filter_id``, the underlying ``dataset`` (object ref), and emits
    a ``models.Filter``. The ``dataset`` field participates in the
    L.1.7 dependency-graph walk.
    """
    filter_id: str
    dataset: Dataset

    def emit(self) -> Filter: ...


# ---------------------------------------------------------------------------
# Typed Filter wrappers
# ---------------------------------------------------------------------------

CategoryMatchOperator = Literal[
    "CONTAINS", "EQUALS", "DOES_NOT_EQUAL", "STARTS_WITH",
]


@dataclass
class CategoryFilter:
    """Filter on a categorical (string) column or calc field.

    ``dataset`` is a ``Dataset`` object ref (L.1.7 hard switch).

    Default match operator ``"CONTAINS"`` matches the
    ``FilterListConfiguration`` shape used by every CategoryFilter in
    the existing builders — pass ``["yes"]`` for the calc-field 'yes'
    sentinel pattern, or pass an explicit list of category values to
    include.

    ``column`` may name a real dataset column or an analysis-level
    calc field — both resolve to a ``ColumnIdentifier`` against the
    given dataset.
    """
    filter_id: str
    dataset: Dataset
    column: ColumnRef
    values: list[str]
    match_operator: CategoryMatchOperator = "CONTAINS"

    def calc_field(self) -> CalcField | None:
        """The CalcField this filter references, or None if it points
        at a real dataset column."""
        return _calc_field_in(self.column)

    def emit(self) -> Filter:
        return Filter(
            CategoryFilter=ModelCategoryFilter(
                FilterId=self.filter_id,
                Column=ColumnIdentifier(
                    DataSetIdentifier=self.dataset.identifier,
                    ColumnName=_resolve_column(self.column),
                ),
                Configuration=CategoryFilterConfiguration(
                    FilterListConfiguration={
                        "MatchOperator": self.match_operator,
                        "CategoryValues": self.values,
                    },
                ),
            ),
        )


NullOption = Literal["NON_NULLS_ONLY", "ALL_VALUES", "NULLS_ONLY"]


@dataclass
class NumericRangeFilter:
    """Filter on a numeric column. Range bounds may be literals
    (``minimum_value`` / ``maximum_value``) or parameter-bound
    (``minimum_parameter`` / ``maximum_parameter`` — object refs to a
    ``ParameterDeclLike``).

    Construction-time check: at most one of (``minimum_value``,
    ``minimum_parameter``) is set; same for the maximum side. The
    parameter-binding object refs catch "bound to a parameter that
    doesn't exist" at the wiring site (the type checker resolves
    ``param.name``; if the param ref is ``None`` you get a static
    bound or no bound).
    """
    filter_id: str
    dataset: Dataset
    column: ColumnRef
    minimum_parameter: ParameterDeclLike | None = None
    minimum_value: float | None = None
    maximum_parameter: ParameterDeclLike | None = None
    maximum_value: float | None = None
    null_option: NullOption = "NON_NULLS_ONLY"
    include_minimum: bool | None = None
    include_maximum: bool | None = None

    def __post_init__(self) -> None:
        if self.minimum_parameter is not None and self.minimum_value is not None:
            raise ValueError(
                f"NumericRangeFilter {self.filter_id!r}: specify either "
                f"minimum_parameter or minimum_value, not both."
            )
        if self.maximum_parameter is not None and self.maximum_value is not None:
            raise ValueError(
                f"NumericRangeFilter {self.filter_id!r}: specify either "
                f"maximum_parameter or maximum_value, not both."
            )

    def _range_value(
        self, parameter: ParameterDeclLike | None, value: float | None,
    ) -> NumericRangeFilterValue | None:
        if parameter is not None:
            return NumericRangeFilterValue(Parameter=parameter.name)
        if value is not None:
            return NumericRangeFilterValue(StaticValue=value)
        return None

    def calc_field(self) -> CalcField | None:
        return _calc_field_in(self.column)

    def emit(self) -> Filter:
        return Filter(
            NumericRangeFilter=ModelNumericRangeFilter(
                FilterId=self.filter_id,
                Column=ColumnIdentifier(
                    DataSetIdentifier=self.dataset.identifier,
                    ColumnName=_resolve_column(self.column),
                ),
                NullOption=self.null_option,
                RangeMinimum=self._range_value(
                    self.minimum_parameter, self.minimum_value,
                ),
                RangeMaximum=self._range_value(
                    self.maximum_parameter, self.maximum_value,
                ),
                IncludeMinimum=self.include_minimum,
                IncludeMaximum=self.include_maximum,
            ),
        )


@dataclass
class TimeRangeFilter:
    """Filter on a date / datetime column.

    ``dataset`` is a ``Dataset`` object ref (L.1.7 hard switch).
    ``column`` is a ``ColumnRef`` — a real column or a ``CalcField``.

    ``minimum`` and ``maximum`` are passthrough dicts for now (the
    existing usage takes a variety of shapes — RollingDate, StaticValue,
    Parameter — and lifting all of them under typed wrappers can wait
    for the L.2/L.3/L.4 ports to surface concrete needs).
    """
    filter_id: str
    dataset: Dataset
    column: ColumnRef
    minimum: dict[str, Any] | None = None
    maximum: dict[str, Any] | None = None
    null_option: NullOption = "NON_NULLS_ONLY"
    time_granularity: str | None = None
    include_minimum: bool | None = None
    include_maximum: bool | None = None

    def calc_field(self) -> CalcField | None:
        return _calc_field_in(self.column)

    def emit(self) -> Filter:
        return Filter(
            TimeRangeFilter=ModelTimeRangeFilter(
                FilterId=self.filter_id,
                Column=ColumnIdentifier(
                    DataSetIdentifier=self.dataset.identifier,
                    ColumnName=_resolve_column(self.column),
                ),
                NullOption=self.null_option,
                TimeGranularity=self.time_granularity,
                RangeMinimumValue=self.minimum,
                RangeMaximumValue=self.maximum,
                IncludeMinimum=self.include_minimum,
                IncludeMaximum=self.include_maximum,
            ),
        )


@dataclass
class FilterGroup:
    """Tree node for one analysis-level filter group.

    Construct with ``FilterGroup(filter_group_id=..., filters=[...])``,
    then attach scope by chaining ``.scope_visuals(sheet, [v1, v2])``
    or ``.scope_sheet(sheet)``. Both call methods validate immediately:

    - ``scope_visuals`` raises if any visual isn't on the given sheet
      (catches the wrong-sheet bug at the call site).
    - ``scope_sheet`` is the all-visuals-on-sheet shortcut.

    Multiple scope entries are allowed — the same FilterGroup can
    apply to (visual subset on sheet A) plus (all visuals on sheet B).
    Each entry emits its own ``SheetVisualScopingConfiguration``.

    ``filters`` takes a list of typed ``FilterLike`` wrappers
    (``CategoryFilter`` / ``NumericRangeFilter`` / ``TimeRangeFilter``
    above). Each wrapper's ``emit()`` returns a ``models.Filter`` at
    emission time. Parameter-bound filters (NumericRangeFilter with
    ``minimum_parameter`` / ``maximum_parameter``) carry object refs
    to ``ParameterDeclLike`` nodes — the type checker catches
    "filter bound to undeclared parameter" at the wiring site.
    """
    filter_group_id: FilterGroupId
    filters: list[FilterLike]
    cross_dataset: Literal["SINGLE_DATASET", "ALL_DATASETS"] = "SINGLE_DATASET"
    enabled: bool = True
    _scope_entries: list[tuple["Sheet", list[VisualLike] | None]] = field(
        default_factory=list, init=False, repr=False,
    )

    def scope_visuals(
        self, sheet: "Sheet", visuals: list[VisualLike],
    ) -> FilterGroup:
        """Scope this filter to specific visuals on a sheet.

        Construction-time check: every visual must already be registered
        on the given sheet via ``sheet.add_visual()``. Cross-sheet
        wiring is the bug class this catches — without the check, a
        scope mixing visuals from sheet A with sheet B's identifier
        emits a SheetVisualScopingConfiguration that silently drops
        the off-sheet visual at deploy time.
        """
        for v in visuals:
            if v not in sheet.visuals:
                raise ValueError(
                    f"Visual {v.visual_id!r} isn't registered on sheet "
                    f"{sheet.sheet_id!r} — register it via "
                    f"sheet.add_visual() before scoping a FilterGroup to it."
                )
        self._scope_entries.append((sheet, list(visuals)))
        return self

    def datasets(self) -> set[Dataset]:
        """Datasets this group's filters reference (object refs)."""
        return {f.dataset for f in self.filters}

    def calc_fields(self) -> set[CalcField]:
        """CalcFields this group's filters reference."""
        deps: set[CalcField] = set()
        for f in self.filters:
            if (cf := f.calc_field()) is not None:
                deps.add(cf)
        return deps

    def scope_sheet(self, sheet: "Sheet") -> FilterGroup:
        """Scope this filter to ALL visuals on a sheet.

        Equivalent to the existing ``_selected_sheets_scope([sheet_id])``
        helper — emits ``Scope=ALL_VISUALS`` on the sheet's
        SheetVisualScopingConfiguration, no per-visual list.
        """
        self._scope_entries.append((sheet, None))
        return self

    def emit(self) -> ModelFilterGroup:
        if not self._scope_entries:
            raise ValueError(
                f"FilterGroup {self.filter_group_id!r} has no scope — "
                f"call scope_visuals() or scope_sheet() before emitting."
            )
        configs = []
        for sheet, visuals in self._scope_entries:
            if visuals is None:
                configs.append(SheetVisualScopingConfiguration(
                    SheetId=sheet.sheet_id,
                    Scope=SheetVisualScopingConfiguration.ALL_VISUALS,
                ))
            else:
                configs.append(SheetVisualScopingConfiguration(
                    SheetId=sheet.sheet_id,
                    Scope=SheetVisualScopingConfiguration.SELECTED_VISUALS,
                    VisualIds=[v.visual_id for v in visuals],
                ))
        return ModelFilterGroup(
            FilterGroupId=self.filter_group_id,
            CrossDataset=(
                ModelFilterGroup.SINGLE_DATASET
                if self.cross_dataset == "SINGLE_DATASET"
                else ModelFilterGroup.ALL_DATASETS
            ),
            ScopeConfiguration=FilterScopeConfiguration(
                SelectedSheets=SelectedSheetsFilterScopeConfiguration(
                    SheetVisualScopingConfigurations=configs,
                ),
            ),
            Status=(
                ModelFilterGroup.ENABLED
                if self.enabled else ModelFilterGroup.DISABLED
            ),
            Filters=[f.emit() for f in self.filters],
        )
