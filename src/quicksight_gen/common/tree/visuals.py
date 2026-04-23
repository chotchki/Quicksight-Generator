"""Typed ``Visual`` subtypes — one per visual kind in active use.

L.1.1 catalog: KPI ×29, Table ×22, BarChart ×13, Sankey ×2 across
the three apps. Each subtype owns its field-well shape and emits the
corresponding ``models.py`` ``Visual`` instance.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal, Protocol, runtime_checkable

from quicksight_gen.common.ids import VisualId
from quicksight_gen.common.models import (
    AxisLabelOptions,
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartSortConfiguration,
    BarChartVisual,
    ChartAxisLabelOptions,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    SankeyDiagramAggregatedFieldWells,
    SankeyDiagramChartConfiguration,
    SankeyDiagramFieldWells,
    SankeyDiagramSortConfiguration,
    SankeyDiagramVisual,
    TableAggregatedFieldWells,
    TableUnaggregatedFieldWells,
    TableConfiguration,
    TableFieldWells,
    TableVisual,
    Visual,
)

from quicksight_gen.common.tree._helpers import (
    AUTO,
    AutoResolved,
    GridLayoutElementType,
    _AutoSentinel,
    subtitle_label,
    title_label,
)
from quicksight_gen.common.tree.actions import Action
from quicksight_gen.common.tree.calc_fields import CalcField
from quicksight_gen.common.tree.datasets import Dataset
from quicksight_gen.common.tree.fields import Dim, FieldRef, Measure, resolve_field_id


@runtime_checkable
class VisualLike(Protocol):
    """Structural type for tree-level visual nodes.

    Typed subtypes (``KPI`` / ``Table`` / ``BarChart`` / ``Sankey``)
    satisfy this Protocol — duck-typed so subtypes don't have to
    inherit from a base class. Subtypes contribute to the L.1.7
    dependency-graph walk via ``datasets()`` / ``calc_fields()``.

    All visual nodes also satisfy ``LayoutNode`` (in ``structure.py``)
    via ``element_id`` + ``element_type`` so they can be placed in a
    sheet's grid layout (``sheet.layout.row(...).add_<kind>(...)``).

    ``visual_id`` is ``VisualId | AutoResolved`` — typed subtypes default
    to ``AUTO`` and ``App._resolve_auto_ids`` replaces it with the
    derived id before emit. The walker / emit assert via ``isinstance``
    narrowing.
    """
    visual_id: VisualId | AutoResolved

    def emit(self) -> Visual: ...

    def datasets(self) -> set[Dataset]: ...

    def calc_fields(self) -> set[CalcField]: ...


def _visual_element_id(node: VisualLike) -> str:
    """LayoutNode.element_id implementation shared by every visual subtype.
    Resolves to ``visual_id`` (the visual's element id is the same id
    QuickSight uses for the visual itself); asserts auto-IDs are
    resolved before access."""
    assert not isinstance(node.visual_id, _AutoSentinel), (
        "visual_id wasn't resolved — App._resolve_auto_ids() must run "
        "before LayoutNode.element_id access."
    )
    return node.visual_id


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
    values: list[Measure] = field(default_factory=list[Measure])
    visual_id: VisualId | AutoResolved = AUTO

    _AUTO_KIND: ClassVar[str] = "kpi"

    @property
    def element_id(self) -> str:
        return _visual_element_id(self)

    @property
    def element_type(self) -> GridLayoutElementType:
        return "VISUAL"

    def datasets(self) -> set[Dataset]:
        return {m.dataset for m in self.values}

    def calc_fields(self) -> set[CalcField]:
        """CalcFields this visual references via its field-well leaves."""
        return {cf for m in self.values if (cf := m.calc_field()) is not None}

    def emit(self) -> Visual:
        assert not isinstance(self.visual_id, _AutoSentinel), (
            "visual_id wasn't resolved — App._resolve_auto_ids() must run "
            "before Visual.emit(). This shouldn't happen via App.emit_*()."
        )
        # KPI doesn't carry Actions per the QuickSight model — KPIs aren't
        # data-point-clickable. If we ever need drill on a KPI, switch to
        # a different visual type.
        return Visual(
            KPIVisual=KPIVisual(
                VisualId=self.visual_id,
                Title=title_label(self.title),
                Subtitle=subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=KPIConfiguration(
                    FieldWells=KPIFieldWells(
                        Values=[m.emit() for m in self.values] if self.values else None,
                    ),
                ),
            ),
        )


@dataclass(eq=False)
class Table:
    """Table visual — two field-well shapes:

    - **Aggregated** (default): ``group_by=[Dim, ...]`` +
      ``values=[Measure, ...]``. One row per distinct ``group_by``
      combination, aggregated by ``values``. Emits
      ``TableAggregatedFieldWells``.
    - **Unaggregated**: pass ``columns=[Dim, ...]`` (and leave
      ``group_by`` / ``values`` empty). Each cell shows the raw column
      value — no aggregation, one row per source row. Emits
      ``TableUnaggregatedFieldWells``. Use this for detail/drill-source
      tables (AR Balances, AR Daily Statement transaction list).

    Optional ``sort_by`` is a ``(field_ref, direction)`` tuple —
    direction is ``"ASC"`` or ``"DESC"``.

    Optional ``conditional_formatting`` passes through to the model's
    raw dict (see ``common/clickability.py`` for the standard
    accent-text and tint-background helpers).

    ``visual_id`` is optional (L.1.8.5 auto-ID).
    """
    title: str
    subtitle: str | None = None
    group_by: list[Dim] = field(default_factory=list[Dim])
    values: list[Measure] = field(default_factory=list[Measure])
    columns: list[Dim] = field(default_factory=list[Dim])
    sort_by: tuple[FieldRef, Literal["ASC", "DESC"]] | None = None
    actions: list[Action] = field(default_factory=list[Action])
    conditional_formatting: dict[str, Any] | None = None
    visual_id: VisualId | AutoResolved = AUTO

    _AUTO_KIND: ClassVar[str] = "table"

    def __post_init__(self) -> None:
        # Unaggregated and aggregated modes are mutually exclusive: if
        # `columns` is set, `group_by` and `values` must be empty (and
        # vice versa). This is the same pattern as the model's
        # `TableFieldWells` — exactly one of `TableAggregatedFieldWells`
        # / `TableUnaggregatedFieldWells` is set.
        if self.columns and (self.group_by or self.values):
            raise ValueError(
                "Table: `columns` (unaggregated mode) cannot be combined "
                "with `group_by` / `values` (aggregated mode). Pick one."
            )

    @property
    def element_id(self) -> str:
        return _visual_element_id(self)

    @property
    def element_type(self) -> GridLayoutElementType:
        return "VISUAL"

    def datasets(self) -> set[Dataset]:
        return (
            {d.dataset for d in self.group_by}
            | {m.dataset for m in self.values}
            | {d.dataset for d in self.columns}
        )

    def calc_fields(self) -> set[CalcField]:
        deps: set[CalcField] = set()
        for d in self.group_by:
            if (cf := d.calc_field()) is not None:
                deps.add(cf)
        for m in self.values:
            if (cf := m.calc_field()) is not None:
                deps.add(cf)
        for d in self.columns:
            if (cf := d.calc_field()) is not None:
                deps.add(cf)
        return deps

    def emit(self) -> Visual:
        assert not isinstance(self.visual_id, _AutoSentinel), (
            "visual_id wasn't resolved — see KPI.emit assertion."
        )
        sort_config: Any = None
        if self.sort_by is not None:
            ref, direction = self.sort_by
            sort_config = {
                "RowSort": [
                    {"FieldSort": {
                        "FieldId": resolve_field_id(ref),
                        "Direction": direction,
                    }},
                ],
            }
        if self.columns:
            field_wells = TableFieldWells(
                TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                    Values=[d.emit_unaggregated_field() for d in self.columns],
                ),
            )
        else:
            field_wells = TableFieldWells(
                TableAggregatedFieldWells=TableAggregatedFieldWells(
                    GroupBy=[d.emit() for d in self.group_by] if self.group_by else None,
                    Values=[m.emit() for m in self.values] if self.values else None,
                ),
            )
        return Visual(
            TableVisual=TableVisual(
                VisualId=self.visual_id,
                Title=title_label(self.title),
                Subtitle=subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=TableConfiguration(
                    FieldWells=field_wells,
                    SortConfiguration=sort_config,
                ),
                Actions=[a.emit() for a in self.actions] if self.actions else None,
                ConditionalFormatting=self.conditional_formatting,
            ),
        )


@dataclass(eq=False)
class BarChart:
    """Bar chart visual — one bar per distinct ``category``, height by
    ``values``.

    Field-well shape: ``Category=[Dim, ...]`` + ``Values=[Measure, ...]``.

    ``orientation`` (``"VERTICAL"`` or ``"HORIZONTAL"``) and
    ``bars_arrangement`` (``"CLUSTERED"`` / ``"STACKED"`` /
    ``"STACKED_PERCENT"``) pass through to the underlying
    ``BarChartConfiguration``. ``sort_by`` is a ``(field_id, direction)``
    tuple — direction ``"ASC"`` or ``"DESC"`` — and emits a
    ``CategorySort`` entry. All three default to ``None`` so the
    QuickSight defaults apply when not specified.

    ``visual_id`` is optional (L.1.8.5 auto-ID).
    """
    title: str
    subtitle: str | None = None
    category: list[Dim] = field(default_factory=list[Dim])
    values: list[Measure] = field(default_factory=list[Measure])
    orientation: Literal["HORIZONTAL", "VERTICAL"] | None = None
    bars_arrangement: Literal[
        "CLUSTERED", "STACKED", "STACKED_PERCENT",
    ] | None = None
    category_label: str | None = None
    value_label: str | None = None
    sort_by: tuple[FieldRef, Literal["ASC", "DESC"]] | None = None
    actions: list[Action] = field(default_factory=list[Action])
    visual_id: VisualId | AutoResolved = AUTO

    _AUTO_KIND: ClassVar[str] = "bar"

    @property
    def element_id(self) -> str:
        return _visual_element_id(self)

    @property
    def element_type(self) -> GridLayoutElementType:
        return "VISUAL"

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
        assert not isinstance(self.visual_id, _AutoSentinel), (
            "visual_id wasn't resolved — see KPI.emit assertion."
        )
        sort_config: BarChartSortConfiguration | None = None
        if self.sort_by is not None:
            ref, direction = self.sort_by
            sort_config = BarChartSortConfiguration(
                CategorySort=[
                    {"FieldSort": {
                        "FieldId": resolve_field_id(ref),
                        "Direction": direction,
                    }},
                ],
            )
        return Visual(
            BarChartVisual=BarChartVisual(
                VisualId=self.visual_id,
                Title=title_label(self.title),
                Subtitle=subtitle_label(self.subtitle) if self.subtitle else None,
                ChartConfiguration=BarChartConfiguration(
                    FieldWells=BarChartFieldWells(
                        BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                            Category=[d.emit() for d in self.category] if self.category else None,
                            Values=[m.emit() for m in self.values] if self.values else None,
                        ),
                    ),
                    Orientation=self.orientation,
                    BarsArrangement=self.bars_arrangement,
                    CategoryLabelOptions=(
                        ChartAxisLabelOptions(AxisLabelOptions=[
                            AxisLabelOptions(CustomLabel=self.category_label),
                        ])
                        if self.category_label is not None else None
                    ),
                    ValueLabelOptions=(
                        ChartAxisLabelOptions(AxisLabelOptions=[
                            AxisLabelOptions(CustomLabel=self.value_label),
                        ])
                        if self.value_label is not None else None
                    ),
                    SortConfiguration=sort_config,
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
    actions: list[Action] = field(default_factory=list[Action])
    visual_id: VisualId | AutoResolved = AUTO

    _AUTO_KIND: ClassVar[str] = "sankey"

    @property
    def element_id(self) -> str:
        return _visual_element_id(self)

    @property
    def element_type(self) -> GridLayoutElementType:
        return "VISUAL"

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
        assert not isinstance(self.visual_id, _AutoSentinel), (
            "visual_id wasn't resolved — see KPI.emit assertion."
        )
        sort_config: Any = None
        if self.weight is not None or self.items_limit is not None:
            sort_config_kwargs: dict[str, Any] = {}
            if self.weight is not None:
                sort_config_kwargs["WeightSort"] = [
                    {
                        "FieldSort": {
                            "FieldId": resolve_field_id(self.weight),
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
                Title=title_label(self.title),
                Subtitle=subtitle_label(self.subtitle) if self.subtitle else None,
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
