"""QuickSight Analysis — sheets/tabs, visuals, filters, and top-level resource."""

from __future__ import annotations

from quicksight_gen.config import Config
from quicksight_gen.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_MERCHANTS,
    DS_PAYMENT_RECON,
    DS_PAYMENT_RETURNS,
    DS_PAYMENTS,
    DS_SALES,
    DS_SETTLEMENT_EXCEPTIONS,
    DS_SETTLEMENTS,
    SHEET_EXCEPTIONS,
    SHEET_PAYMENT_RECON,
    SHEET_PAYMENTS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
)
from quicksight_gen.datasets import build_financial_datasets, build_recon_datasets
from quicksight_gen.filters import (
    build_exceptions_controls,
    build_filter_groups,
    build_payments_controls,
    build_sales_controls,
    build_settlements_controls,
)
from quicksight_gen.recon_filters import build_recon_controls, build_recon_filter_groups
from quicksight_gen.models import (
    Analysis,
    AnalysisDefinition,
    CategoryFilter,
    CategoryFilterConfiguration,
    ColumnIdentifier,
    Dashboard,
    DashboardPublishOptions,
    DataSetIdentifierDeclaration,
    Filter,
    FilterGroup,
    FilterScopeConfiguration,
    GridLayoutConfiguration,
    GridLayoutElement,
    Layout,
    LayoutConfiguration,
    ParameterDeclaration,
    ResourcePermission,
    SelectedSheetsFilterScopeConfiguration,
    SheetDefinition,
    SheetVisualScopingConfiguration,
    StringParameterDeclaration,
)
from quicksight_gen.theme import get_preset
from quicksight_gen.recon_visuals import build_payment_recon_visuals
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
_THIRD = 12  # one-third of 36 columns
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


def _build_payment_recon_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_PAYMENT_RECON,
        Name="Payment Reconciliation",
        Title="Payment Reconciliation",
        Description=(
            "Compares internal payments against external system transactions. "
            "The top KPIs show matched and unmatched totals. The external "
            "transactions table shows each transaction with its match status — "
            "click a row to see which internal payments are linked. The payments "
            "table below shows the internal side — click a row to highlight its "
            "external transaction. Use the filters to narrow by date, status, "
            "or external system."
        ),
        ContentType="INTERACTIVE",
        Visuals=build_payment_recon_visuals(),
        FilterControls=build_recon_controls(),
        Layouts=_grid_layout([
            GridLayoutElement(
                ElementId="recon-kpi-matched-amount", ElementType="VISUAL",
                ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
            ),
            GridLayoutElement(
                ElementId="recon-kpi-unmatched-amount", ElementType="VISUAL",
                ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_THIRD,
            ),
            GridLayoutElement(
                ElementId="recon-kpi-late-count", ElementType="VISUAL",
                ColumnSpan=_THIRD, RowSpan=_KPI_ROW_SPAN, ColumnIndex=_THIRD * 2,
            ),
            _full_width("recon-bar-by-system", _CHART_ROW_SPAN),
            _full_width("recon-ext-txn-table", _TABLE_ROW_SPAN),
            _full_width("recon-payments-table", _TABLE_ROW_SPAN),
        ]),
    )


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical dataset identifiers to their ARNs."""
    financial_datasets = build_financial_datasets(cfg)
    financial_names = [
        DS_MERCHANTS,
        DS_SALES,
        DS_SETTLEMENTS,
        DS_PAYMENTS,
        DS_SETTLEMENT_EXCEPTIONS,
        DS_PAYMENT_RETURNS,
    ]

    recon_datasets = build_recon_datasets(cfg)
    recon_names = [
        DS_EXTERNAL_TRANSACTIONS,
        DS_PAYMENT_RECON,
    ]

    all_datasets = list(zip(financial_names, financial_datasets)) + list(
        zip(recon_names, recon_datasets)
    )
    return [
        DataSetIdentifierDeclaration(
            Identifier=name,
            DataSetArn=cfg.dataset_arn(ds.DataSetId),
        )
        for name, ds in all_datasets
    ]


# ---------------------------------------------------------------------------
# Shared definition
# ---------------------------------------------------------------------------

def _settlement_id_parameter() -> ParameterDeclaration:
    """Declare the pSettlementId parameter for drill-down navigation."""
    return ParameterDeclaration(
        StringParameterDeclaration=StringParameterDeclaration(
            ParameterValueType="SINGLE_VALUED",
            Name="pSettlementId",
            DefaultValues={"StaticValues": []},
        ),
    )


def _external_txn_id_parameter() -> ParameterDeclaration:
    """Declare the pExternalTransactionId parameter for recon drill-down."""
    return ParameterDeclaration(
        StringParameterDeclaration=StringParameterDeclaration(
            ParameterValueType="SINGLE_VALUED",
            Name="pExternalTransactionId",
            DefaultValues={"StaticValues": []},
        ),
    )


def _settlement_id_filter_group(
    filter_group_id: str,
    filter_id: str,
    ds_identifier: str,
    sheet_id: str,
) -> FilterGroup:
    """Build a filter group that filters settlement_id by the pSettlementId parameter."""
    return FilterGroup(
        FilterGroupId=filter_group_id,
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=FilterScopeConfiguration(
            SelectedSheets=SelectedSheetsFilterScopeConfiguration(
                SheetVisualScopingConfigurations=[
                    SheetVisualScopingConfiguration(
                        SheetId=sheet_id,
                        Scope="ALL_VISUALS",
                    ),
                ],
            ),
        ),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId=filter_id,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=ds_identifier,
                        ColumnName="settlement_id",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        CustomFilterConfiguration={
                            "MatchOperator": "EQUALS",
                            "ParameterName": "pSettlementId",
                            "NullOption": "ALL_VALUES",
                        },
                    ),
                ),
            ),
        ],
    )


def _ext_txn_id_filter_group(
    filter_group_id: str,
    filter_id: str,
    ds_identifier: str,
    column_name: str,
) -> FilterGroup:
    """Build a filter group that filters by the pExternalTransactionId parameter."""
    return FilterGroup(
        FilterGroupId=filter_group_id,
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=FilterScopeConfiguration(
            SelectedSheets=SelectedSheetsFilterScopeConfiguration(
                SheetVisualScopingConfigurations=[
                    SheetVisualScopingConfiguration(
                        SheetId=SHEET_PAYMENT_RECON,
                        Scope="ALL_VISUALS",
                    ),
                ],
            ),
        ),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId=filter_id,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=ds_identifier,
                        ColumnName=column_name,
                    ),
                    Configuration=CategoryFilterConfiguration(
                        CustomFilterConfiguration={
                            "MatchOperator": "EQUALS",
                            "ParameterName": "pExternalTransactionId",
                            "NullOption": "ALL_VALUES",
                        },
                    ),
                ),
            ),
        ],
    )


def _build_financial_definition(cfg: Config) -> AnalysisDefinition:
    """Build the definition shared by both the analysis and dashboard."""
    drill_down_filters = [
        _settlement_id_filter_group(
            "fg-drill-settlement-on-sales",
            "filter-drill-settlement-on-sales",
            DS_SALES,
            SHEET_SALES,
        ),
        _settlement_id_filter_group(
            "fg-drill-settlement-on-settlements",
            "filter-drill-settlement-on-settlements",
            DS_SETTLEMENTS,
            SHEET_SETTLEMENTS,
        ),
    ]

    recon_drill_down_filters = [
        _ext_txn_id_filter_group(
            "fg-drill-ext-txn-on-recon",
            "filter-drill-ext-txn-on-recon",
            DS_PAYMENT_RECON,
            "transaction_id",
        ),
        _ext_txn_id_filter_group(
            "fg-drill-ext-txn-on-payments",
            "filter-drill-ext-txn-on-payments",
            DS_PAYMENTS,
            "external_transaction_id",
        ),
    ]

    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
        Sheets=[
            _build_sales_sheet(),
            _build_settlements_sheet(),
            _build_payments_sheet(),
            _build_exceptions_sheet(),
            _build_payment_recon_sheet(),
        ],
        FilterGroups=(
            build_filter_groups()
            + drill_down_filters
            + build_recon_filter_groups()
            + recon_drill_down_filters
        ),
        ParameterDeclarations=[
            _settlement_id_parameter(),
            _external_txn_id_parameter(),
        ],
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
