"""QuickSight Reconciliation Analysis — matching internal records to external systems."""

from __future__ import annotations

from quicksight_gen.config import Config
from quicksight_gen.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_PAYMENT_RECON,
    DS_RECON_EXCEPTIONS,
    DS_SALES_RECON,
    DS_SETTLEMENT_RECON,
    SHEET_PAYMENT_RECON,
    SHEET_RECON_OVERVIEW,
    SHEET_SALES_RECON,
    SHEET_SETTLEMENT_RECON,
)
from quicksight_gen.datasets import build_recon_datasets
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
from quicksight_gen.recon_filters import (
    build_payment_recon_controls,
    build_recon_filter_groups,
    build_recon_overview_controls,
    build_sales_recon_controls,
    build_settlement_recon_controls,
)
from quicksight_gen.recon_visuals import (
    build_payment_recon_visuals,
    build_recon_overview_visuals,
    build_sales_recon_visuals,
    build_settlement_recon_visuals,
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
_THIRD = 12  # one-third of 36 columns
_HALF = 18
_FULL = 36


def _grid_layout(elements: list[GridLayoutElement]) -> list[Layout]:
    return [Layout(Configuration=LayoutConfiguration(
        GridLayout=GridLayoutConfiguration(Elements=elements),
    ))]


def _recon_type_layout(prefix: str) -> list[Layout]:
    """Standard layout for the per-type recon sheets (2 KPIs, bar, table)."""
    return _grid_layout([
        GridLayoutElement(
            ElementId=f"{prefix}-kpi-matched", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=f"{prefix}-kpi-unmatched", ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_HALF,
        ),
        GridLayoutElement(
            ElementId=f"{prefix}-bar-merchant", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_CHART_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=f"{prefix}-detail-table", ElementType="VISUAL",
            ColumnSpan=_FULL, RowSpan=_TABLE_ROW_SPAN, ColumnIndex=0,
        ),
    ])


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _build_recon_overview_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_RECON_OVERVIEW,
        Name="Reconciliation Overview",
        Title="Reconciliation Overview",
        Description=(
            "High-level view of how well internal records match external system "
            "totals. The KPIs at the top show matched, pending, and late counts. "
            "Use the charts below to see which transaction types or external "
            "systems have the most mismatches. Use the filters to narrow by date, "
            "status, or external system."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_recon_overview_visuals(),
        FilterControls=build_recon_overview_controls(),
        Layouts=_grid_layout([
            GridLayoutElement(
                ElementId="recon-kpi-matched", ElementType="VISUAL",
                ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
            ),
            GridLayoutElement(
                ElementId="recon-kpi-pending", ElementType="VISUAL",
                ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_THIRD,
            ),
            GridLayoutElement(
                ElementId="recon-kpi-late", ElementType="VISUAL",
                ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_THIRD * 2,
            ),
            GridLayoutElement(
                ElementId="recon-pie-status", ElementType="VISUAL",
                ColumnSpan=_FULL, RowSpan=_CHART_ROW_SPAN, ColumnIndex=0,
            ),
            GridLayoutElement(
                ElementId="recon-bar-by-type", ElementType="VISUAL",
                ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN, ColumnIndex=0,
            ),
            GridLayoutElement(
                ElementId="recon-bar-by-system", ElementType="VISUAL",
                ColumnSpan=_HALF, RowSpan=_CHART_ROW_SPAN, ColumnIndex=_HALF,
            ),
        ]),
    )


def _build_sales_recon_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_SALES_RECON,
        Name="Sales Reconciliation",
        Title="Sales Reconciliation",
        Description=(
            "Compares internal sales records against external system transaction "
            "totals. A match means the external amount exactly equals the sum of "
            "internal sales for that transaction. The detail table shows every "
            "transaction with its match status, difference, and how many days it "
            "has been outstanding. The 'Late Threshold' column shows when a "
            "pending item is considered late for this type."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_sales_recon_visuals(),
        FilterControls=build_sales_recon_controls(),
        Layouts=_recon_type_layout("sales-recon"),
    )


def _build_settlement_recon_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_SETTLEMENT_RECON,
        Name="Settlement Reconciliation",
        Title="Settlement Reconciliation",
        Description=(
            "Compares internal settlement records against external system "
            "transaction totals. A match means the external amount exactly equals "
            "the sum of internal settlements for that transaction. Use the 'Days "
            "Outstanding' slider to focus on the most overdue items."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_settlement_recon_visuals(),
        FilterControls=build_settlement_recon_controls(),
        Layouts=_recon_type_layout("settlement-recon"),
    )


def _build_payment_recon_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_PAYMENT_RECON,
        Name="Payment Reconciliation",
        Title="Payment Reconciliation",
        Description=(
            "Compares internal payment records against external system transaction "
            "totals. A match means the external amount exactly equals the sum of "
            "internal payments for that transaction. Late items have exceeded the "
            "payment-specific threshold shown in the detail table."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_payment_recon_visuals(),
        FilterControls=build_payment_recon_controls(),
        Layouts=_recon_type_layout("payment-recon"),
    )


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_recon_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical dataset identifiers to their ARNs."""
    datasets = build_recon_datasets(cfg)
    # Order matches build_recon_datasets: external-transactions, sales-recon,
    # settlement-recon, payment-recon, recon-exceptions
    identifier_names = [
        DS_EXTERNAL_TRANSACTIONS,
        DS_SALES_RECON,
        DS_SETTLEMENT_RECON,
        DS_PAYMENT_RECON,
        DS_RECON_EXCEPTIONS,
    ]
    return [
        DataSetIdentifierDeclaration(
            Identifier=name,
            DataSetArn=cfg.dataset_arn(ds.DataSetId),
        )
        for name, ds in zip(identifier_names, datasets)
    ]


# ---------------------------------------------------------------------------
# Shared definition and name
# ---------------------------------------------------------------------------

def _build_recon_definition(cfg: Config) -> AnalysisDefinition:
    """Build the definition shared by both the analysis and dashboard."""
    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_recon_dataset_declarations(cfg),
        Sheets=[
            _build_recon_overview_sheet(),
            _build_sales_recon_sheet(),
            _build_settlement_recon_sheet(),
            _build_payment_recon_sheet(),
        ],
        FilterGroups=build_recon_filter_groups(),
    )


def _recon_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Reconciliation"
    return "Reconciliation Analysis"


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


def build_recon_analysis(cfg: Config) -> Analysis:
    """Build the Reconciliation Analysis with four sheets."""
    analysis_id = cfg.prefixed("reconciliation-analysis")
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
        Name=_recon_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_recon_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
    )


def build_recon_dashboard(cfg: Config) -> Dashboard:
    """Build a published Dashboard from the reconciliation analysis definition."""
    dashboard_id = cfg.prefixed("reconciliation-dashboard")
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
        Name=_recon_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_recon_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
        VersionDescription="Generated by quicksight-gen",
        DashboardPublishOptions=DashboardPublishOptions(
            AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
            ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
            SheetControlsOption={"VisibilityState": "EXPANDED"},
        ),
    )
