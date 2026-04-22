"""QuickSight Analysis + Dashboard for the Investigation app.

K.4.2 ships the skeleton: 4 sheets (Getting Started + 3 stubs named for
K.4.3 / K.4.4 / K.4.5), zero datasets, zero filter groups, zero
visuals. The stub sheets carry only a text-box explaining what the
sheet will hold once K.4.3 / K.4.4 / K.4.5 land.

The skeleton exists so the app can be wired into the CLI, deployed to
AWS QuickSight, and exercised end-to-end before any sheet content
arrives — failures in dataset wiring or sheet plumbing surface up
front, not after the visuals are built.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
    SHEET_INV_MONEY_TRAIL,
)
from quicksight_gen.apps.investigation.datasets import build_all_datasets
from quicksight_gen.apps.investigation.filters import build_filter_groups
from quicksight_gen.common import rich_text as rt
from quicksight_gen.common.config import Config
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

_FULL = 36


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


# ---------------------------------------------------------------------------
# Sheet bodies
# ---------------------------------------------------------------------------

_FANOUT_BODY = (
    "Who is receiving money from an unusual number of distinct senders? "
    "Surfaces recipient accounts whose distinct-sender count over a "
    "chosen window crosses a fanout threshold — the classic structuring "
    "/ funnel-account pattern. KPI + ranked table; cross-app drill into "
    "Account Reconciliation Transactions for the recipient."
)

_ANOMALY_BODY = (
    "Which sender → recipient pair just spiked? Rolling SUM(amount) per "
    "pair over a sliding window, compared against the population mean + "
    "standard deviation across pairs. Rows above mean + Nσ are flagged. "
    "Distribution plot + flagged-rows table; cross-app drill into the "
    "underlying transactions for the pair × window."
)

_MONEY_TRAIL_BODY = (
    "Where did this transfer actually originate, and where does it go? "
    "Recursive walk up and down the parent_transfer_id chain from a "
    "selected transfer_id, flattened to one row per edge. Sankey is the "
    "headline visual; hop-by-hop detail table sits beside it. Cross-app "
    "drill into Payment Reconciliation if the chain crosses an "
    "external_txn / payment / settlement edge; otherwise into AR "
    "Transactions."
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
                "distinct senders? (lands in K.4.3)",
                "Volume Anomalies — which sender → recipient pair just "
                "spiked above the rolling baseline? (lands in K.4.4)",
                "Money Trail — where did this transfer originate and "
                "where does it go? (lands in K.4.5)",
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


def _build_stub_sheet(
    sheet_id: str, title: str, body: str, lands_in: str, accent: str,
) -> SheetDefinition:
    """Skeleton sheet — single text-box describing what's coming."""
    box_id = f"{sheet_id}-stub"
    box = SheetTextBox(
        SheetTextBoxId=box_id,
        Content=rt.text_box(
            rt.heading(title, color=accent),
            rt.BR,
            rt.BR,
            rt.body(body),
            rt.BR,
            rt.BR,
            rt.inline(f"Visuals land in {lands_in}.", color=accent),
        ),
    )
    return SheetDefinition(
        SheetId=sheet_id,
        Name=title,
        Title=title,
        Description=f"Skeleton sheet — full visuals land in {lands_in}.",
        ContentType="INTERACTIVE",
        TextBoxes=[box],
        Layouts=_grid_layout([_full_width_text(box_id, row_span=10)]),
    )


# ---------------------------------------------------------------------------
# Analysis / Dashboard
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """No datasets in the K.4.2 skeleton."""
    return []


def _build_definition(cfg: Config) -> AnalysisDefinition:
    accent = get_preset(cfg.theme_preset).accent
    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
        Sheets=[
            _build_getting_started_sheet(cfg),
            _build_stub_sheet(
                SHEET_INV_FANOUT, "Recipient Fanout",
                _FANOUT_BODY, "K.4.3", accent,
            ),
            _build_stub_sheet(
                SHEET_INV_ANOMALIES, "Volume Anomalies",
                _ANOMALY_BODY, "K.4.4", accent,
            ),
            _build_stub_sheet(
                SHEET_INV_MONEY_TRAIL, "Money Trail",
                _MONEY_TRAIL_BODY, "K.4.5", accent,
            ),
        ],
        FilterGroups=build_filter_groups(cfg),
        CalculatedFields=[],
        ParameterDeclarations=[],
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
