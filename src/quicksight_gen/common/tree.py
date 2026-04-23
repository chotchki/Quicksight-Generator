"""Tree primitives for App / Dashboard / Analysis / Sheet construction.

Replaces the constant-heavy + manually-cross-referenced builders in
``apps/{payment_recon,account_recon,investigation}/{analysis,filters,
visuals}.py``. Authors construct apps as trees of typed nodes; the
tree walks itself at emit time to produce the existing ``models.py``
dataclasses, which serialize through the same ``to_aws_json()`` path
the deploy pipeline uses.

**Locked decisions** (see PLAN.md Phase L):

- Cross-references are object refs, not string IDs. ``GridSlot.visual``
  takes a ``VisualNode``; later sub-steps extend to filter group
  scope (``FilterGroup.scope = [visual_a, visual_b]``) and drill
  destinations (``Sheet`` refs in actions).
- IDs appear once — at the constructor of the node that owns them.
  Per-app ``constants.py`` modules collapse: every other reference
  is the local Python variable holding the node ref.
- ``emit()`` per node is the universal interface; trees walk
  recursively to produce ``models.py`` instances.
- Visual subtypes are typed per kind (KPI, Table, Bar, Sankey) —
  L.1.3 lifts them in. L.1.2 ships the structural foundation
  (App / Dashboard / Analysis / Sheet) plus a spike-shape
  ``VisualNode`` factory wrapper that L.1.3 will deprecate in favor
  of typed subclasses.

**Visual kind catalog** (L.1.1 finding, used in active codebase):
KPIVisual ×29, TableVisual ×22, BarChartVisual ×13,
SankeyDiagramVisual ×2. PieChartVisual is modeled but unused.

**Module organization:** single file for now; split into
``common/tree/`` package if it grows past ~600 lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, TypeVar, runtime_checkable

# PEP 695 generic syntax `def add_visual[T: VisualLike](...)` would be
# cleaner but requires Python 3.12+; project targets 3.11+ so we stick
# with the TypeVar form.
_VisualT = TypeVar("_VisualT", bound="VisualLike")

from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId, VisualId
from quicksight_gen.common.models import (
    AnalysisDefinition,
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartVisual,
    CategoricalDimensionField,
    CategoricalMeasureField,
    ColumnIdentifier,
    DashboardPublishOptions,
    DataSetIdentifierDeclaration,
    DateDimensionField,
    DimensionField,
    GridLayoutConfiguration,
    GridLayoutElement,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    Layout,
    LayoutConfiguration,
    MeasureField,
    NumericalAggregationFunction,
    NumericalDimensionField,
    NumericalMeasureField,
    ParameterControl,
    ResourcePermission,
    SankeyDiagramAggregatedFieldWells,
    SankeyDiagramChartConfiguration,
    SankeyDiagramFieldWells,
    SankeyDiagramSortConfiguration,
    SankeyDiagramVisual,
    SheetDefinition,
    SheetTextBox,
    TableAggregatedFieldWells,
    TableConfiguration,
    TableFieldWells,
    TableVisual,
    Visual,
    VisualSubtitleLabelOptions,
    VisualTitleLabelOptions,
)
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard


# ---------------------------------------------------------------------------
# Field-well leaf nodes — Dim + Measure typed wrappers around the
# DimensionField / MeasureField models. Class-method factories give
# ergonomic construction (Dim.date(...), Measure.sum(...), ...).
# ---------------------------------------------------------------------------

DimKind = Literal["categorical", "date", "numerical"]


@dataclass
class Dim:
    """One dimension field-well entry — typed wrapper that emits a
    ``DimensionField`` of the appropriate kind.

    Default kind is ``categorical`` (the most common); use the
    ``date()`` / ``numerical()`` classmethods for the other variants.
    Values may name a real dataset column or an analysis-level calc
    field — the tree treats both the same.
    """
    dataset: str
    field_id: str
    column: str
    kind: DimKind = "categorical"

    @classmethod
    def date(cls, dataset: str, field_id: str, column: str) -> Dim:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="date")

    @classmethod
    def numerical(cls, dataset: str, field_id: str, column: str) -> Dim:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="numerical")

    def emit(self) -> DimensionField:
        col = ColumnIdentifier(
            DataSetIdentifier=self.dataset, ColumnName=self.column,
        )
        if self.kind == "date":
            return DimensionField(
                DateDimensionField=DateDimensionField(
                    FieldId=self.field_id, Column=col,
                ),
            )
        if self.kind == "numerical":
            return DimensionField(
                NumericalDimensionField=NumericalDimensionField(
                    FieldId=self.field_id, Column=col,
                ),
            )
        return DimensionField(
            CategoricalDimensionField=CategoricalDimensionField(
                FieldId=self.field_id, Column=col,
            ),
        )


# Measure aggregation kinds — split into "categorical" (COUNT,
# DISTINCT_COUNT — read off any column type) and "numerical" (SUM,
# MAX, MIN, AVERAGE — require a numeric column). The split mirrors
# the underlying ``CategoricalMeasureField`` vs ``NumericalMeasureField``
# distinction in models.py.
MeasureKind = Literal[
    "sum", "max", "min", "average",          # → NumericalMeasureField
    "count", "distinct_count",               # → CategoricalMeasureField
]


_NUMERICAL_AGG = {
    "sum": "SUM", "max": "MAX", "min": "MIN", "average": "AVERAGE",
}
_CATEGORICAL_AGG = {
    "count": "COUNT", "distinct_count": "DISTINCT_COUNT",
}


@dataclass
class Measure:
    """One value field-well entry — typed wrapper that emits a
    ``MeasureField`` with the appropriate aggregation shape.

    Use the classmethod factories for ergonomic construction:
    ``Measure.sum(...)``, ``Measure.distinct_count(...)``, etc.
    Aggregation kind determines which underlying model class is
    emitted (numerical aggregations on numeric columns,
    categorical on count-style aggregations).
    """
    dataset: str
    field_id: str
    column: str
    kind: MeasureKind

    @classmethod
    def sum(cls, dataset: str, field_id: str, column: str) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="sum")

    @classmethod
    def max(cls, dataset: str, field_id: str, column: str) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="max")

    @classmethod
    def min(cls, dataset: str, field_id: str, column: str) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="min")

    @classmethod
    def average(cls, dataset: str, field_id: str, column: str) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="average")

    @classmethod
    def count(cls, dataset: str, field_id: str, column: str) -> Measure:
        return cls(dataset=dataset, field_id=field_id, column=column, kind="count")

    @classmethod
    def distinct_count(
        cls, dataset: str, field_id: str, column: str,
    ) -> Measure:
        return cls(
            dataset=dataset, field_id=field_id, column=column,
            kind="distinct_count",
        )

    def emit(self) -> MeasureField:
        col = ColumnIdentifier(
            DataSetIdentifier=self.dataset, ColumnName=self.column,
        )
        if self.kind in _CATEGORICAL_AGG:
            return MeasureField(
                CategoricalMeasureField=CategoricalMeasureField(
                    FieldId=self.field_id,
                    Column=col,
                    AggregationFunction=_CATEGORICAL_AGG[self.kind],
                ),
            )
        return MeasureField(
            NumericalMeasureField=NumericalMeasureField(
                FieldId=self.field_id,
                Column=col,
                AggregationFunction=NumericalAggregationFunction(
                    SimpleNumericalAggregation=_NUMERICAL_AGG[self.kind],
                ),
            ),
        )


# ---------------------------------------------------------------------------
# Title / subtitle helpers — port of apps/investigation/visuals.py's
# private _title / _subtitle. Lifted into common/ so visual subtypes
# don't carry their own copies.
# ---------------------------------------------------------------------------

def _title_label(text: str) -> VisualTitleLabelOptions:
    return VisualTitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


def _subtitle_label(text: str) -> VisualSubtitleLabelOptions:
    return VisualSubtitleLabelOptions(
        Visibility="VISIBLE", FormatText={"PlainText": text},
    )


# ---------------------------------------------------------------------------
# Visual node Protocol + typed subtypes per visual kind.
#
# Every visual node — typed subtype or spike-shape factory wrapper —
# exposes ``visual_id`` and ``emit() -> Visual``. ``VisualLike``
# captures that as a Protocol so ``Sheet.add_visual`` and
# ``GridSlot.visual`` accept any node satisfying the shape.
# ---------------------------------------------------------------------------

@runtime_checkable
class VisualLike(Protocol):
    """Structural type for tree-level visual nodes.

    Both ``VisualNode`` (the spike-shape factory wrapper) and the
    L.1.3 typed subtypes (``KPI`` / ``Table`` / ``BarChart`` /
    ``Sankey``) satisfy this Protocol — duck-typed so subtypes don't
    have to inherit from a base class.
    """
    visual_id: VisualId

    def emit(self) -> Visual: ...


@dataclass
class VisualNode:
    """Spike-shape factory wrapper for a Visual.

    Kept for migration during L.1 — apps port from this factory
    pattern to the typed subtypes (``KPI`` / ``Table`` / ``BarChart``
    / ``Sankey``) one app at a time. The wrapper itself is removed
    once all three apps and the new Executives app are on the
    typed subtypes.
    """
    visual_id: VisualId
    builder: Callable[[], Visual]

    def emit(self) -> Visual:
        return self.builder()


@dataclass
class KPI:
    """KPI visual — single number per ``values`` entry, no grouping.

    Field-well shape: ``Values=[Measure, ...]``. Most KPIs use one
    measure; multiple are allowed and render as side-by-side numbers.
    """
    visual_id: VisualId
    title: str
    subtitle: str | None = None
    values: list[Measure] = field(default_factory=list)

    def emit(self) -> Visual:
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


@dataclass
class Table:
    """Table visual — one row per distinct combination of ``group_by``,
    aggregated by ``values``.

    Field-well shape: ``GroupBy=[Dim, ...]`` + ``Values=[Measure, ...]``.
    Optional ``sort_by`` is a ``(field_id, direction)`` tuple — direction
    is ``"ASC"`` or ``"DESC"``.
    """
    visual_id: VisualId
    title: str
    subtitle: str | None = None
    group_by: list[Dim] = field(default_factory=list)
    values: list[Measure] = field(default_factory=list)
    sort_by: tuple[str, Literal["ASC", "DESC"]] | None = None

    def emit(self) -> Visual:
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
            ),
        )


@dataclass
class BarChart:
    """Bar chart visual — one bar per distinct ``category``, height by
    ``values``.

    Field-well shape: ``Category=[Dim, ...]`` + ``Values=[Measure, ...]``.
    Future: ``orientation: "HORIZONTAL" | "VERTICAL"`` if needed; today
    every BarChart in the codebase is vertical.
    """
    visual_id: VisualId
    title: str
    subtitle: str | None = None
    category: list[Dim] = field(default_factory=list)
    values: list[Measure] = field(default_factory=list)

    def emit(self) -> Visual:
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
            ),
        )


@dataclass
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
    """
    visual_id: VisualId
    title: str
    subtitle: str | None = None
    source: Dim | None = None
    target: Dim | None = None
    weight: Measure | None = None
    items_limit: int | None = None

    def emit(self) -> Visual:
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
            ),
        )


@dataclass
class ParameterControlNode:
    """Spike-shape factory wrapper for a ParameterControl.

    L.1.6 introduces typed control variants; this wrapper stays until
    then.
    """
    builder: Callable[[], ParameterControl]

    def emit(self) -> ParameterControl:
        return self.builder()


# ---------------------------------------------------------------------------
# Layout — GridSlot references a VisualNode by object (locked decision).
# ---------------------------------------------------------------------------

@dataclass
class GridSlot:
    """One placement in a sheet's grid layout.

    Holds an OBJECT reference to the placed visual node — the locked
    decision is cross-references via object refs, not via ``VisualId``
    strings. The element id is read off the referenced node at emit
    time. ``visual`` accepts any ``VisualLike`` — the spike-shape
    ``VisualNode`` factory wrapper, or the typed subtypes (``KPI``,
    ``Table``, ``BarChart``, ``Sankey``).
    """
    visual: VisualLike
    col_span: int
    row_span: int
    col_index: int
    row_index: int | None = None

    def emit(self) -> GridLayoutElement:
        return GridLayoutElement(
            ElementId=self.visual.visual_id,
            ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=self.col_span,
            RowSpan=self.row_span,
            ColumnIndex=self.col_index,
            RowIndex=self.row_index,
        )


# ---------------------------------------------------------------------------
# Sheet — child of Analysis.
# ---------------------------------------------------------------------------

@dataclass
class Sheet:
    """Tree node for one sheet on an Analysis / Dashboard.

    Authors register visuals + controls via ``add_visual`` /
    ``add_parameter_control``; place visuals into the grid layout via
    ``place(visual_node, ...)`` (which validates the visual is
    registered on this sheet first). ``emit()`` returns the
    ``SheetDefinition`` ready to drop into ``AnalysisDefinition.Sheets``.
    """
    sheet_id: SheetId
    name: str
    title: str
    description: str
    visuals: list[VisualLike] = field(default_factory=list)
    parameter_controls: list[ParameterControlNode] = field(default_factory=list)
    text_boxes: list[SheetTextBox] = field(default_factory=list)
    grid_slots: list[GridSlot] = field(default_factory=list)
    # FilterControls join in L.1.6.
    # TextBoxes are passed through directly for now; a TextBoxNode
    # comes when the rich-text helper is ported.

    def add_visual(self, node: _VisualT) -> _VisualT:
        """Register a visual on this sheet.

        Accepts any ``VisualLike`` — spike-shape ``VisualNode`` or
        typed subtype (``KPI`` / ``Table`` / ``BarChart`` / ``Sankey``).
        Generic over ``T`` so the caller's variable keeps the concrete
        subtype rather than widening to the Protocol.
        """
        self.visuals.append(node)
        return node

    def add_parameter_control(
        self, node: ParameterControlNode,
    ) -> ParameterControlNode:
        self.parameter_controls.append(node)
        return node

    def add_text_box(self, text_box: SheetTextBox) -> SheetTextBox:
        self.text_boxes.append(text_box)
        return text_box

    def place(
        self,
        visual: VisualLike,
        *,
        col_span: int,
        row_span: int,
        col_index: int,
        row_index: int | None = None,
    ) -> GridSlot:
        """Place a registered visual into the grid layout.

        Construction-time check: the visual must already be registered
        on this sheet via ``add_visual()``. Catches the wrong-sheet
        bug class at the call site.
        """
        if visual not in self.visuals:
            raise ValueError(
                f"Visual {visual.visual_id!r} isn't registered on this "
                f"sheet — call add_visual() first."
            )
        slot = GridSlot(
            visual=visual,
            col_span=col_span,
            row_span=row_span,
            col_index=col_index,
            row_index=row_index,
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
            Visuals=[v.emit() for v in self.visuals] if self.visuals else None,
            FilterControls=[],  # L.1.6
            ParameterControls=(
                [c.emit() for c in self.parameter_controls]
                if self.parameter_controls else None
            ),
            TextBoxes=self.text_boxes if self.text_boxes else None,
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
# Analysis — owns the sheet tree; emits AnalysisDefinition. The wrapping
# (AnalysisId / AwsAccountId / Permissions / ThemeArn) is supplied by
# the App.
# ---------------------------------------------------------------------------

@dataclass
class Analysis:
    """Tree node for the Analysis-level structure.

    ``analysis_id_suffix`` is the part the App's ``cfg.prefixed()``
    will prepend to (e.g. ``"investigation-analysis"`` becomes
    ``"qs-gen-investigation-analysis"``). Keeping the suffix on the
    tree node keeps the per-app naming under the tree's control while
    leaving the global resource-prefix in the Config.

    ``emit_definition()`` returns the ``models.AnalysisDefinition`` —
    the App combines this with metadata (``AwsAccountId``,
    ``ThemeArn``, ``Permissions``, dataset declarations) to produce
    the full ``models.Analysis`` ready for deploy.
    """
    analysis_id_suffix: str
    name: str
    sheets: list[Sheet] = field(default_factory=list)
    # ParameterDeclarations join in L.1.4
    # FilterGroups join in L.1.5
    # CalculatedFields join in a later sub-step
    # DataSetIdentifierDeclarations come from the App at emit time

    def add_sheet(self, sheet: Sheet) -> Sheet:
        if any(s.sheet_id == sheet.sheet_id for s in self.sheets):
            raise ValueError(
                f"Sheet {sheet.sheet_id!r} is already on this Analysis"
            )
        self.sheets.append(sheet)
        return sheet

    def emit_definition(
        self,
        *,
        dataset_declarations: list[DataSetIdentifierDeclaration],
    ) -> AnalysisDefinition:
        return AnalysisDefinition(
            DataSetIdentifierDeclarations=dataset_declarations,
            Sheets=[s.emit() for s in self.sheets],
            FilterGroups=None,  # L.1.5
            CalculatedFields=None,  # later
            ParameterDeclarations=None,  # L.1.4
        )


# ---------------------------------------------------------------------------
# Dashboard — references an Analysis (object ref) so they share the
# same definition.
# ---------------------------------------------------------------------------

@dataclass
class Dashboard:
    """Tree node for a Dashboard.

    Carries an object reference to the ``Analysis`` whose definition
    this Dashboard publishes. ``dashboard_id_suffix`` follows the same
    pattern as ``Analysis.analysis_id_suffix`` — App's ``cfg.prefixed()``
    prepends the project resource prefix.

    ``analysis`` is the SAME tree node the App owns; the Dashboard
    re-emits the same definition the Analysis produces, which matches
    the existing ``build_dashboard(cfg)`` pattern in the per-app
    builders.
    """
    dashboard_id_suffix: str
    name: str
    analysis: Analysis


# ---------------------------------------------------------------------------
# App — top-level tree node. Owns Analysis + Dashboard + Config-derived
# context (theme arn, dataset arns, permissions). Emits the full
# models.Analysis and models.Dashboard ready for deploy.
# ---------------------------------------------------------------------------

# Action constants — same as the per-app `_ANALYSIS_ACTIONS` /
# `_DASHBOARD_ACTIONS` lists today; lifted into common/ here.
_ANALYSIS_ACTIONS = [
    "quicksight:DescribeAnalysis",
    "quicksight:DescribeAnalysisPermissions",
    "quicksight:UpdateAnalysis",
    "quicksight:UpdateAnalysisPermissions",
    "quicksight:DeleteAnalysis",
    "quicksight:QueryAnalysis",
    "quicksight:RestoreAnalysis",
]

_DASHBOARD_ACTIONS = [
    "quicksight:DescribeDashboard",
    "quicksight:ListDashboardVersions",
    "quicksight:UpdateDashboardPermissions",
    "quicksight:QueryDashboard",
    "quicksight:UpdateDashboard",
    "quicksight:DeleteDashboard",
    "quicksight:DescribeDashboardPermissions",
    "quicksight:UpdateDashboardPublishedVersion",
]


@dataclass
class App:
    """Top-level tree node — coordinates an Analysis + Dashboard plus
    the deploy-time context (theme, dataset arns, permissions) drawn
    from the Config.

    Authors construct an App, attach the Analysis (which holds the
    sheet tree), optionally attach the Dashboard (most apps do — they
    publish what they author), and call ``emit_analysis()`` /
    ``emit_dashboard()`` to get the ``models.py`` instances ready for
    deploy.

    ``dataset_arns`` is the per-logical-id → ARN mapping the Analysis
    references via ``DataSetIdentifierDeclarations``. Today this is
    supplied at ``emit_*`` time so apps can plug in lazy dataset
    construction; a later sub-step may move it onto the App as a
    typed dataset declaration tree node.
    """
    name: str
    cfg: Config
    analysis: Analysis | None = None
    dashboard: Dashboard | None = None

    def set_analysis(self, analysis: Analysis) -> Analysis:
        self.analysis = analysis
        return analysis

    def set_dashboard(self, dashboard: Dashboard) -> Dashboard:
        if dashboard.analysis is not self.analysis:
            raise ValueError(
                "Dashboard.analysis must be the same Analysis instance "
                "the App owns. Construct the Dashboard with the App's "
                "Analysis: Dashboard(analysis=app.analysis, ...)."
            )
        self.dashboard = dashboard
        return dashboard

    def _permissions(self, actions: list[str]) -> list[ResourcePermission] | None:
        if not self.cfg.principal_arns:
            return None
        return [
            ResourcePermission(Principal=arn, Actions=actions)
            for arn in self.cfg.principal_arns
        ]

    def _theme_arn(self) -> str:
        return self.cfg.theme_arn(self.cfg.prefixed("theme"))

    def emit_analysis(
        self,
        *,
        dataset_declarations: list[DataSetIdentifierDeclaration],
    ) -> ModelAnalysis:
        if self.analysis is None:
            raise ValueError(
                "App has no Analysis — call set_analysis() first."
            )
        return ModelAnalysis(
            AwsAccountId=self.cfg.aws_account_id,
            AnalysisId=self.cfg.prefixed(self.analysis.analysis_id_suffix),
            Name=self.analysis.name,
            ThemeArn=self._theme_arn(),
            Definition=self.analysis.emit_definition(
                dataset_declarations=dataset_declarations,
            ),
            Permissions=self._permissions(_ANALYSIS_ACTIONS),
            Tags=self.cfg.tags(),
        )

    def emit_dashboard(
        self,
        *,
        dataset_declarations: list[DataSetIdentifierDeclaration],
    ) -> ModelDashboard:
        if self.dashboard is None:
            raise ValueError(
                "App has no Dashboard — call set_dashboard() first."
            )
        return ModelDashboard(
            AwsAccountId=self.cfg.aws_account_id,
            DashboardId=self.cfg.prefixed(self.dashboard.dashboard_id_suffix),
            Name=self.dashboard.name,
            ThemeArn=self._theme_arn(),
            Definition=self.dashboard.analysis.emit_definition(
                dataset_declarations=dataset_declarations,
            ),
            Permissions=self._permissions(_DASHBOARD_ACTIONS),
            Tags=self.cfg.tags(),
            VersionDescription="Generated by quicksight-gen",
            DashboardPublishOptions=DashboardPublishOptions(
                AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
                ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
                SheetControlsOption={"VisibilityState": "EXPANDED"},
            ),
        )
