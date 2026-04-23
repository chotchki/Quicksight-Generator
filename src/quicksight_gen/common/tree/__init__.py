"""Tree primitives for App / Dashboard / Analysis / Sheet construction.

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/{payment_recon,account_recon,investigation}/{analysis,filters,
visuals}.py``. Authors construct apps as trees of typed nodes; the
tree walks itself at emit time to produce the existing ``models.py``
dataclasses, which serialize through the same ``to_aws_json()`` path
the deploy pipeline uses.

**Locked decisions** (see PLAN.md Phase L):

- Cross-references are object refs, not string IDs. ``GridSlot.visual``
  takes a visual node; ``FilterGroup.scope_visuals`` takes
  ``(sheet, [visual, ...])``; drill destinations take ``Sheet`` refs.
- IDs appear once — at the constructor of the node that owns them.
  Per-app ``constants.py`` modules collapse: every other reference
  is the local Python variable holding the node ref.
- ``emit()`` per node is the universal interface; trees walk
  recursively to produce ``models.py`` instances.
- Visual subtypes are typed per kind (KPI, Table, Bar, Sankey).
  Same names as ``models.py`` where they exist; tree types alias
  models on import inside their own submodules to keep user-facing
  imports clean (``from quicksight_gen.common.tree import KPI,
  Sankey, FilterGroup`` etc.).

**Visual kind catalog** (L.1.1 finding, used in active codebase):
KPIVisual ×29, TableVisual ×22, BarChartVisual ×13,
SankeyDiagramVisual ×2. PieChartVisual is modeled but unused.

**Module organization:**

- ``_helpers`` — title/subtitle label builders + permissions actions
- ``fields`` — ``Dim`` / ``Measure`` field-well leaf nodes
- ``parameters`` — ``ParameterDeclLike`` Protocol + ``StringParam``
  / ``IntegerParam`` / ``DateTimeParam``
- ``visuals`` — ``VisualLike`` Protocol + ``VisualNode`` (factory
  wrapper) + ``KPI`` / ``Table`` / ``BarChart`` / ``Sankey``
- ``filters`` — ``FilterGroup`` (object-ref scope + scope-on-same-sheet
  validation); typed Filter wrappers (CategoryFilter / NumericRangeFilter
  / TimeRangeFilter) land in L.1.6.
- ``structure`` — ``GridSlot`` / ``Sheet`` / ``Analysis`` / ``Dashboard``
  / ``App`` / ``ParameterControlNode``
"""

from __future__ import annotations

from quicksight_gen.common.tree.fields import (
    Dim,
    DimKind,
    Measure,
    MeasureKind,
)
from quicksight_gen.common.tree.filters import FilterGroup
from quicksight_gen.common.tree.parameters import (
    DateTimeParam,
    IntegerParam,
    ParameterDeclLike,
    StringParam,
)
from quicksight_gen.common.tree.structure import (
    Analysis,
    App,
    Dashboard,
    GridSlot,
    ParameterControlNode,
    Sheet,
)
from quicksight_gen.common.tree.visuals import (
    KPI,
    BarChart,
    Sankey,
    Table,
    VisualLike,
    VisualNode,
)

__all__ = [
    # Field-well leaves
    "Dim", "DimKind", "Measure", "MeasureKind",
    # Parameters
    "ParameterDeclLike", "StringParam", "IntegerParam", "DateTimeParam",
    # Visuals
    "VisualLike", "VisualNode", "KPI", "Table", "BarChart", "Sankey",
    # Filters
    "FilterGroup",
    # Structure
    "GridSlot", "Sheet", "Analysis", "Dashboard", "App",
    "ParameterControlNode",
]
