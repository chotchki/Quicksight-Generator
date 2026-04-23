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
    Visual,
)
from quicksight_gen.common.models import Analysis as ModelAnalysis
from quicksight_gen.common.models import Dashboard as ModelDashboard

from quicksight_gen.common.ids import FilterGroupId, SheetId, VisualId
from quicksight_gen.common.tree._helpers import (
    ANALYSIS_ACTIONS,
    DASHBOARD_ACTIONS,
)
from quicksight_gen.common.tree.actions import Drill
from quicksight_gen.common.tree.calc_fields import CalcField
from quicksight_gen.common.tree.controls import (
    FilterControlLike,
    ParameterControlLike,
)
from quicksight_gen.common.tree.datasets import Dataset
from quicksight_gen.common.tree.filters import FilterGroup
from quicksight_gen.common.tree.parameters import ParameterDeclLike
from quicksight_gen.common.tree.text_boxes import TextBox
from quicksight_gen.common.tree.visuals import VisualLike


# ---------------------------------------------------------------------------
# Spike-shape ParameterControlNode wrapper — mirrors the VisualNode
# factory pattern. L.1.9 introduces typed Control variants alongside.
# ---------------------------------------------------------------------------

from typing import Callable, Protocol, runtime_checkable


# Field-well slot roles used by the auto-id resolver. The `role`
# letter goes into the auto-derived field_id so the synthesized id
# encodes which well a leaf came from.
_FIELD_SLOTS: tuple[tuple[str, str], ...] = (
    ("group_by", "g"),  # Table
    ("values", "v"),    # KPI / Table / BarChart
    ("category", "c"),  # BarChart
    ("source", "s"),    # Sankey
    ("target", "t"),    # Sankey
    ("weight", "w"),    # Sankey
)


def _resolve_field_ids(
    *, visual, visual_kind: str, sheet_idx: int, visual_idx: int,
) -> None:
    """Walk a visual's field-well slots and assign auto field_ids to
    any Dim/Measure leaves that left field_id unset.

    Iterates the fixed ``_FIELD_SLOTS`` table — each entry names an
    attribute and a one-letter role tag. Missing attributes (e.g. KPI
    has no ``group_by``) are skipped via ``getattr`` default ``None``.
    Slots may be a single leaf (Sankey ``source`` / ``target`` /
    ``weight``) or a list (KPI / Table / BarChart ``values``); both
    shapes are handled.
    """
    for attr, role in _FIELD_SLOTS:
        slot = getattr(visual, attr, None)
        if slot is None:
            continue
        leaves = slot if isinstance(slot, list) else [slot]
        for slot_idx, leaf in enumerate(leaves):
            if leaf is None:
                continue
            if getattr(leaf, "field_id", "explicit") is None:
                leaf.field_id = (
                    f"f-{visual_kind}-s{sheet_idx}-v{visual_idx}-{role}{slot_idx}"
                )


@dataclass(eq=False)
class ParameterControlNode:
    """Spike-shape factory wrapper for a ParameterControl.

    L.1.9 introduces typed control variants; this wrapper stays until
    apps migrate.
    """
    builder: Callable[[], ParameterControl]

    def emit(self) -> ParameterControl:
        return self.builder()


# ---------------------------------------------------------------------------
# Layout — GridSlot references a LayoutNode by object (locked decision).
# LayoutNode hides QuickSight's split between Visuals and TextBoxes —
# both turn into a GridLayoutElement carrying an id + ElementType, but
# flow into different SheetDefinition fields at emit time.
# ---------------------------------------------------------------------------

@runtime_checkable
class LayoutNode(Protocol):
    """Anything placeable in a sheet's grid layout.

    Both typed visual subtypes (``KPI`` / ``Table`` / ``BarChart`` /
    ``Sankey``) and the typed ``TextBox`` wrapper satisfy this Protocol.
    Each exposes ``element_id`` (the layout slot's ``ElementId``) and
    ``element_type`` (``"VISUAL"`` or ``"TEXT_BOX"``) — the slot reads
    them off the node at emit time.

    The Protocol means ``Sheet.place(node, ...)`` accepts both visuals
    and text boxes uniformly; QuickSight's two-list split (Visuals vs
    TextBoxes in ``SheetDefinition``) stays an emit-time concern that
    callers never see.
    """
    @property
    def element_id(self) -> str: ...

    @property
    def element_type(self) -> str: ...


@dataclass(eq=False)
class GridSlot:
    """One placement in a sheet's grid layout.

    Holds an OBJECT reference to the placed ``LayoutNode``. The element
    id and element type are read off the node at emit time — the slot
    is agnostic about whether it carries a visual or a text box.
    """
    element: LayoutNode
    col_span: int
    row_span: int
    col_index: int
    row_index: int | None = None

    def emit(self) -> GridLayoutElement:
        return GridLayoutElement(
            ElementId=self.element.element_id,
            ElementType=self.element.element_type,
            ColumnSpan=self.col_span,
            RowSpan=self.row_span,
            ColumnIndex=self.col_index,
            RowIndex=self.row_index,
        )


# ---------------------------------------------------------------------------
# Sheet — child of Analysis.
# ---------------------------------------------------------------------------

@dataclass(eq=False)
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
    parameter_controls: list[ParameterControlLike | ParameterControlNode] = field(
        default_factory=list,
    )
    filter_controls: list[FilterControlLike] = field(default_factory=list)
    text_boxes: list[TextBox] = field(default_factory=list)
    grid_slots: list[GridSlot] = field(default_factory=list)

    def add_visual[T: VisualLike](self, node: T) -> T:
        """Register a visual on this sheet.

        Accepts any ``VisualLike`` — spike-shape ``VisualNode`` or
        typed subtype (``KPI`` / ``Table`` / ``BarChart`` / ``Sankey``).
        Generic over ``T`` so the caller's variable keeps the concrete
        subtype rather than widening to the Protocol (PEP 695).
        """
        self.visuals.append(node)
        return node

    def add_parameter_control[T: ParameterControlLike | ParameterControlNode](
        self, node: T,
    ) -> T:
        """Register a parameter control on this sheet.

        Accepts either a typed control (``ParameterDropdown`` /
        ``ParameterSlider`` / ``ParameterDateTimePicker``) or the
        spike-shape ``ParameterControlNode`` factory wrapper.
        """
        self.parameter_controls.append(node)
        return node

    def add_filter_control[T: FilterControlLike](self, node: T) -> T:
        """Register a filter control on this sheet.

        Typed controls (``FilterDropdown`` / ``FilterSlider`` /
        ``FilterDateTimePicker`` / ``FilterCrossSheet``) bind to
        a ``FilterLike`` inside a registered FilterGroup; the
        control's ``SourceFilterId`` resolves at emit time to the
        bound filter's id.
        """
        self.filter_controls.append(node)
        return node

    def add_text_box(self, text_box: TextBox) -> TextBox:
        """Register a typed ``TextBox`` on this sheet.

        The TextBox is a ``LayoutNode``, so the same ``Sheet.place(...)``
        method that places visuals also places text boxes — the layout
        slot reads ``element_id`` / ``element_type`` off the node and
        emits the appropriate ``GridLayoutElement``.
        """
        self.text_boxes.append(text_box)
        return text_box

    def find_visual(
        self,
        *,
        title: str | None = None,
        title_contains: str | None = None,
        visual_id: VisualId | str | None = None,
    ) -> VisualLike:
        """Look up a single visual on this sheet by title / partial title /
        visual id.

        Designed for e2e + introspection: pass any of the three lookup
        keys and get the matching node back. Raises if no match or
        multiple matches — the API forces unambiguity at the call
        site so tests can rely on the result.

        Auto-IDs (L.1.8.5) make this the right way to find a visual
        from outside the tree — IDs are not stable under tree
        restructuring, but titles + structural position are.
        """
        matches: list[VisualLike] = []
        for v in self.visuals:
            if visual_id is not None and v.visual_id == visual_id:
                matches.append(v)
                continue
            v_title = getattr(v, "title", None)
            if title is not None and v_title == title:
                matches.append(v)
                continue
            if title_contains is not None and v_title and title_contains in v_title:
                matches.append(v)
                continue
        if not matches:
            raise ValueError(
                f"No visual on sheet {self.sheet_id!r} matches "
                f"title={title!r} title_contains={title_contains!r} "
                f"visual_id={visual_id!r}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Multiple visuals on sheet {self.sheet_id!r} match "
                f"title={title!r} title_contains={title_contains!r} "
                f"visual_id={visual_id!r} — got {len(matches)}; "
                f"narrow the criteria."
            )
        return matches[0]

    def place(
        self,
        node: LayoutNode,
        *,
        col_span: int,
        row_span: int,
        col_index: int,
        row_index: int | None = None,
    ) -> GridSlot:
        """Place a registered ``LayoutNode`` (visual or text box) into
        the grid layout.

        Construction-time checks:
        - The node must already be registered on this sheet via
          ``add_visual()`` (for visuals) or ``add_text_box()`` (for
          text boxes). Catches the wrong-sheet bug class — a visual
          built for sheet A but placed on sheet B never silently
          renders.
        - The node must not already be placed in the grid layout
          (placing the same node twice emits two slots with the same
          ElementId, which QuickSight rejects).

        The slot reads ``element_id`` / ``element_type`` off the node
        at emit time — visuals contribute ``("VISUAL", visual_id)``,
        text boxes contribute ``("TEXT_BOX", text_box_id)``.
        """
        if isinstance(node, TextBox):
            registry = self.text_boxes
            registry_method = "add_text_box"
            kind_label = "TextBox"
            id_for_msg = node.text_box_id
        else:
            registry = self.visuals
            registry_method = "add_visual"
            kind_label = "Visual"
            id_for_msg = getattr(node, "visual_id", "?")
        if node not in registry:
            raise ValueError(
                f"{kind_label} {id_for_msg!r} isn't registered on this "
                f"sheet — call {registry_method}() first."
            )
        for existing in self.grid_slots:
            if existing.element is node:
                raise ValueError(
                    f"{kind_label} {id_for_msg!r} is already placed on "
                    f"sheet {self.sheet_id!r}. A node can occupy at most "
                    f"one grid slot — placing it twice emits duplicate "
                    f"ElementIds."
                )
        slot = GridSlot(
            element=node,
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
            FilterControls=(
                [fc.emit() for fc in self.filter_controls]
                if self.filter_controls else []
            ),
            ParameterControls=(
                [c.emit() for c in self.parameter_controls]
                if self.parameter_controls else None
            ),
            TextBoxes=(
                [tb.emit() for tb in self.text_boxes]
                if self.text_boxes else None
            ),
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

@dataclass(eq=False)
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
    calc_fields: list[CalcField] = field(default_factory=list)
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

        Construction-time check: explicit filter group IDs are unique.
        (Auto-IDs are unique by construction — assigned from the
        index in the analysis's filter_groups list — so the check
        only applies when callers passed an explicit id.)
        """
        if fg.filter_group_id is not None and any(
            existing.filter_group_id == fg.filter_group_id
            for existing in self.filter_groups
        ):
            raise ValueError(
                f"FilterGroup {fg.filter_group_id!r} is already on this Analysis"
            )
        self.filter_groups.append(fg)
        return fg

    def find_sheet(
        self,
        *,
        name: str | None = None,
        sheet_id: SheetId | str | None = None,
    ) -> Sheet:
        """Look up a single sheet on this analysis by name or sheet id.

        Raises on no-match or multi-match. Sheet IDs stay explicit
        (URL-facing per the L.1.8.5 mixed scheme) so passing
        ``sheet_id=`` is the most robust lookup; ``name=`` is the
        next-best for tests that don't want to hardcode IDs.
        """
        matches = []
        for s in self.sheets:
            if sheet_id is not None and s.sheet_id == sheet_id:
                matches.append(s)
                continue
            if name is not None and s.name == name:
                matches.append(s)
                continue
        if not matches:
            raise ValueError(
                f"No sheet on Analysis {self.name!r} matches "
                f"name={name!r} sheet_id={sheet_id!r}"
            )
        if len(matches) > 1:
            raise ValueError(
                f"Multiple sheets on Analysis {self.name!r} match "
                f"name={name!r} sheet_id={sheet_id!r} — got {len(matches)}."
            )
        return matches[0]

    def find_filter_group(
        self,
        *,
        filter_group_id: FilterGroupId | str | None = None,
    ) -> FilterGroup:
        """Look up a single filter group by id (auto or explicit)."""
        matches = [
            fg for fg in self.filter_groups
            if fg.filter_group_id == filter_group_id
        ]
        if not matches:
            raise ValueError(
                f"No filter group on Analysis {self.name!r} with "
                f"filter_group_id={filter_group_id!r}"
            )
        return matches[0]

    def find_calc_field(self, *, name: str) -> CalcField:
        """Look up a single calc field by name."""
        matches = [c for c in self.calc_fields if c.name == name]
        if not matches:
            raise ValueError(
                f"No calc field on Analysis {self.name!r} named {name!r}"
            )
        return matches[0]

    def add_calc_field(self, calc: CalcField) -> CalcField:
        """Register a calculated field on this analysis.

        Construction-time check: calc field names are unique within
        the analysis. Two calc fields sharing a Name silently let one
        win at deploy time — same shadow-bug class as parameters /
        filter groups / datasets.
        """
        if any(c.name == calc.name for c in self.calc_fields):
            raise ValueError(
                f"CalcField {calc.name!r} is already on this Analysis"
            )
        self.calc_fields.append(calc)
        return calc

    def datasets(self) -> set[Dataset]:
        """Walk the analysis tree and return every Dataset referenced
        by any visual, filter group, or registered calc field. Used by
        App.dataset_dependencies to derive the precise refresh set.

        Visuals using the spike-shape ``VisualNode`` factory wrapper
        don't expose their dataset refs (the factory hides them).
        Typed Visual subtypes (``KPI`` / ``Table`` / ``BarChart`` /
        ``Sankey``) all expose ``datasets()`` and contribute. The
        spike-shape gap closes once apps port to typed subtypes
        (L.2/L.3/L.4).

        Registered CalcFields contribute too — their ``Dataset`` ref
        becomes a dep even if no visual directly references the
        underlying columns.
        """
        deps: set[Dataset] = set()
        for sheet in self.sheets:
            for visual in sheet.visuals:
                if hasattr(visual, "datasets"):
                    deps.update(visual.datasets())
            # Parameter / filter controls with LinkedValues populate
            # from a Dataset — that's a dep too.
            for ctrl in sheet.parameter_controls:
                if hasattr(ctrl, "datasets"):
                    deps.update(ctrl.datasets())
            for ctrl in sheet.filter_controls:
                if hasattr(ctrl, "datasets"):
                    deps.update(ctrl.datasets())
        for fg in self.filter_groups:
            deps.update(fg.datasets())
        for calc in self.calc_fields:
            deps.add(calc.dataset)
        return deps

    def calc_fields_referenced(self) -> set[CalcField]:
        """Walk the analysis tree and return every CalcField referenced
        by any visual or filter group. Distinct from ``self.calc_fields``
        (the registry): this returns only the calc fields actually used.

        Catches "calc field declared but never used" (registered but
        not in this set) and "calc field used but not declared" (in
        this set but not in the registry — App._validate_calc_field_
        references raises on emit).
        """
        deps: set[CalcField] = set()
        for sheet in self.sheets:
            for visual in sheet.visuals:
                if hasattr(visual, "calc_fields"):
                    deps.update(visual.calc_fields())
        for fg in self.filter_groups:
            deps.update(fg.calc_fields())
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
            CalculatedFields=(
                [c.emit() for c in self.calc_fields]
                if self.calc_fields else None
            ),
            ParameterDeclarations=(
                [p.emit() for p in self.parameters]
                if self.parameters else None
            ),
        )


# ---------------------------------------------------------------------------
# Dashboard — references an Analysis (object ref) so they share the
# same definition.
# ---------------------------------------------------------------------------

@dataclass(eq=False)
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

@dataclass(eq=False)
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
    # Bare-string column refs (``Dim(ds, "amount")`` instead of
    # ``ds["amount"].dim()``) are typo-prone — they bypass the dataset
    # contract validation. ``emit_analysis`` raises on any bare-string
    # column ref unless this flag is set. Test fixtures + datasets
    # without a registered contract (kitchen-sink) opt in via
    # ``allow_bare_strings=True``.
    allow_bare_strings: bool = False

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

    def find_sheet(
        self,
        *,
        name: str | None = None,
        sheet_id: SheetId | str | None = None,
    ) -> Sheet:
        """Convenience pass-through to ``app.analysis.find_sheet(...)``."""
        if self.analysis is None:
            raise ValueError(
                f"App {self.name!r} has no Analysis — can't find sheets."
            )
        return self.analysis.find_sheet(name=name, sheet_id=sheet_id)

    def _resolve_auto_ids(self) -> None:
        """Walk the tree and assign auto-IDs to nodes that left their
        IDs unset. Called from emit_analysis / emit_dashboard before
        any validation or emission.

        Mixed scheme (L.1.8.5 + L.1.16): URL-facing IDs (``SheetId``,
        ``ParameterName``) and analyst-facing identifiers (``Dataset``
        identifier) stay explicit. Internal IDs the analyst never
        types — visual_id, filter_id, control_id, action_id, field_id,
        calc-field name — get tree-position-derived defaults when
        omitted.

        Auto-ID formats:
        - Visual: ``v-{kind}-s{sheet_idx}-{visual_idx}``
        - FilterGroup: ``fg-{idx}`` — analysis-scoped
        - Filter: ``f-{kind}-fg{fg_idx}-{filt_idx}``
        - ParameterControl: ``pc-{kind}-s{sheet_idx}-{ctrl_idx}``
        - FilterControl: ``fc-{kind}-s{sheet_idx}-{ctrl_idx}``
        - Drill action: ``act-s{sheet_idx}-v{visual_idx}-{action_idx}``
        - Field-well leaf (Dim/Measure): ``f-{visual_kind}-s{sheet_idx}
          -v{visual_idx}-{role}{slot_idx}`` where role tags the field
          well slot (``g`` group_by, ``v`` values, ``c`` category,
          ``s`` source, ``t`` target, ``w`` weight)
        - CalcField: ``calc-{idx}`` — analysis-scoped

        Same-sheet drills also get their target_sheet back-filled here
        (Drill.target_sheet=None means "the sheet that owns me").

        Idempotent: nodes that already have explicit IDs aren't touched.
        """
        if self.analysis is None:
            return
        for sheet_idx, sheet in enumerate(self.analysis.sheets):
            for visual_idx, visual in enumerate(sheet.visuals):
                kind = getattr(visual, "_AUTO_KIND", None)
                current = getattr(visual, "visual_id", None)
                if kind is not None and current is None:
                    visual.visual_id = VisualId(
                        f"v-{kind}-s{sheet_idx}-{visual_idx}",
                    )
                # Field-well leaves — Dim/Measure get position-indexed
                # field_ids. Walk the slots that exist on this visual
                # type; missing attributes (e.g. KPI has no group_by)
                # are skipped via getattr default.
                _resolve_field_ids(
                    visual=visual,
                    visual_kind=kind or "v",
                    sheet_idx=sheet_idx,
                    visual_idx=visual_idx,
                )
                # Drill action IDs (sheet+visual scoped). Same-sheet
                # drills (target_sheet=None at construction) get the
                # owning sheet back-filled here — the cycle closes the
                # same time IDs resolve.
                actions = getattr(visual, "actions", None)
                if actions:
                    for action_idx, action in enumerate(actions):
                        if action.action_id is None:
                            action.action_id = (
                                f"act-s{sheet_idx}-v{visual_idx}-{action_idx}"
                            )
                        if hasattr(action, "target_sheet") and action.target_sheet is None:
                            action.target_sheet = sheet
            # Parameter controls — auto-IDs scoped to the sheet.
            for ctrl_idx, ctrl in enumerate(sheet.parameter_controls):
                kind = getattr(ctrl, "_AUTO_KIND", None)
                if kind is not None and getattr(ctrl, "control_id", None) is None:
                    ctrl.control_id = f"pc-{kind}-s{sheet_idx}-{ctrl_idx}"
            # Filter controls — auto-IDs scoped to the sheet.
            for ctrl_idx, ctrl in enumerate(sheet.filter_controls):
                kind = getattr(ctrl, "_AUTO_KIND", None)
                if kind is not None and getattr(ctrl, "control_id", None) is None:
                    ctrl.control_id = f"fc-{kind}-s{sheet_idx}-{ctrl_idx}"
        for fg_idx, fg in enumerate(self.analysis.filter_groups):
            if fg.filter_group_id is None:
                fg.filter_group_id = FilterGroupId(f"fg-{fg_idx}")
            for filt_idx, filt in enumerate(fg.filters):
                kind = getattr(filt, "_AUTO_KIND", None)
                if kind is not None and getattr(filt, "filter_id", None) is None:
                    filt.filter_id = f"f-{kind}-fg{fg_idx}-{filt_idx}"
        # CalcField names — analysis-scoped position index.
        for calc_idx, calc in enumerate(self.analysis.calc_fields):
            if calc.name is None:
                calc.name = f"calc-{calc_idx}"

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

    def _validate_parameter_references(self) -> None:
        """Raise if any ParameterDeclLike reference in the tree
        (control bindings, NumericRangeFilter parameter bounds) points
        at a parameter that isn't registered on the analysis.

        Same shadow-bug class as datasets and calc fields: a typed
        parameter ref with .name set but never registered on the
        analysis would emit a SourceParameterName / Parameter binding
        that QuickSight resolves to "no such parameter" silently —
        controls don't drive their bound parameter, filters don't
        narrow.

        DrillParam (in K.2 ``common/drill.py``) takes a string
        ParameterName — those aren't validated here. Closing that
        gap requires a typed-parameter-ref refactor of DrillParam,
        queued as L.1.x follow-up.
        """
        if self.analysis is None:
            return
        registered_params = self.analysis.parameters
        bad: list[str] = []

        def _check(param, where: str) -> None:
            if param is None:
                return
            if not any(p is param for p in registered_params):
                bad.append(
                    f"{where} → parameter {param.name!r} not registered"
                )

        for sheet in self.analysis.sheets:
            for ctrl in sheet.parameter_controls:
                p = getattr(ctrl, "parameter", None)
                _check(p, f"sheet {sheet.sheet_id!r} parameter control")
        for fg in self.analysis.filter_groups:
            for f in fg.filters:
                _check(
                    getattr(f, "minimum_parameter", None),
                    f"filter {f.filter_id!r} minimum_parameter",
                )
                _check(
                    getattr(f, "maximum_parameter", None),
                    f"filter {f.filter_id!r} maximum_parameter",
                )
        if bad:
            raise ValueError(
                f"App {self.name!r} has parameter references that aren't "
                f"registered on the analysis: {bad} — call "
                f"analysis.add_parameter() first."
            )

    def _validate_drill_destinations(self) -> None:
        """Raise if any Drill action targets a Sheet that isn't on
        this App's Analysis. Catches "drill into a sheet that doesn't
        exist" at emit time. The string-only ``target_sheet=SheetId(...)``
        pattern lets typos through to deploy where the click silently
        does nothing.

        Sheet identity check uses ``is`` rather than ``in``/``set``
        because Sheet's dataclass-generated ``__eq__`` compares fields
        and Sheet isn't hashable — but we want OBJECT identity here,
        not field equality.
        """
        if self.analysis is None:
            return
        registered_sheets = self.analysis.sheets
        bad: list[str] = []
        for sheet in registered_sheets:
            for visual in sheet.visuals:
                actions = getattr(visual, "actions", None) or []
                for action in actions:
                    if not any(
                        action.target_sheet is s for s in registered_sheets
                    ):
                        bad.append(
                            f"action {action.name!r} on visual "
                            f"{getattr(visual, 'visual_id', '?')!r} → sheet "
                            f"{action.target_sheet.sheet_id!r}"
                        )
        if bad:
            raise ValueError(
                f"App {self.name!r} has drill actions targeting sheets that "
                f"aren't registered on the analysis: {bad}"
            )

    def _validate_no_bare_string_columns(self) -> None:
        """Raise if any tree node uses a bare-string column ref.

        Bare strings (``Dim(ds, "amount")``) bypass the dataset contract
        validation that ``ds["amount"]`` carries — a typo silently
        renders a broken visual at deploy. The validated path is the
        ``Column`` ref form, ``ds["column_name"].dim()`` /
        ``.sum()`` / etc.

        ``allow_bare_strings=True`` on the App opts out of this check
        for test fixtures and datasets without a registered contract
        (the kitchen sink, which has no DatasetContract).
        """
        if self.allow_bare_strings or self.analysis is None:
            return
        bad: list[str] = []

        def _check(column, where: str) -> None:
            if isinstance(column, str):
                bad.append(f"{where} → {column!r}")

        for sheet in self.analysis.sheets:
            for visual in sheet.visuals:
                for attr, _role in _FIELD_SLOTS:
                    slot = getattr(visual, attr, None)
                    if slot is None:
                        continue
                    leaves = slot if isinstance(slot, list) else [slot]
                    for leaf in leaves:
                        if leaf is None:
                            continue
                        _check(
                            getattr(leaf, "column", None),
                            f"sheet {sheet.sheet_id!r} visual "
                            f"{getattr(visual, 'visual_id', '?')!r} "
                            f"{attr}",
                        )
                # LinkedValues on parameter / filter controls hits the
                # same column-ref slot.
                for ctrl in (
                    *sheet.parameter_controls, *sheet.filter_controls,
                ):
                    sv = getattr(ctrl, "selectable_values", None)
                    if sv is not None:
                        _check(
                            getattr(sv, "column", None),
                            f"sheet {sheet.sheet_id!r} control "
                            f"{getattr(ctrl, 'control_id', '?')!r} "
                            f"selectable_values",
                        )
        for fg in self.analysis.filter_groups:
            for filt in fg.filters:
                _check(
                    getattr(filt, "column", None),
                    f"filter {getattr(filt, 'filter_id', '?')!r}",
                )
        if bad:
            raise ValueError(
                f"App {self.name!r} has bare-string column refs "
                f"(typo-prone — they bypass the dataset contract "
                f"validation that ds[\"col\"] carries):\n  "
                + "\n  ".join(bad)
                + "\n\nUse the typed form: ds[\"column_name\"].dim() "
                "/ .sum() / .date() / etc. — or pass "
                "``allow_bare_strings=True`` on the App when no "
                "dataset contract is registered (test fixtures)."
            )

    def _validate_calc_field_references(self) -> None:
        """Raise if the tree references any CalcField not registered on
        this App's Analysis. Catches "filter / visual references calc
        field that doesn't exist" at emit time. The string-only
        column pattern lets that bug flow through to deploy where it
        renders silently as an empty column."""
        if self.analysis is None:
            return
        referenced = self.analysis.calc_fields_referenced()
        registered = set(self.analysis.calc_fields)
        unregistered = referenced - registered
        if unregistered:
            names = sorted(c.name for c in unregistered)
            raise ValueError(
                f"App {self.name!r} references unregistered calc fields: "
                f"{names} — register each via "
                f"app.analysis.add_calc_field() first."
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
        self._resolve_auto_ids()
        self._validate_dataset_references()
        self._validate_calc_field_references()
        self._validate_parameter_references()
        self._validate_drill_destinations()
        self._validate_no_bare_string_columns()
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
        self._resolve_auto_ids()
        self._validate_dataset_references()
        self._validate_calc_field_references()
        self._validate_parameter_references()
        self._validate_drill_destinations()
        self._validate_no_bare_string_columns()
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
