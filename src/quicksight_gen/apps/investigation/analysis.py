"""QuickSight Analysis + Dashboard for the Investigation app.

K.4.3 lands the Recipient Fanout sheet: dataset declaration, the
analysis-level ``recipient_distinct_sender_count`` calc field that
backs the threshold filter, three KPIs + a ranked table, a date-range
window filter, and a slider-bound integer parameter for the fanout
threshold.

K.4.4 lands the Volume Anomalies sheet: rolling 2-day SUM matview
(``inv_pair_rolling_anomalies``) computed at refresh time, KPI flagged
count, σ-bucket distribution chart (intentionally NOT gated by the
σ filter — its job is to show the full population), and ranked table of
flagged windows.

K.4.5 lands the Money Trail sheet: matview-backed recursive-CTE walk
(``inv_money_trail_edges``) that flattens parent_transfer_id chains to
one row per multi-leg edge, a chain-root dropdown bound to a string
parameter, max-hops + min-hop-amount sliders, and a Sankey diagram +
hop-by-hop detail table laid out side-by-side.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_MONEY_TRAIL,
    DS_INV_RECIPIENT_FANOUT,
    DS_INV_VOLUME_ANOMALIES,
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    SHEET_INV_MONEY_TRAIL,
    V_INV_ANOMALIES_DISTRIBUTION,
    V_INV_ANOMALIES_KPI_FLAGGED,
    V_INV_ANOMALIES_TABLE,
    V_INV_FANOUT_KPI_AMOUNT,
    V_INV_FANOUT_KPI_RECIPIENTS,
    V_INV_FANOUT_KPI_SENDERS,
    V_INV_FANOUT_TABLE,
    V_INV_MONEY_TRAIL_SANKEY,
    V_INV_MONEY_TRAIL_TABLE,
)
from quicksight_gen.apps.investigation.datasets import build_all_datasets
from quicksight_gen.apps.investigation.filters import (
    build_anomalies_filter_controls,
    build_anomalies_parameter_controls,
    build_fanout_filter_controls,
    build_fanout_parameter_controls,
    build_filter_groups,
    build_money_trail_filter_controls,
    build_money_trail_parameter_controls,
    build_parameter_declarations,
)
from quicksight_gen.apps.investigation.visuals import (
    build_anomalies_visuals,
    build_fanout_visuals,
    build_money_trail_visuals,
)
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import VisualId
from quicksight_gen.common.models import (
    Analysis,
    AnalysisDefinition,
    Dashboard,
    DashboardPublishOptions,
    DataSetIdentifierDeclaration,
    GridLayoutConfiguration,
    GridLayoutElement,
    Layout,
    LayoutConfiguration,
    ResourcePermission,
    SheetDefinition,
    SheetTextBox,
)
from quicksight_gen.common.theme import get_preset

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
    "quicksight:UpdateDashboardLinks",
]

# Grid is 36 columns wide.
_FULL = 36
_THIRD = 12
_KPI_ROW_SPAN = 6
_TABLE_ROW_SPAN = 18


def _grid_layout(elements: list[GridLayoutElement]) -> list[Layout]:
    return [Layout(Configuration=LayoutConfiguration(
        GridLayout=GridLayoutConfiguration(Elements=elements),
    ))]


def _full_width_text(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType=GridLayoutElement.TEXT_BOX,
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


def _full_width_visual(element_id: VisualId, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType=GridLayoutElement.VISUAL,
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


def _kpi_triple(
    id_a: VisualId, id_b: VisualId, id_c: VisualId,
) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_a, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_b, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_THIRD,
        ),
        GridLayoutElement(
            ElementId=id_c, ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_THIRD * 2,
        ),
    ]


# ---------------------------------------------------------------------------
# Sheet bodies
# ---------------------------------------------------------------------------

_FANOUT_DESCRIPTION = (
    "Who is receiving money from an unusual number of distinct senders? "
    "Drag the slider to set the minimum sender count; the table ranks "
    "qualifying recipients by funnel width. K.4.7 wires per-row drill "
    "into Account Reconciliation Transactions for the recipient."
)

_ANOMALY_DESCRIPTION = (
    "Which sender → recipient pair just spiked above its baseline? "
    "Rolling 2-day SUM per pair vs. the population mean + standard "
    "deviation. Drag the σ slider to flag the tail. The distribution "
    "chart shows the full population — your slider cutoff against that "
    "shape — while the KPI + table show only flagged windows. K.4.7 "
    "wires per-row drill into Account Reconciliation Transactions."
)

_MONEY_TRAIL_DESCRIPTION = (
    "Where did this transfer actually originate, and where does it go? "
    "Pick a chain root from the dropdown — the Sankey renders that "
    "chain's source-to-target ribbons, and the hop-by-hop table beside "
    "it lists every edge ordered by depth. Single-leg transfers (sales, "
    "raw external arrivals) appear as chain members but don't contribute "
    "Sankey ribbons; drill them from the table into AR Transactions. "
    "K.4.7 wires per-edge cross-app drill into Payment Reconciliation "
    "when the chain crosses external_txn / payment / settlement, "
    "otherwise into AR Transactions."
)


# ---------------------------------------------------------------------------
# Sheets
# ---------------------------------------------------------------------------

def _build_getting_started_sheet(cfg: Config) -> SheetDefinition:
    accent = get_preset(cfg.theme_preset).accent

    welcome = SheetTextBox(
        SheetTextBoxId="inv-gs-welcome",
        Content=rt.text_box(
            rt.inline(
                "Investigation Dashboard",
                font_size="36px",
                color=accent,
            ),
            rt.BR,
            rt.BR,
            rt.body(
                "Compliance / AML triage surface for the Sasquatch "
                "National Bank shared base ledger. Three question-shaped "
                "sheets — recipient fanout, volume anomalies, and money "
                "trail — each one drilling back into Account "
                "Reconciliation or Payment Reconciliation for the row "
                "evidence."
            ),
        ),
    )

    roadmap = SheetTextBox(
        SheetTextBoxId="inv-gs-roadmap",
        Content=rt.text_box(
            rt.heading("Sheets in this dashboard", color=accent),
            rt.BR,
            rt.BR,
            rt.bullets([
                "Recipient Fanout — who is receiving money from too many "
                "distinct senders? (live)",
                "Volume Anomalies — which sender → recipient pair just "
                "spiked above the rolling baseline? (live)",
                "Money Trail — where did this transfer originate and "
                "where does it go? (live)",
            ]),
        ),
    )

    return SheetDefinition(
        SheetId=SHEET_INV_GETTING_STARTED,
        Name="Getting Started",
        Title="Getting Started",
        Description=(
            "Landing page — summarises each tab in this dashboard. "
            "No filters or visuals."
        ),
        ContentType="INTERACTIVE",
        TextBoxes=[welcome, roadmap],
        Layouts=_grid_layout([
            _full_width_text("inv-gs-welcome", 5),
            _full_width_text("inv-gs-roadmap", 6),
        ]),
    )


def _build_recipient_fanout_sheet(cfg: Config) -> SheetDefinition:
    """Recipient Fanout — KPIs + ranked table.

    Layout:
      * Row 1: 3 KPIs (qualifying recipients / distinct senders /
        total inbound), each ⅓ width.
      * Row 2: full-width recipient table sorted by distinct sender
        count desc.
    Date-range filter widget + threshold slider live in the sheet's
    controls panel (FilterControls + ParameterControls).
    """
    return SheetDefinition(
        SheetId=SHEET_INV_FANOUT,
        Name="Recipient Fanout",
        Title="Recipient Fanout",
        Description=_FANOUT_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_fanout_visuals(cfg),
        FilterControls=build_fanout_filter_controls(cfg),
        ParameterControls=build_fanout_parameter_controls(cfg),
        Layouts=_grid_layout(
            _kpi_triple(
                V_INV_FANOUT_KPI_RECIPIENTS,
                V_INV_FANOUT_KPI_SENDERS,
                V_INV_FANOUT_KPI_AMOUNT,
            )
            + [_full_width_visual(V_INV_FANOUT_TABLE, _TABLE_ROW_SPAN)]
        ),
    )


def _build_volume_anomalies_sheet(cfg: Config) -> SheetDefinition:
    """Volume Anomalies — flagged-count KPI + distribution + ranked table.

    Layout:
      * Row 1: KPI flagged count (¼ width-ish) + distribution bar chart
        side-by-side. KPI is third-width, chart takes the remaining
        two-thirds so its bucket bars have room.
      * Row 2: full-width flagged table sorted by z_score desc.
    Date-range filter widget + σ slider live in the sheet's controls
    panel. The σ filter is scoped SELECTED_VISUALS in filters.py so the
    distribution chart sees the full population while KPI + table see
    only the cutoff tail.
    """
    layout_elements = [
        GridLayoutElement(
            ElementId=V_INV_ANOMALIES_KPI_FLAGGED,
            ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=V_INV_ANOMALIES_DISTRIBUTION,
            ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD * 2, RowSpan=_KPI_ROW_SPAN * 2,
            ColumnIndex=_THIRD,
        ),
        _full_width_visual(V_INV_ANOMALIES_TABLE, _TABLE_ROW_SPAN),
    ]
    return SheetDefinition(
        SheetId=SHEET_INV_ANOMALIES,
        Name="Volume Anomalies",
        Title="Volume Anomalies",
        Description=_ANOMALY_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_anomalies_visuals(cfg),
        FilterControls=build_anomalies_filter_controls(cfg),
        ParameterControls=build_anomalies_parameter_controls(cfg),
        Layouts=_grid_layout(layout_elements),
    )


def _build_money_trail_sheet(cfg: Config) -> SheetDefinition:
    """Money Trail — Sankey + hop-by-hop detail table side-by-side.

    Layout:
      * Row 1: Sankey on the left (⅔ width), table on the right (⅓
        width). The Sankey is the headline; the table is reference for
        edges the diagram hides plus the canonical surface for drill
        into AR Transactions / PR Payment Reconciliation (K.4.7).
    Chain-root dropdown + max-hops slider + min-hop-amount slider live
    in the parameter controls panel.
    """
    sankey_height = _TABLE_ROW_SPAN
    layout_elements = [
        GridLayoutElement(
            ElementId=V_INV_MONEY_TRAIL_SANKEY,
            ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD * 2,
            RowSpan=sankey_height,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=V_INV_MONEY_TRAIL_TABLE,
            ElementType=GridLayoutElement.VISUAL,
            ColumnSpan=_THIRD,
            RowSpan=sankey_height,
            ColumnIndex=_THIRD * 2,
        ),
    ]
    return SheetDefinition(
        SheetId=SHEET_INV_MONEY_TRAIL,
        Name="Money Trail",
        Title="Money Trail",
        Description=_MONEY_TRAIL_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_money_trail_visuals(cfg),
        FilterControls=build_money_trail_filter_controls(cfg),
        ParameterControls=build_money_trail_parameter_controls(cfg),
        Layouts=_grid_layout(layout_elements),
    )


# ---------------------------------------------------------------------------
# Calculated fields
# ---------------------------------------------------------------------------

def _build_calculated_fields() -> list[dict]:
    """Analysis-level calc fields.

    ``recipient_distinct_sender_count`` is a windowed distinct count of
    sender_account_id partitioned by recipient_account_id — every row of
    a recipient carries the same value. The threshold NumericRangeFilter
    references this calc field as its column, so dragging the slider
    narrows visuals to recipients whose count crosses the threshold.
    """
    return [
        {
            "Name": CF_INV_FANOUT_DISTINCT_SENDERS,
            "DataSetIdentifier": DS_INV_RECIPIENT_FANOUT,
            "Expression": (
                "distinct_count({sender_account_id}, "
                "[{recipient_account_id}])"
            ),
        },
    ]


# ---------------------------------------------------------------------------
# Dataset declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical Investigation dataset identifiers to ARNs.

    Order matches ``build_all_datasets`` so each ARN lines up with the
    intended logical identifier.
    """
    datasets = build_all_datasets(cfg)
    names = [
        DS_INV_RECIPIENT_FANOUT,
        DS_INV_VOLUME_ANOMALIES,
        DS_INV_MONEY_TRAIL,
    ]
    return [
        DataSetIdentifierDeclaration(
            Identifier=name,
            DataSetArn=cfg.dataset_arn(ds.DataSetId),
        )
        for name, ds in zip(names, datasets)
    ]


# ---------------------------------------------------------------------------
# Analysis / Dashboard
# ---------------------------------------------------------------------------

def _build_definition(cfg: Config) -> AnalysisDefinition:
    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
        Sheets=[
            _build_getting_started_sheet(cfg),
            _build_recipient_fanout_sheet(cfg),
            _build_volume_anomalies_sheet(cfg),
            _build_money_trail_sheet(cfg),
        ],
        FilterGroups=build_filter_groups(cfg),
        CalculatedFields=_build_calculated_fields(),
        ParameterDeclarations=build_parameter_declarations(cfg),
    )


def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Investigation"
    return "Investigation"


def build_analysis(cfg: Config) -> Analysis:
    """Build the complete Investigation Analysis resource."""
    analysis_id = cfg.prefixed("investigation-analysis")
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arns:
        permissions = [
            ResourcePermission(Principal=arn, Actions=_ANALYSIS_ACTIONS)
            for arn in cfg.principal_arns
        ]

    return Analysis(
        AwsAccountId=cfg.aws_account_id,
        AnalysisId=analysis_id,
        Name=_analysis_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
    )


def build_investigation_dashboard(cfg: Config) -> Dashboard:
    """Build the Investigation published Dashboard."""
    dashboard_id = cfg.prefixed("investigation-dashboard")
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arns:
        permissions = [
            ResourcePermission(Principal=arn, Actions=_DASHBOARD_ACTIONS)
            for arn in cfg.principal_arns
        ]

    return Dashboard(
        AwsAccountId=cfg.aws_account_id,
        DashboardId=dashboard_id,
        Name=_analysis_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
        VersionDescription="Generated by quicksight-gen",
        DashboardPublishOptions=DashboardPublishOptions(
            AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
            ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
            SheetControlsOption={"VisibilityState": "EXPANDED"},
        ),
    )
