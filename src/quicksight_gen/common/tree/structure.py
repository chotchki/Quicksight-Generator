"""Structural tree types — ``GridSlot`` / ``Sheet`` / ``Analysis`` /
``Dashboard`` / ``App``.

The skeleton the rest of the tree hangs off. Authors construct an
``App``, attach an ``Analysis`` (which holds the sheet tree),
optionally attach a ``Dashboard``, and call ``app.emit_analysis()``
/ ``app.emit_dashboard()`` to get the ``models.py`` instances ready
for deploy.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId
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

from quicksight_gen.common.tree._helpers import (
    ANALYSIS_ACTIONS,
    DASHBOARD_ACTIONS,
)
from quicksight_gen.common.tree.datasets import Dataset
from quicksight_gen.common.tree.filters import FilterGroup
from quicksight_gen.common.tree.parameters import ParameterDeclLike
from quicksight_gen.common.tree.visuals import VisualLike


# ---------------------------------------------------------------------------
# Spike-shape ParameterControlNode wrapper — mirrors the VisualNode
# factory pattern. L.1.9 introduces typed Control variants alongside.
# ---------------------------------------------------------------------------

from typing import Callable


@dataclass
class ParameterControlNode:
    """Spike-shape factory wrapper for a ParameterControl.

    L.1.9 introduces typed control variants; this wrapper stays until
    apps migrate.
    """
    builder: Callable[[], ParameterControl]

    def emit(self) -> ParameterControl:
        return self.builder()


# ---------------------------------------------------------------------------
# Layout — GridSlot references a VisualLike by object (locked decision).
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
    # FilterControls join in L.1.9.

    def add_visual[T: VisualLike](self, node: T) -> T:
        """Register a visual on this sheet.

        Accepts any ``VisualLike`` — spike-shape ``VisualNode`` or
        typed subtype (``KPI`` / ``Table`` / ``BarChart`` / ``Sankey``).
        Generic over ``T`` so the caller's variable keeps the concrete
        subtype rather than widening to the Protocol (PEP 695).
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
            FilterControls=[],  # L.1.9
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
    parameters: list[ParameterDeclLike] = field(default_factory=list)
    filter_groups: list[FilterGroup] = field(default_factory=list)
    # CalculatedFields join in L.1.8
    # DataSetIdentifierDeclarations come from the App at emit time

    def add_sheet(self, sheet: Sheet) -> Sheet:
        if any(s.sheet_id == sheet.sheet_id for s in self.sheets):
            raise ValueError(
                f"Sheet {sheet.sheet_id!r} is already on this Analysis"
            )
        self.sheets.append(sheet)
        return sheet

    def add_parameter[T: ParameterDeclLike](self, param: T) -> T:
        """Declare a parameter on this analysis.

        Construction-time check: parameter names are unique within
        the analysis. Catches the silent shadow bug where two declarations
        share a Name and only one wins at deploy time. Generic over
        the concrete subtype so the returned ref keeps its type
        (``StringParam`` / ``IntegerParam`` / ``DateTimeParam``) (PEP 695).
        """
        if any(p.name == param.name for p in self.parameters):
            raise ValueError(
                f"Parameter {param.name!r} is already declared on this Analysis"
            )
        self.parameters.append(param)
        return param

    def add_filter_group(self, fg: FilterGroup) -> FilterGroup:
        """Register a filter group on this analysis.

        Construction-time check: filter group IDs are unique. Same
        shadow-bug class as parameters — two declarations sharing an
        ID silently let one win at deploy.
        """
        if any(
            existing.filter_group_id == fg.filter_group_id
            for existing in self.filter_groups
        ):
            raise ValueError(
                f"FilterGroup {fg.filter_group_id!r} is already on this Analysis"
            )
        self.filter_groups.append(fg)
        return fg

    def datasets(self) -> set[Dataset]:
        """Walk the analysis tree and return every Dataset referenced
        by any visual or filter group. Used by App.dataset_dependencies
        to derive the precise refresh set.

        Visuals using the spike-shape ``VisualNode`` factory wrapper
        don't expose their dataset refs (the factory hides them).
        Typed Visual subtypes (``KPI`` / ``Table`` / ``BarChart`` /
        ``Sankey``) all expose ``datasets()`` and contribute. The
        spike-shape gap closes once apps port to typed subtypes
        (L.2/L.3/L.4).
        """
        deps: set[Dataset] = set()
        for sheet in self.sheets:
            for visual in sheet.visuals:
                if hasattr(visual, "datasets"):
                    deps.update(visual.datasets())
        for fg in self.filter_groups:
            deps.update(fg.datasets())
        return deps

    def emit_definition(
        self,
        *,
        datasets: list[Dataset],
    ) -> AnalysisDefinition:
        return AnalysisDefinition(
            DataSetIdentifierDeclarations=[
                d.emit_declaration() for d in datasets
            ],
            Sheets=[s.emit() for s in self.sheets],
            FilterGroups=(
                [fg.emit() for fg in self.filter_groups]
                if self.filter_groups else None
            ),
            CalculatedFields=None,  # L.1.8
            ParameterDeclarations=(
                [p.emit() for p in self.parameters]
                if self.parameters else None
            ),
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
# App — top-level tree node.
# ---------------------------------------------------------------------------

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

    Datasets are registered on the App via ``add_dataset()`` and
    referenced from visuals / filters by object ref. At emit time
    the App walks the tree's ``dataset_dependencies()`` and includes
    only the datasets actually used in the emitted
    ``DataSetIdentifierDeclarations`` — selective by construction.
    Validation: if a visual or filter references a Dataset that
    isn't registered on the App, ``emit_analysis`` raises with the
    offending identifiers.
    """
    name: str
    cfg: Config
    analysis: Analysis | None = None
    dashboard: Dashboard | None = None
    datasets: list[Dataset] = field(default_factory=list)

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

    def add_dataset(self, dataset: Dataset) -> Dataset:
        """Register a Dataset on the App.

        Construction-time check: dataset identifiers are unique within
        the app. Catches the silent shadow bug where two registrations
        share an identifier and only one wins at deploy.
        """
        if any(d.identifier == dataset.identifier for d in self.datasets):
            raise ValueError(
                f"Dataset {dataset.identifier!r} is already registered on this App"
            )
        self.datasets.append(dataset)
        return dataset

    def dataset_dependencies(self) -> set[Dataset]:
        """The set of Datasets referenced anywhere in the App's tree.

        Walks the Analysis (sheets → visuals + filter_groups). Each
        typed Visual subtype + typed Filter wrapper exposes its own
        ``datasets()`` set; the App unions them.

        **Deployment side effect.** This set drives:
        - selective deploy (only re-create / refresh the datasets
          downstream of an actual change),
        - matview REFRESH ordering (REFRESH only the matviews backing
          datasets that the changed deploy surface depends on).

        Returns an empty set when the App has no Analysis.
        """
        if self.analysis is None:
            return set()
        return self.analysis.datasets()

    def _validate_dataset_references(self) -> None:
        """Raise if the tree references any Dataset not registered on
        this App. Catches "visual references undeclared dataset" at
        emit time, where the existing string-keyed pattern would let
        the mismatch flow through to deploy."""
        referenced = self.dataset_dependencies()
        registered = set(self.datasets)
        unregistered = referenced - registered
        if unregistered:
            ids = sorted(d.identifier for d in unregistered)
            raise ValueError(
                f"App {self.name!r} references unregistered datasets: "
                f"{ids} — register each via app.add_dataset() first."
            )

    def _permissions(self, actions: list[str]) -> list[ResourcePermission] | None:
        if not self.cfg.principal_arns:
            return None
        return [
            ResourcePermission(Principal=arn, Actions=actions)
            for arn in self.cfg.principal_arns
        ]

    def _theme_arn(self) -> str:
        return self.cfg.theme_arn(self.cfg.prefixed("theme"))

    def _used_datasets(self) -> list[Dataset]:
        """Datasets the analysis emits declarations for — only those
        actually referenced by the tree, in registration order."""
        referenced = self.dataset_dependencies()
        return [d for d in self.datasets if d in referenced]

    def emit_analysis(self) -> ModelAnalysis:
        if self.analysis is None:
            raise ValueError(
                "App has no Analysis — call set_analysis() first."
            )
        self._validate_dataset_references()
        return ModelAnalysis(
            AwsAccountId=self.cfg.aws_account_id,
            AnalysisId=self.cfg.prefixed(self.analysis.analysis_id_suffix),
            Name=self.analysis.name,
            ThemeArn=self._theme_arn(),
            Definition=self.analysis.emit_definition(
                datasets=self._used_datasets(),
            ),
            Permissions=self._permissions(ANALYSIS_ACTIONS),
            Tags=self.cfg.tags(),
        )

    def emit_dashboard(self) -> ModelDashboard:
        if self.dashboard is None:
            raise ValueError(
                "App has no Dashboard — call set_dashboard() first."
            )
        self._validate_dataset_references()
        return ModelDashboard(
            AwsAccountId=self.cfg.aws_account_id,
            DashboardId=self.cfg.prefixed(self.dashboard.dashboard_id_suffix),
            Name=self.dashboard.name,
            ThemeArn=self._theme_arn(),
            Definition=self.dashboard.analysis.emit_definition(
                datasets=self._used_datasets(),
            ),
            Permissions=self._permissions(DASHBOARD_ACTIONS),
            Tags=self.cfg.tags(),
            VersionDescription="Generated by quicksight-gen",
            DashboardPublishOptions=DashboardPublishOptions(
                AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
                ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
                SheetControlsOption={"VisibilityState": "EXPANDED"},
            ),
        )
