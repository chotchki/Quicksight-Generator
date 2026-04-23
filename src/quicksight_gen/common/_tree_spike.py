"""L.0 spike: minimal tree primitives, scoped to the Investigation
Account Network sheet.

Goal of this spike: validate that a tree-shaped builder emits the same
``SheetDefinition`` as the existing imperative builder
(``_build_account_network_sheet`` in ``apps/investigation/analysis.py``).
The contract is byte-identity through ``to_aws_json()``.

This is INTENTIONALLY minimal:

- The tree's leaves (visual + control nodes) delegate to the existing
  private builder helpers in ``apps/investigation/visuals.py`` and
  ``apps/investigation/filters.py``. The spike validates composition
  (parent/child wiring, layout slots referencing visual nodes by object,
  emit ordering) — not visual-builder mechanics. L.1 will lift those
  mechanics into proper tree primitives.
- Only the ``SheetDefinition`` level is modeled. Analysis-level pieces
  (parameters, calc fields, filter groups, dataset declarations) stay
  out of the spike's scope.
- The cross-reference shape is the locked-decision object-ref form:
  layout slots reference ``VisualNode`` instances directly, not
  ``VisualId`` strings. The visual id is resolved from the referenced
  node at emit time.

Comparison test: ``tests/test_l0_spike.py`` asserts byte-identity at the
``to_aws_json()`` level between the existing builder and this module's
``build_account_network_sheet_via_tree``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from quicksight_gen.common.ids import SheetId, VisualId
from quicksight_gen.common.models import (
    GridLayoutConfiguration,
    GridLayoutElement,
    Layout,
    LayoutConfiguration,
    ParameterControl,
    SheetDefinition,
    Visual,
)


# ---------------------------------------------------------------------------
# Tree node types — minimum surface for the spike.
# ---------------------------------------------------------------------------

@dataclass
class VisualNode:
    """Tree node wrapping one Visual.

    The node carries the visual_id (the tree's identity for cross-refs)
    and a builder callable that produces the underlying ``Visual`` at
    emit time. Spike-only: in L.1 this collapses into typed Visual
    subtypes that produce their own emission directly.
    """
    visual_id: VisualId
    builder: Callable[[], Visual]

    def emit(self) -> Visual:
        return self.builder()


@dataclass
class ParameterControlNode:
    """Tree node wrapping one ParameterControl. Same delegation pattern
    as ``VisualNode``."""
    builder: Callable[[], ParameterControl]

    def emit(self) -> ParameterControl:
        return self.builder()


@dataclass
class GridSlot:
    """One placement in the sheet's grid layout.

    Holds an OBJECT reference to the placed ``VisualNode`` — the
    locked decision is cross-references via object refs, not via
    ``VisualId`` strings. The element id is read off the referenced
    node at emit time.
    """
    visual: VisualNode
    col_span: int
    row_span: int
    col_index: int

    def emit(self) -> GridLayoutElement:
        return GridLayoutElement(
            ElementId=self.visual.visual_id,
            ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=self.col_span,
            RowSpan=self.row_span,
            ColumnIndex=self.col_index,
        )


@dataclass
class SheetNode:
    """Tree root for the spike. Holds visuals, controls, and layout.

    Visuals must be registered via ``add_visual()`` before being placed
    via ``place()``. Construction-time check: ``place()`` raises if the
    visual isn't on this sheet. This is the smallest taste of what the
    L.1 validation hooks will look like.
    """
    sheet_id: SheetId
    name: str
    title: str
    description: str
    visuals: list[VisualNode] = field(default_factory=list)
    parameter_controls: list[ParameterControlNode] = field(default_factory=list)
    grid_slots: list[GridSlot] = field(default_factory=list)

    def add_visual(self, node: VisualNode) -> VisualNode:
        self.visuals.append(node)
        return node

    def add_parameter_control(
        self, node: ParameterControlNode,
    ) -> ParameterControlNode:
        self.parameter_controls.append(node)
        return node

    def place(
        self,
        visual: VisualNode,
        *,
        col_span: int,
        row_span: int,
        col_index: int,
    ) -> GridSlot:
        if visual not in self.visuals:
            raise ValueError(
                f"Visual {visual.visual_id!r} isn't registered on this "
                "sheet — call add_visual() first."
            )
        slot = GridSlot(
            visual=visual,
            col_span=col_span,
            row_span=row_span,
            col_index=col_index,
        )
        self.grid_slots.append(slot)
        return slot

    def emit(self) -> SheetDefinition:
        return SheetDefinition(
            SheetId=self.sheet_id,
            Name=self.name,
            Title=self.title,
            Description=self.description,
            ContentType="INTERACTIVE",
            Visuals=[v.emit() for v in self.visuals],
            FilterControls=[],
            ParameterControls=[c.emit() for c in self.parameter_controls],
            Layouts=[
                Layout(
                    Configuration=LayoutConfiguration(
                        GridLayout=GridLayoutConfiguration(
                            Elements=[s.emit() for s in self.grid_slots],
                        ),
                    ),
                ),
            ],
        )


# ---------------------------------------------------------------------------
# Account Network spike port.
#
# Builds the same SheetDefinition as
# apps.investigation.analysis._build_account_network_sheet. Imports the
# existing private builders for visuals + parameter controls — the spike
# is testing tree composition, not reimplementing visual mechanics.
# ---------------------------------------------------------------------------

# Layout constants mirror apps/investigation/analysis.py. Re-declared
# here rather than imported to keep the spike module self-contained;
# L.1 will fold both into a shared layout helper.
_FULL = 36
_TABLE_ROW_SPAN = 18


def build_account_network_sheet_via_tree() -> SheetDefinition:
    """Build the Account Network sheet via the spike's tree primitives.

    Returns a ``SheetDefinition`` that should be byte-identical to
    ``_build_account_network_sheet(cfg)`` — the spike's only job is to
    prove that going through the tree intermediate doesn't break the
    emission shape.

    Takes no ``cfg`` argument because the existing ``cfg`` parameter on
    ``_build_account_network_sheet`` is unused at the sheet level — it
    threads through to the visual builders via control / filter
    helpers, all of which are zero-arg today. Keeps the spike
    contract clean.

    **IDs appear ONCE.** Each ``SheetId`` / ``VisualId`` is constructed
    inline at the node's constructor — there are no imports from
    ``apps/investigation/constants``. This is the endpoint shape the
    locked object-ref decision unlocks: with cross-references carried
    by object refs, the only place the string ID is needed is the
    node that owns it. Every other reference is `inbound`, `outbound`,
    `table` (the local Python variable holding the node ref). L.1's
    full primitives will eliminate the per-app constants modules
    entirely under the same principle.

    Caveat for the spike: the existing private visual builders this
    spike delegates to (e.g. ``_account_network_sankey_inbound``)
    still read ``V_INV_ANETWORK_SANKEY_INBOUND`` from the constants
    module to set their internal ``SankeyDiagramVisual.VisualId``. The
    spike's literal here happens to equal that constant's string value
    (which is what makes byte-identity hold). When L.1 lifts the
    visual mechanics into typed ``Visual`` subtypes, the literal will
    truly appear once — set on the node and read back at emit time
    to populate the underlying model's ``VisualId``.
    """
    # Imports inside the function to avoid load-time coupling between
    # common/ and apps/. This module is a spike; L.1's primitives will
    # live in common/ unconditionally and apps/ will import from them.
    from quicksight_gen.apps.investigation.analysis import (
        _ACCOUNT_NETWORK_DESCRIPTION,
    )
    from quicksight_gen.apps.investigation.filters import (
        _anetwork_amount_control,
        _anetwork_anchor_control,
    )
    from quicksight_gen.apps.investigation.visuals import (
        _account_network_sankey_inbound,
        _account_network_sankey_outbound,
        _account_network_table,
    )

    half_width = _FULL // 2
    sankey_height = _TABLE_ROW_SPAN

    sheet = SheetNode(
        sheet_id=SheetId("inv-sheet-account-network"),
        name="Account Network",
        title="Account Network",
        description=_ACCOUNT_NETWORK_DESCRIPTION,
    )

    # Visuals: register on the sheet, then place into the layout. The
    # references returned by add_visual() are passed to place() — this
    # is what the locked object-ref decision looks like in practice.
    # The visual_id literals appear here ONCE; every other reference
    # is the local variable (`inbound`, `outbound`, `table`).
    inbound = sheet.add_visual(
        VisualNode(
            visual_id=VisualId("inv-anetwork-sankey-inbound"),
            builder=_account_network_sankey_inbound,
        )
    )
    outbound = sheet.add_visual(
        VisualNode(
            visual_id=VisualId("inv-anetwork-sankey-outbound"),
            builder=_account_network_sankey_outbound,
        )
    )
    table = sheet.add_visual(
        VisualNode(
            visual_id=VisualId("inv-anetwork-table"),
            builder=_account_network_table,
        )
    )

    sheet.place(
        inbound, col_span=half_width, row_span=sankey_height, col_index=0,
    )
    sheet.place(
        outbound,
        col_span=half_width,
        row_span=sankey_height,
        col_index=half_width,
    )
    sheet.place(
        table, col_span=_FULL, row_span=_TABLE_ROW_SPAN, col_index=0,
    )

    sheet.add_parameter_control(
        ParameterControlNode(builder=_anetwork_anchor_control)
    )
    sheet.add_parameter_control(
        ParameterControlNode(builder=_anetwork_amount_control)
    )

    return sheet.emit()
