"""Typed Filter + Parameter control wrappers (L.1.9).

Each control binds to a typed source by object reference: parameter
controls take a ``ParameterDeclLike`` (the parameter declaration node
they read/write); filter controls take a ``FilterLike`` (the inner
filter their UI drives). At emit time the wrapper reads
``parameter.name`` or ``filter.filter_id`` to populate the underlying
``models.SourceParameterName`` / ``SourceFilterId``.

Naming convention: same as L.1.6 — tree wrappers use a clean,
unsuffixed name that doesn't collide with the underlying
``models.*Control`` classes (``Parameter*Control``, ``Filter*Control``).
User code reads:

    from quicksight_gen.common.tree import (
        ParameterDropdown, ParameterSlider, FilterDropdown, ...,
    )

``LinkedValues`` / ``StaticValues`` typed wrappers replace the
existing dict-shaped ``SelectableValues`` argument — ``LinkedValues``
takes a typed ``Dataset`` ref + column name (catches "dropdown
populated from undeclared dataset" via the App's dependency graph
walk).

Auto-IDs (L.1.8.5 extension): ``control_id`` fields are Optional;
the App walker assigns position-indexed IDs at emit time
(``pc-{kind}-s{sheet_idx}-{control_idx}`` for parameter controls,
``fc-{kind}-s{sheet_idx}-{control_idx}`` for filter controls).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from quicksight_gen.common.models import (
    FilterControl,
    ParameterControl,
)
from quicksight_gen.common.models import (
    FilterCrossSheetControl as ModelFilterCrossSheetControl,
)
from quicksight_gen.common.models import (
    FilterDateTimePickerControl as ModelFilterDateTimePickerControl,
)
from quicksight_gen.common.models import (
    FilterDropDownControl as ModelFilterDropDownControl,
)
from quicksight_gen.common.models import (
    FilterSliderControl as ModelFilterSliderControl,
)
from quicksight_gen.common.models import (
    ParameterDateTimePickerControl as ModelParameterDateTimePickerControl,
)
from quicksight_gen.common.models import (
    ParameterDropDownControl as ModelParameterDropDownControl,
)
from quicksight_gen.common.models import (
    ParameterSliderControl as ModelParameterSliderControl,
)

from quicksight_gen.common.tree.datasets import Column, Dataset
from quicksight_gen.common.tree.filters import FilterLike
from quicksight_gen.common.tree.parameters import ParameterDeclLike


# ---------------------------------------------------------------------------
# Selectable values wrappers — typed alternatives to the dict-shaped
# SelectableValues argument used by the dropdown controls.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class StaticValues:
    """Restrict the dropdown to a fixed list of options."""
    values: list[str]

    def emit(self) -> dict[str, Any]:
        return {"Values": list(self.values)}


@dataclass(frozen=True)
class LinkedValues:
    """Auto-populate the dropdown's options from a dataset column.

    Two forms (the typed-Column form is preferred — L.1.17):

    - ``LinkedValues(ds["column_name"])`` — single positional Column,
      dataset implicit. Validated against the contract at
      construction.
    - ``LinkedValues(dataset=ds, column="column_name")`` — escape
      hatch for unvalidated string. Dataset must be passed.

    The Dataset participates in the L.1.7 dependency-graph walk via
    the control's ``datasets()`` method.
    """
    column: str | Column
    dataset: Dataset | None = None

    def __post_init__(self) -> None:
        if isinstance(self.column, Column):
            inferred = self.column.dataset
            if self.dataset is None:
                # frozen=True — bypass __setattr__ guard.
                object.__setattr__(self, "dataset", inferred)
            elif self.dataset is not inferred:
                raise ValueError(
                    f"LinkedValues dataset mismatch: column "
                    f"{self.column.name!r} belongs to "
                    f"{inferred.identifier!r}, but dataset arg "
                    f"is {self.dataset.identifier!r}."
                )
        elif self.dataset is None:
            raise ValueError(
                "LinkedValues: dataset is required when column is a "
                "bare string. Prefer ``LinkedValues(ds[\"column\"])`` "
                "for the validated path."
            )

    def emit(self) -> dict[str, Any]:
        column_name = (
            self.column.name if isinstance(self.column, Column)
            else self.column
        )
        return {
            "LinkToDataSetColumn": {
                "DataSetIdentifier": self.dataset.identifier,
                "ColumnName": column_name,
            },
        }


SelectableValues = StaticValues | LinkedValues


# ---------------------------------------------------------------------------
# Control protocols — Sheet.add_parameter_control + add_filter_control
# accept any node satisfying these structural types.
# ---------------------------------------------------------------------------

@runtime_checkable
class ParameterControlLike(Protocol):
    """Tree-level parameter control nodes.

    ``datasets()`` participates in the L.1.7 dependency-graph walk —
    controls with ``LinkedValues`` populate from a ``Dataset``, and
    that's a dep. Controls with static values return an empty set.
    """
    control_id: str | None

    def emit(self) -> ParameterControl: ...

    def datasets(self) -> set[Dataset]: ...


@runtime_checkable
class FilterControlLike(Protocol):
    """Tree-level filter control nodes.

    ``datasets()`` participates in the L.1.7 dependency-graph walk —
    same shape as ``ParameterControlLike.datasets()``.
    """
    control_id: str | None

    def emit(self) -> FilterControl: ...

    def datasets(self) -> set[Dataset]: ...


# ---------------------------------------------------------------------------
# Parameter controls
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class ParameterDropdown:
    """Dropdown control bound to a ``ParameterDeclLike`` parameter.

    ``parameter`` is the typed parameter declaration the control
    reads/writes — at emit time, the control's ``SourceParameterName``
    becomes ``parameter.name``. The type checker catches "control
    bound to a parameter that doesn't exist" at the wiring site.

    ``selectable_values`` accepts a ``StaticValues(["a", "b"])`` for a
    fixed option list or ``LinkedValues(dataset, column)`` for an
    auto-populated list. The ``LinkedValues.dataset`` ref participates
    in the App's dependency graph.

    ``hidden_select_all=True`` suppresses the "Select all" entry —
    needed for SINGLE_SELECT dropdowns where empty/All semantics don't
    apply (e.g. a Sankey anchor that needs exactly one value).
    """
    parameter: ParameterDeclLike
    title: str
    type: Literal["SINGLE_SELECT", "MULTI_SELECT"] = "SINGLE_SELECT"
    selectable_values: SelectableValues | None = None
    hidden_select_all: bool = False
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "dropdown"

    def datasets(self) -> set[Dataset]:
        """Datasets this control references (via LinkedValues if any)."""
        if isinstance(self.selectable_values, LinkedValues):
            return {self.selectable_values.dataset}
        return set()

    def emit(self) -> ParameterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        display_options: dict[str, Any] | None = None
        if self.hidden_select_all:
            display_options = {
                "SelectAllOptions": {"Visibility": "HIDDEN"},
            }
        return ParameterControl(
            Dropdown=ModelParameterDropDownControl(
                ParameterControlId=self.control_id,
                Title=self.title,
                SourceParameterName=self.parameter.name,
                Type=self.type,
                SelectableValues=(
                    self.selectable_values.emit()
                    if self.selectable_values is not None else None
                ),
                DisplayOptions=display_options,
            ),
        )


@dataclass(eq=False)
class ParameterSlider:
    """Slider control bound to a numeric parameter."""
    parameter: ParameterDeclLike
    title: str
    minimum_value: float
    maximum_value: float
    step_size: float
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "slider"

    def datasets(self) -> set[Dataset]:
        return set()

    def emit(self) -> ParameterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        return ParameterControl(
            Slider=ModelParameterSliderControl(
                ParameterControlId=self.control_id,
                Title=self.title,
                SourceParameterName=self.parameter.name,
                MinimumValue=self.minimum_value,
                MaximumValue=self.maximum_value,
                StepSize=self.step_size,
            ),
        )


@dataclass(eq=False)
class ParameterDateTimePicker:
    """Date/time picker control bound to a DateTime parameter."""
    parameter: ParameterDeclLike
    title: str
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "datetime"

    def datasets(self) -> set[Dataset]:
        return set()

    def emit(self) -> ParameterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        return ParameterControl(
            DateTimePicker=ModelParameterDateTimePickerControl(
                ParameterControlId=self.control_id,
                Title=self.title,
                SourceParameterName=self.parameter.name,
            ),
        )


# ---------------------------------------------------------------------------
# Filter controls
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class FilterDropdown:
    """Dropdown control bound to an inner filter (``CategoryFilter``).

    ``filter`` is the typed inner filter the dropdown drives — at
    emit time, the control's ``SourceFilterId`` becomes
    ``filter.filter_id``. The filter must be inside a ``FilterGroup``
    that's been registered on the analysis.
    """
    filter: FilterLike
    title: str
    type: Literal["SINGLE_SELECT", "MULTI_SELECT"] = "MULTI_SELECT"
    selectable_values: SelectableValues | None = None
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "dropdown"

    def datasets(self) -> set[Dataset]:
        if isinstance(self.selectable_values, LinkedValues):
            return {self.selectable_values.dataset}
        return set()

    def emit(self) -> FilterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        return FilterControl(
            Dropdown=ModelFilterDropDownControl(
                FilterControlId=self.control_id,
                Title=self.title,
                SourceFilterId=self.filter.filter_id,
                Type=self.type,
                SelectableValues=(
                    self.selectable_values.emit()
                    if self.selectable_values is not None else None
                ),
            ),
        )


@dataclass(eq=False)
class FilterSlider:
    """Slider control bound to a NumericRangeFilter."""
    filter: FilterLike
    title: str
    minimum_value: float
    maximum_value: float
    step_size: float
    type: Literal["SINGLE_POINT", "RANGE"] = "RANGE"
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "slider"

    def datasets(self) -> set[Dataset]:
        return set()

    def emit(self) -> FilterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        return FilterControl(
            Slider=ModelFilterSliderControl(
                FilterControlId=self.control_id,
                Title=self.title,
                SourceFilterId=self.filter.filter_id,
                MinimumValue=self.minimum_value,
                MaximumValue=self.maximum_value,
                StepSize=self.step_size,
                Type=self.type,
            ),
        )


@dataclass(eq=False)
class FilterDateTimePicker:
    """Date/time picker control bound to a TimeRangeFilter."""
    filter: FilterLike
    title: str
    type: Literal["SINGLE_VALUED", "DATE_RANGE"] = "DATE_RANGE"
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "datetime"

    def datasets(self) -> set[Dataset]:
        return set()

    def emit(self) -> FilterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        return FilterControl(
            DateTimePicker=ModelFilterDateTimePickerControl(
                FilterControlId=self.control_id,
                Title=self.title,
                SourceFilterId=self.filter.filter_id,
                Type=self.type,
            ),
        )


@dataclass(eq=False)
class FilterCrossSheet:
    """Cross-sheet filter control — surfaces the filter on multiple
    sheets via the same bound filter.

    No title; the Cross-Sheet control inherits its UI from the
    underlying filter's primary control.
    """
    filter: FilterLike
    control_id: str | None = None

    _AUTO_KIND: ClassVar[str] = "crosssheet"

    def datasets(self) -> set[Dataset]:
        return set()

    def emit(self) -> FilterControl:
        assert self.control_id is not None, (
            "control_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        return FilterControl(
            CrossSheet=ModelFilterCrossSheetControl(
                FilterControlId=self.control_id,
                SourceFilterId=self.filter.filter_id,
            ),
        )
