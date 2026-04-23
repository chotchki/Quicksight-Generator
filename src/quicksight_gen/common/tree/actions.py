"""Typed drill action wrapper (L.1.10).

A ``Drill`` is one custom action attached to a typed Visual — left-click
or right-click on a data point fires it. The drill navigates to a
target sheet (same-sheet or cross-sheet) and optionally sets parameter
values from the clicked data point.

The L.1.10 typed wrapper keeps K.2's shape-validated parameter writes
(``DrillParam`` + ``DrillSourceField`` + ``ColumnShape``) and adds:

- ``target_sheet`` is a typed ``Sheet`` object ref, not a ``SheetId``
  string. The App's emit-time validation catches "drill into a sheet
  that isn't on this analysis" the same way the dataset and calc-field
  walks catch unregistered references.
- ``action_id`` is Optional — the App walker assigns
  ``act-s{sheet_idx}-v{visual_idx}-{action_idx}`` at emit time.

Visual subtypes (KPI / Table / BarChart / Sankey) accept a typed
``actions: list[Drill]`` field; their ``emit()`` passes the resolved
list into the underlying model's ``Actions`` slot.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar, Literal

from quicksight_gen.common.drill import (
    DrillResetSentinel,
    DrillSourceField,
    DrillWriteValue,
    cross_sheet_drill as _emit_cross_sheet_drill,
)
from quicksight_gen.common.drill import DrillParam as _DrillParam
from quicksight_gen.common.models import VisualCustomAction

from quicksight_gen.common.tree.parameters import ParameterDeclLike
# Sheet is referenced via TYPE_CHECKING — same trick as filters.py
# uses for the FilterGroup → Sheet ref. Avoids circular import.
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from quicksight_gen.common.tree.structure import Sheet


# Re-exports so user code only needs to import from quicksight_gen.common.tree:
DrillParam = _DrillParam  # K.2 shape-validated parameter spec — name + ColumnShape
__all__ = [
    "Drill",
    "DrillParam",
    "DrillSourceField",
    "DrillResetSentinel",
]


# A typed drill write — pairs a destination DrillParam with either a
# source field (read the value off the clicked data point) or a reset
# sentinel (clear the param to PASS).
DrillWrite = tuple[DrillParam, DrillWriteValue]


@dataclass(eq=False)
class Drill:
    """One custom action on a Visual.

    ``target_sheet`` is the destination ``Sheet`` object ref. Two
    binding modes:

    - **Cross-sheet drill** — pass an explicit ``target_sheet=sheet``.
      The drill navigates to that sheet (and writes parameter values
      to it).
    - **Same-sheet drill** (the walk-the-flow / re-render-around-new-anchor
      pattern) — leave ``target_sheet`` as ``None``. ``App._resolve_auto_ids``
      back-fills the field with the sheet that owns the visual carrying
      the drill, so the author never types ``target_sheet=this_sheet``
      when wiring a drill inside the function that builds the sheet.
      Resolves the chicken-and-egg cycle (sheet doesn't exist yet when
      the drill is constructed inside ``Sheet.add_visual(...)``) without
      a back-fill loop at the call site.

    ``writes`` is a list of ``(DrillParam, DrillSourceField | DrillResetSentinel)``
    tuples — same shape K.2 introduced. The ``DrillParam`` carries
    its own ``ColumnShape``; ``DrillSourceField.shape`` must match
    or ``cross_sheet_drill`` raises (call-site shape validation).

    ``trigger`` picks the click semantic — ``DATA_POINT_CLICK`` for
    left-click, ``DATA_POINT_MENU`` for right-click context menu.

    ``action_id`` is Optional — the App walker assigns one at emit
    time when not specified.

    ``name`` is the visible label QuickSight shows in the right-click
    menu (for DATA_POINT_MENU triggers). For DATA_POINT_CLICK actions
    the name doesn't surface in the UI but is still required by the
    underlying model.
    """
    writes: list[DrillWrite]
    name: str
    trigger: Literal["DATA_POINT_CLICK", "DATA_POINT_MENU"] = "DATA_POINT_CLICK"
    action_id: str | None = None
    target_sheet: "Sheet | None" = None

    _AUTO_KIND: ClassVar[str] = "drill"

    def emit(self) -> VisualCustomAction:
        assert self.action_id is not None, (
            "action_id wasn't resolved — App._resolve_auto_ids() must run."
        )
        assert self.target_sheet is not None, (
            "target_sheet wasn't resolved — App._resolve_auto_ids() must "
            "run before Drill.emit(). Same-sheet drills get back-filled "
            "with the owning sheet automatically."
        )
        return _emit_cross_sheet_drill(
            action_id=self.action_id,
            name=self.name,
            target_sheet=self.target_sheet.sheet_id,
            writes=self.writes,
            trigger=self.trigger,
        )
