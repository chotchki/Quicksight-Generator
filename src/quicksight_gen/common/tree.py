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
from typing import Callable

from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId, VisualId
from quicksight_gen.common.models import (
    AnalysisDefinition,
    DashboardPublishOptions,
    DataSetIdentifierDeclaration,
    GridLayoutConfiguration,
    GridLayoutElement,
    Layout,
    LayoutConfiguration,
    ParameterControl,
    ResourcePermission,
    SheetDefinition,
    SheetTextBox,
    Visual,
)
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard


# ---------------------------------------------------------------------------
# Visual + control nodes — L.1.2 ships spike-shape factory wrappers.
# L.1.3 will introduce typed Visual subtypes (KPI, Table, Bar, Sankey)
# alongside; the wrappers stay until apps port to typed subtypes.
# ---------------------------------------------------------------------------

@dataclass
class VisualNode:
    """Spike-shape factory wrapper for a Visual.

    L.1.3 introduces typed subtypes per visual kind; this wrapper stays
    until apps migrate. Keep `visual_id` as the node's identity and the
    factory callable as the source of the underlying Visual.
    """
    visual_id: VisualId
    builder: Callable[[], Visual]

    def emit(self) -> Visual:
        return self.builder()


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

    Holds an OBJECT reference to the placed ``VisualNode`` — the locked
    decision is cross-references via object refs, not via ``VisualId``
    strings. The element id is read off the referenced node at emit
    time.
    """
    visual: VisualNode
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
    visuals: list[VisualNode] = field(default_factory=list)
    parameter_controls: list[ParameterControlNode] = field(default_factory=list)
    text_boxes: list[SheetTextBox] = field(default_factory=list)
    grid_slots: list[GridSlot] = field(default_factory=list)
    # FilterControls join in L.1.6.
    # TextBoxes are passed through directly for now; a TextBoxNode
    # comes when the rich-text helper is ported.

    def add_visual(self, node: VisualNode) -> VisualNode:
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
        visual: VisualNode,
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
