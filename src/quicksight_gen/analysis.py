"""QuickSight Analysis — sheets/tabs, visuals, filters, and top-level resource."""

from __future__ import annotations

from quicksight_gen.config import Config
from quicksight_gen.constants import (
    DS_MERCHANTS,
    DS_PAYMENT_RETURNS,
    DS_PAYMENTS,
    DS_SALES,
    DS_SETTLEMENT_EXCEPTIONS,
    DS_SETTLEMENTS,
    SHEET_EXCEPTIONS,
    SHEET_PAYMENTS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
)
from quicksight_gen.datasets import build_financial_datasets
from quicksight_gen.filters import (
    build_exceptions_controls,
    build_filter_groups,
    build_payments_controls,
    build_sales_controls,
    build_settlements_controls,
)
from quicksight_gen.models import (
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
)
from quicksight_gen.theme import get_preset
from quicksight_gen.visuals import (
    build_exceptions_visuals,
    build_payments_visuals,
    build_sales_visuals,
    build_settlements_visuals,
)

_ANALYSIS_ACTIONS = [
    "quicksight:DescribeAnalysis",
    "quicksight:DescribeAnalysisPermissions",
    "quicksight:UpdateAnalysis",
    "quicksight:UpdateAnalysisPermissions",
    "quicksight:DeleteAnalysis",
    "quicksight:QueryAnalysis",
    "quicksight:RestoreAnalysis",
]


# ---------------------------------------------------------------------------
# Layout helpers — QuickSight grid is 36 columns wide
# ---------------------------------------------------------------------------

_KPI_ROW_SPAN = 6
_CHART_ROW_SPAN = 12
_TABLE_ROW_SPAN = 18
_HALF = 18   # half of 36 columns
_FULL = 36


def _grid_layout(elements: list[GridLayoutElement]) -> list[Layout]:
    return [Layout(Configuration=LayoutConfiguration(
        GridLayout=GridLayoutConfiguration(Elements=elements),
    ))]


def _kpi_pair(id_left: str, id_right: str) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


def _chart_pair(id_left: str, id_right: str) -> list[GridLayoutElement]:
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


def _full_width(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType="VISUAL",
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _build_sales_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_SALES,
        Name="Sales Overview",
        Title="Sales Overview",
        Description=(
            "Shows total sales volume and dollar amounts. Use the filters above "
            "to narrow by date range, merchant, or location. The bar charts "
            "highlight which merchants and locations drive the most sales, and "
            "the detail table at the bottom lists individual transactions."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_sales_visuals(),
        FilterControls=build_sales_controls(),
        Layouts=_grid_layout(
            _kpi_pair("sales-kpi-count", "sales-kpi-amount")
            + _chart_pair("sales-bar-by-merchant", "sales-bar-by-location")
            + [_full_width("sales-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_settlements_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_SETTLEMENTS,
        Name="Settlements",
        Title="Settlements",
        Description=(
            "Shows how sales are bundled into settlements for each merchant. "
            "The KPIs show total settled amounts and pending counts. Use the "
            "settlement status filter to focus on specific statuses. The bar "
            "chart breaks down amounts by merchant type, and the detail table "
            "lists each settlement with its current status."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_settlements_visuals(),
        FilterControls=build_settlements_controls(),
        Layouts=_grid_layout(
            _kpi_pair("settlements-kpi-amount", "settlements-kpi-pending")
            + [_full_width("settlements-bar-by-type", _CHART_ROW_SPAN)]
            + [_full_width("settlements-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_payments_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_PAYMENTS,
        Name="Payments",
        Title="Payments",
        Description=(
            "Shows payments made to merchants from settlements. The KPIs show "
            "total paid amounts and how many payments were returned. The pie "
            "chart breaks down payment statuses, and the detail table includes "
            "return reasons for any returned payments."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_payments_visuals(),
        FilterControls=build_payments_controls(),
        Layouts=_grid_layout(
            _kpi_pair("payments-kpi-amount", "payments-kpi-returns")
            + [_full_width("payments-pie-status", _CHART_ROW_SPAN)]
            + [_full_width("payments-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_exceptions_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_EXCEPTIONS,
        Name="Exceptions & Alerts",
        Title="Exceptions & Alerts",
        Description=(
            "Highlights items that need attention: sales that have not been "
            "settled and payments that were returned. Use this tab to "
            "investigate overdue settlements and understand why payments "
            "were sent back."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_exceptions_visuals(),
        FilterControls=build_exceptions_controls(),
        Layouts=_grid_layout(
            _kpi_pair("exceptions-kpi-unsettled", "exceptions-kpi-returns")
            + [_full_width("exceptions-unsettled-table", _TABLE_ROW_SPAN)]
            + [_full_width("exceptions-returns-table", _TABLE_ROW_SPAN)]
        ),
    )


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical dataset identifiers to their ARNs."""
    datasets = build_financial_datasets(cfg)
    # Order matches build_financial_datasets: merchants, sales, settlements,
    # payments, settlement-exceptions, payment-returns
    identifier_names = [
        DS_MERCHANTS,
        DS_SALES,
        DS_SETTLEMENTS,
        DS_PAYMENTS,
        DS_SETTLEMENT_EXCEPTIONS,
        DS_PAYMENT_RETURNS,
    ]
    return [
        DataSetIdentifierDeclaration(
            Identifier=name,
            DataSetArn=cfg.dataset_arn(ds.DataSetId),
        )
        for name, ds in zip(identifier_names, datasets)
    ]


# ---------------------------------------------------------------------------
# Shared definition
# ---------------------------------------------------------------------------

def _build_financial_definition(cfg: Config) -> AnalysisDefinition:
    """Build the definition shared by both the analysis and dashboard."""
    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
        Sheets=[
            _build_sales_sheet(),
            _build_settlements_sheet(),
            _build_payments_sheet(),
            _build_exceptions_sheet(),
        ],
        FilterGroups=build_filter_groups(),
    )


def _financial_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Financial Reporting"
    return "Financial Reporting Analysis"


# ---------------------------------------------------------------------------
# Top-level analysis
# ---------------------------------------------------------------------------

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


def build_analysis(cfg: Config) -> Analysis:
    """Build the complete Analysis resource with four sheets and visuals."""
    analysis_id = cfg.prefixed("financial-analysis")
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arn:
        permissions = [
            ResourcePermission(
                Principal=cfg.principal_arn,
                Actions=_ANALYSIS_ACTIONS,
            )
        ]

    return Analysis(
        AwsAccountId=cfg.aws_account_id,
        AnalysisId=analysis_id,
        Name=_financial_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_financial_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
    )


def build_financial_dashboard(cfg: Config) -> Dashboard:
    """Build a published Dashboard from the financial analysis definition."""
    dashboard_id = cfg.prefixed("financial-dashboard")
    theme_id = cfg.prefixed("theme")

    permissions = None
    if cfg.principal_arn:
        permissions = [
            ResourcePermission(
                Principal=cfg.principal_arn,
                Actions=_DASHBOARD_ACTIONS,
            )
        ]

    return Dashboard(
        AwsAccountId=cfg.aws_account_id,
        DashboardId=dashboard_id,
        Name=_financial_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_financial_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
        VersionDescription="Generated by quicksight-gen",
        DashboardPublishOptions=DashboardPublishOptions(
            AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
            ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
            SheetControlsOption={"VisibilityState": "EXPANDED"},
        ),
    )
