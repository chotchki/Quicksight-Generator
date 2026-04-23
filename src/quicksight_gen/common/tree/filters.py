"""Filter primitives — ``FilterGroup`` (L.1.5) plus typed Filter
wrappers (L.1.6 — landing soon).

Filter groups carry their scope as object refs (``Sheet`` + ``[VisualLike]``)
and validate at the call site that scoped visuals belong to the
referenced sheet. Catches the wrong-sheet bug class — the type
checker carries the wiring; raise at construction confirms.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from quicksight_gen.common.ids import FilterGroupId
from quicksight_gen.common.models import (
    Filter,
    FilterScopeConfiguration,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
)
from quicksight_gen.common.models import FilterGroup as ModelFilterGroup

from quicksight_gen.common.tree.visuals import VisualLike

if TYPE_CHECKING:
    from quicksight_gen.common.tree.structure import Sheet


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

    ``filters`` is a list of ``models.Filter`` for now (typed Filter
    wrappers — CategoryFilter / NumericRangeFilter / TimeRangeFilter
    — land in L.1.6). Same shape as the existing builders so the
    migration is mechanical: existing ``Filter(CategoryFilter=
    CategoryFilter(...))`` calls drop straight in.
    """
    filter_group_id: FilterGroupId
    filters: list[Filter]
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
            Filters=self.filters,
        )
