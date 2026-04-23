"""Typed ``Visual`` subtypes — one per visual kind in active use.

L.1.1 catalog: KPI ×29, Table ×22, BarChart ×13, Sankey ×2 across
the three apps. Each subtype owns its field-well shape and emits the
corresponding ``models.py`` ``Visual`` instance. Spike-shape
``VisualNode`` factory wrapper kept for migration-window
compatibility — apps port from factory pattern to typed subtypes one
at a time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Literal, Protocol, runtime_checkable

from quicksight_gen.common.ids import VisualId
from quicksight_gen.common.models import (
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartVisual,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    SankeyDiagramAggregatedFieldWells,
    SankeyDiagramChartConfiguration,
    SankeyDiagramFieldWells,
    SankeyDiagramSortConfiguration,
    SankeyDiagramVisual,
    TableAggregatedFieldWells,
    TableConfiguration,
    TableFieldWells,
    TableVisual,
    Visual,
)

from quicksight_gen.common.tree._helpers import _subtitle_label, _title_label
from quicksight_gen.common.tree.actions import Drill
from quicksight_gen.common.tree.calc_fields import CalcField
from quicksight_gen.common.tree.datasets import Dataset
from quicksight_gen.common.tree.fields import Dim, Measure


@runtime_checkable
class VisualLike(Protocol):
    """Structural type for tree-level visual nodes.

    Both ``VisualNode`` (the spike-shape factory wrapper) and the
    typed subtypes (``KPI`` / ``Table`` / ``BarChart`` / ``Sankey``)
    satisfy this Protocol — duck-typed so subtypes don't have to
    inherit from a base class.

    Typed subtypes also expose ``datasets() -> set[Dataset]`` for the
    L.1.7 dependency-graph walk; the spike-shape ``VisualNode`` does
    not (its factory callable hides its dataset references). Apps
    using factory wrappers don't contribute to dependency tracking;
    typed subtypes do.
    """
    visual_id: VisualId

    def emit(self) -> Visual: ...


@dataclass(eq=False)
class VisualNode:
    """Spike-shape factory wrapper for a Visual.

    Kept for migration during L.1 — apps port from this factory
    pattern to the typed subtypes one app at a time. The wrapper
    itself is removed once all apps are on the typed subtypes.
    """
    visual_id: VisualId
    builder: Callable[[], Visual]

    def emit(self) -> Visual:
        return self.builder()


@dataclass(eq=False)
class KPI:
    """KPI visual — single number per ``values`` entry, no grouping.

    Field-well shape: ``Values=[Measure, ...]``. Most KPIs use one
    measure; multiple are allowed and render as side-by-side numbers.

    ``visual_id`` is optional (L.1.8.5 auto-ID). When omitted, the
    App's tree walker assigns ``v-kpi-s{sheet_idx}-{visual_idx}`` at
    emit time. Pass an explicit ``VisualId(...)`` to override.
    """
    title: str
    subtitle: str | None = None
    values: list[Measure] = field(default_factory=list)
    visual_id: VisualId | None = None

    _AUTO_KIND: ClassVar[str] = "kpi"

    def datasets(self) -> set[Dataset]:
        return {m.dataset for m in self.values}

    def calc_fields(self) -> set[CalcField]:
        """CalcFields this visual references via its field-well leaves."""
        return {cf for m in self.values if (cf := m.calc_field()) is not None}

    def emit(self) -> Visual:
        assert self.visual_id is not None, (
            "visual_id wasn't resolved — App._resolve_auto_ids() must run "
            "before Visual.emit(). This shouldn't happen via App.emit_*()."
        )
        # KPI doesn't carry Actions per the QuickSight model — KPIs aren't
        # data-point-clickable. If we ever need drill on a KPI, switch to
        # a different visual type.
        return Visual(
            KPIVisual=KPIVisual(
                VisualId=self.visual_id,
                Title=_title_label(self.title),
                Subtitle=_subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=KPIConfiguration(
                    FieldWells=KPIFieldWells(
                        Values=[m.emit() for m in self.values] if self.values else None,
                    ),
                ),
            ),
        )


@dataclass(eq=False)
class Table:
    """Table visual — one row per distinct combination of ``group_by``,
    aggregated by ``values``.

    Field-well shape: ``GroupBy=[Dim, ...]`` + ``Values=[Measure, ...]``.
    Optional ``sort_by`` is a ``(field_id, direction)`` tuple — direction
    is ``"ASC"`` or ``"DESC"``.

    ``visual_id`` is optional (L.1.8.5 auto-ID).
    """
    title: str
    subtitle: str | None = None
    group_by: list[Dim] = field(default_factory=list)
    values: list[Measure] = field(default_factory=list)
    sort_by: tuple[str, Literal["ASC", "DESC"]] | None = None
    actions: list[Drill] = field(default_factory=list)
    visual_id: VisualId | None = None

    _AUTO_KIND: ClassVar[str] = "table"

    def datasets(self) -> set[Dataset]:
        return ({d.dataset for d in self.group_by}
                | {m.dataset for m in self.values})

    def calc_fields(self) -> set[CalcField]:
        deps: set[CalcField] = set()
        for d in self.group_by:
            if (cf := d.calc_field()) is not None:
                deps.add(cf)
        for m in self.values:
            if (cf := m.calc_field()) is not None:
                deps.add(cf)
        return deps

    def emit(self) -> Visual:
        assert self.visual_id is not None, (
            "visual_id wasn't resolved — see KPI.emit assertion."
        )
        sort_config: Any = None
        if self.sort_by is not None:
            field_id, direction = self.sort_by
            sort_config = {
                "RowSort": [
                    {"FieldSort": {"FieldId": field_id, "Direction": direction}},
                ],
            }
        return Visual(
            TableVisual=TableVisual(
                VisualId=self.visual_id,
                Title=_title_label(self.title),
                Subtitle=_subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=TableConfiguration(
                    FieldWells=TableFieldWells(
                        TableAggregatedFieldWells=TableAggregatedFieldWells(
                            GroupBy=[d.emit() for d in self.group_by] if self.group_by else None,
                            Values=[m.emit() for m in self.values] if self.values else None,
                        ),
                    ),
                    SortConfiguration=sort_config,
                ),
                Actions=[a.emit() for a in self.actions] if self.actions else None,
            ),
        )


@dataclass(eq=False)
class BarChart:
    """Bar chart visual — one bar per distinct ``category``, height by
    ``values``.

    Field-well shape: ``Category=[Dim, ...]`` + ``Values=[Measure, ...]``.
    Future: ``orientation: "HORIZONTAL" | "VERTICAL"`` if needed; today
    every BarChart in the codebase is vertical.

    ``visual_id`` is optional (L.1.8.5 auto-ID).
    """
    title: str
    subtitle: str | None = None
    category: list[Dim] = field(default_factory=list)
    values: list[Measure] = field(default_factory=list)
    actions: list[Drill] = field(default_factory=list)
    visual_id: VisualId | None = None

    _AUTO_KIND: ClassVar[str] = "bar"

    def datasets(self) -> set[Dataset]:
        return ({d.dataset for d in self.category}
                | {m.dataset for m in self.values})

    def calc_fields(self) -> set[CalcField]:
        deps: set[CalcField] = set()
        for d in self.category:
            if (cf := d.calc_field()) is not None:
                deps.add(cf)
        for m in self.values:
            if (cf := m.calc_field()) is not None:
                deps.add(cf)
        return deps

    def emit(self) -> Visual:
        assert self.visual_id is not None, (
            "visual_id wasn't resolved — see KPI.emit assertion."
        )
        return Visual(
            BarChartVisual=BarChartVisual(
                VisualId=self.visual_id,
                Title=_title_label(self.title),
                Subtitle=_subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=BarChartConfiguration(
                    FieldWells=BarChartFieldWells(
                        BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                            Category=[d.emit() for d in self.category] if self.category else None,
                            Values=[m.emit() for m in self.values] if self.values else None,
                        ),
                    ),
                ),
                Actions=[a.emit() for a in self.actions] if self.actions else None,
            ),
        )


@dataclass(eq=False)
class Sankey:
    """Sankey diagram visual — flows from ``source`` nodes to
    ``target`` nodes, ribbon thickness by ``weight``.

    Field-well shape: each of ``source`` / ``target`` / ``weight`` is
    a single ``Dim`` / ``Measure`` (the underlying model expects
    lists, but every usage today has exactly one entry; emit wraps).

    ``items_limit`` caps the number of source / destination nodes
    rendered (matches the ``ItemsLimit`` shape on the underlying
    sort configuration). ``OtherCategories`` defaults to ``"INCLUDE"``
    so capped flows roll into a "(others)" bucket rather than being
    dropped silently.

    ``visual_id`` is optional (L.1.8.5 auto-ID).
    """
    title: str
    subtitle: str | None = None
    source: Dim | None = None
    target: Dim | None = None
    weight: Measure | None = None
    items_limit: int | None = None
    actions: list[Drill] = field(default_factory=list)
    visual_id: VisualId | None = None

    _AUTO_KIND: ClassVar[str] = "sankey"

    def datasets(self) -> set[Dataset]:
        deps: set[Dataset] = set()
        if self.source is not None:
            deps.add(self.source.dataset)
        if self.target is not None:
            deps.add(self.target.dataset)
        if self.weight is not None:
            deps.add(self.weight.dataset)
        return deps

    def calc_fields(self) -> set[CalcField]:
        deps: set[CalcField] = set()
        for leaf in (self.source, self.target, self.weight):
            if leaf is None:
                continue
            if (cf := leaf.calc_field()) is not None:
                deps.add(cf)
        return deps

    def emit(self) -> Visual:
        assert self.visual_id is not None, (
            "visual_id wasn't resolved — see KPI.emit assertion."
        )
        sort_config: Any = None
        if self.weight is not None or self.items_limit is not None:
            sort_config_kwargs: dict[str, Any] = {}
            if self.weight is not None:
                sort_config_kwargs["WeightSort"] = [
                    {
                        "FieldSort": {
                            "FieldId": self.weight.field_id,
                            "Direction": "DESC",
                        },
                    },
                ]
            if self.items_limit is not None:
                limit_block = {
                    "ItemsLimit": self.items_limit,
                    "OtherCategories": "INCLUDE",
                }
                sort_config_kwargs["SourceItemsLimit"] = limit_block
                sort_config_kwargs["DestinationItemsLimit"] = limit_block
            sort_config = SankeyDiagramSortConfiguration(**sort_config_kwargs)
        return Visual(
            SankeyDiagramVisual=SankeyDiagramVisual(
                VisualId=self.visual_id,
                Title=_title_label(self.title),
                Subtitle=_subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=SankeyDiagramChartConfiguration(
                    FieldWells=SankeyDiagramFieldWells(
                        SankeyDiagramAggregatedFieldWells=SankeyDiagramAggregatedFieldWells(
                            Source=[self.source.emit()] if self.source else None,
                            Destination=[self.target.emit()] if self.target else None,
                            Weight=[self.weight.emit()] if self.weight else None,
                        ),
                    ),
                    SortConfiguration=sort_config,
                ),
                Actions=[a.emit() for a in self.actions] if self.actions else None,
            ),
        )
