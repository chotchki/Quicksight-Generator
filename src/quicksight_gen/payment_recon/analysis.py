"""QuickSight Analysis — sheets/tabs, visuals, filters, and top-level resource."""

from __future__ import annotations

from xml.sax.saxutils import escape as _xml_escape

from quicksight_gen.common.config import Config
from quicksight_gen.payment_recon.constants import (
    DS_EXTERNAL_TRANSACTIONS,
    DS_MERCHANTS,
    DS_PAYMENT_RECON,
    DS_PAYMENT_RETURNS,
    DS_PAYMENTS,
    DS_SALE_SETTLEMENT_MISMATCH,
    DS_SALES,
    DS_SETTLEMENT_EXCEPTIONS,
    DS_SETTLEMENT_PAYMENT_MISMATCH,
    DS_SETTLEMENTS,
    DS_UNMATCHED_EXTERNAL_TXNS,
    SHEET_EXCEPTIONS,
    SHEET_GETTING_STARTED,
    SHEET_PAYMENT_RECON,
    SHEET_PAYMENTS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
)
from quicksight_gen.payment_recon.datasets import build_pipeline_datasets, build_recon_datasets
from quicksight_gen.payment_recon.filters import (
    build_exceptions_controls,
    build_filter_groups,
    build_payments_controls,
    build_sales_controls,
    build_settlements_controls,
)
from quicksight_gen.payment_recon.recon_filters import build_recon_controls, build_recon_filter_groups
from quicksight_gen.common.models import (
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
    SheetTextBox,
    SheetVisualScopingConfiguration,
    StringParameterDeclaration,
)
from quicksight_gen.common.theme import get_preset
from quicksight_gen.payment_recon.recon_visuals import build_payment_recon_visuals
from quicksight_gen.payment_recon.visuals import (
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
# Sheet descriptions (shared with the Getting Started sheet per SPEC 2.6)
# ---------------------------------------------------------------------------

_SALES_DESCRIPTION = (
    "Shows total sales volume and dollar amounts. Use the filters above "
    "to narrow by date range, merchant, or location. The bar charts "
    "highlight which merchants and locations drive the most sales, and "
    "the detail table at the bottom lists individual transactions."
)

_SETTLEMENTS_DESCRIPTION = (
    "Shows how sales are bundled into settlements for each merchant. "
    "The KPIs show total settled amounts and pending counts. Use the "
    "settlement status filter to focus on specific statuses. The bar "
    "chart breaks down amounts by merchant type, and the detail table "
    "lists each settlement with its current status."
)

_PAYMENTS_DESCRIPTION = (
    "Shows payments made to merchants from settlements. The KPIs show "
    "total paid amounts and how many payments were returned. The pie "
    "chart breaks down payment statuses, and the detail table includes "
    "return reasons for any returned payments."
)

_EXCEPTIONS_DESCRIPTION = (
    "Highlights items that need attention: sales that have not been "
    "settled and payments that were returned. Use this tab to "
    "investigate overdue settlements and understand why payments "
    "were sent back. Layout is compact — half-width tables side-by-side "
    "so all exception categories are visible without scrolling."
)

_PAYMENT_RECON_DESCRIPTION = (
    "Compares internal payments against external system transactions. "
    "The top KPIs show matched and unmatched totals. External transactions "
    "and internal payments are shown side-by-side — click a row in either "
    "table to filter the other. Use the filters to narrow by date, status, "
    "or external system."
)

_DEMO_SCENARIO_FLAVOR = (
    "<text-box>"
    "Demo scenario — Sasquatch National Bank. The data "
    "in this dashboard is seeded from six fictional Seattle coffee shops "
    "(Bigfoot Brews, Sasquatch Sips, Yeti Espresso, Skookum Coffee Co., "
    "Cryptid Coffee Cart, and Wildman's Roastery). Sales flow into settlements "
    "which pay out to the merchants; some settlements are intentionally left "
    "unsettled, a handful of payments are returned, and a few amounts are "
    "nudged off to populate the Exceptions tab."
    "<br/><br/>"
    "Anchor date for relative timestamps is the day the seed was generated. "
    "Explore the filters and drill-downs — everything you see here was produced "
    "deterministically from the demo_data.py generator."
    "</text-box>"
)


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _text_box_element(
    box_id: str, row_span: int, column_span: int = _FULL, column_index: int = 0,
) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=box_id, ElementType="TEXT_BOX",
        ColumnSpan=column_span, RowSpan=row_span,
        ColumnIndex=column_index,
    )


def _text_box(box_id: str, title: str, body: str) -> SheetTextBox:
    """QuickSight's text-box parser requires a single ``<text-box>`` root and
    XML-escaped entity references. Canonical format confirmed by round-tripping
    a UI-authored text box via ``describe-analysis-definition``.
    """
    return SheetTextBox(
        SheetTextBoxId=box_id,
        Content=(
            f"<text-box>{_xml_escape(title)}<br/><br/>"
            f"{_xml_escape(body)}</text-box>"
        ),
    )


def _build_getting_started_sheet(cfg: Config) -> SheetDefinition:
    """Landing tab that auto-derives a description block per downstream sheet."""
    is_demo = cfg.demo_database_url is not None

    welcome_html = (
        "<text-box>"
        "Payment Reconciliation Dashboard"
        "<br/><br/>"
        "This dashboard helps you track sales, settlements, and payments "
        "through the full reconciliation lifecycle. Use the tabs above to "
        "explore each stage — the blocks below summarise what each tab covers."
        "</text-box>"
    )
    welcome_box = SheetTextBox(
        SheetTextBoxId="gs-welcome",
        Content=welcome_html,
    )

    legend_html = (
        "<text-box>"
        "Clickable cells"
        "<br/><br/>"
        "Cells rendered in the theme accent color are interactive. "
        "Plain accent-colored text means left-click drills to a related "
        "tab or filters this view. Accent text with a pale tinted "
        "background means a right-click menu is available — use it to "
        "drill to a secondary related tab without losing the left-click "
        "drill on the primary id."
        "</text-box>"
    )
    legend_box = SheetTextBox(
        SheetTextBoxId="gs-clickability-legend",
        Content=legend_html,
    )

    text_boxes: list[SheetTextBox] = [welcome_box, legend_box]
    layout: list[GridLayoutElement] = [
        _text_box_element("gs-welcome", 4),
        _text_box_element("gs-clickability-legend", 4),
    ]

    if is_demo:
        text_boxes.append(SheetTextBox(
            SheetTextBoxId="gs-demo-flavor",
            Content=_DEMO_SCENARIO_FLAVOR,
        ))
        layout.append(_text_box_element("gs-demo-flavor", 6))

    sheet_blocks = [
        ("gs-sales", "Sales Overview", _SALES_DESCRIPTION),
        ("gs-settlements", "Settlements", _SETTLEMENTS_DESCRIPTION),
        ("gs-payments", "Payments", _PAYMENTS_DESCRIPTION),
        ("gs-exceptions", "Exceptions & Alerts", _EXCEPTIONS_DESCRIPTION),
        ("gs-payment-recon", "Payment Reconciliation", _PAYMENT_RECON_DESCRIPTION),
    ]

    for i, (box_id, title, body) in enumerate(sheet_blocks):
        text_boxes.append(_text_box(box_id, title, body))
        col_index = 0 if i % 2 == 0 else _HALF
        layout.append(_text_box_element(
            box_id, row_span=5, column_span=_HALF, column_index=col_index,
        ))

    return SheetDefinition(
        SheetId=SHEET_GETTING_STARTED,
        Name="Getting Started",
        Title="Getting Started",
        Description=(
            "Landing page — summarises each tab in this dashboard so readers "
            "know where to look first. No filters or visuals."
        ),
        ContentType="INTERACTIVE",
        TextBoxes=text_boxes,
        Layouts=_grid_layout(layout),
    )


def _build_sales_sheet(cfg: Config) -> SheetDefinition:
    preset = get_preset(cfg.theme_preset)
    return SheetDefinition(
        SheetId=SHEET_SALES,
        Name="Sales Overview",
        Title="Sales Overview",
        Description=_SALES_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_sales_visuals(preset.accent, preset.link_tint),
        FilterControls=build_sales_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("sales-kpi-count", "sales-kpi-amount")
            + _chart_pair("sales-bar-by-merchant", "sales-bar-by-location")
            + [_full_width("sales-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_settlements_sheet(cfg: Config) -> SheetDefinition:
    preset = get_preset(cfg.theme_preset)
    return SheetDefinition(
        SheetId=SHEET_SETTLEMENTS,
        Name="Settlements",
        Title="Settlements",
        Description=_SETTLEMENTS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_settlements_visuals(preset.accent, preset.link_tint),
        FilterControls=build_settlements_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("settlements-kpi-amount", "settlements-kpi-pending")
            + [_full_width("settlements-bar-by-type", _CHART_ROW_SPAN)]
            + [_full_width("settlements-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_payments_sheet(cfg: Config) -> SheetDefinition:
    preset = get_preset(cfg.theme_preset)
    return SheetDefinition(
        SheetId=SHEET_PAYMENTS,
        Name="Payments",
        Title="Payments",
        Description=_PAYMENTS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_payments_visuals(preset.accent, preset.link_tint),
        FilterControls=build_payments_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("payments-kpi-amount", "payments-kpi-returns")
            + [_full_width("payments-pie-status", _CHART_ROW_SPAN)]
            + [_full_width("payments-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_exceptions_sheet(cfg: Config) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_EXCEPTIONS,
        Name="Exceptions & Alerts",
        Title="Exceptions & Alerts",
        Description=_EXCEPTIONS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_exceptions_visuals(),
        FilterControls=build_exceptions_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("exceptions-kpi-unsettled", "exceptions-kpi-returns")
            + _chart_pair(
                "exceptions-unsettled-table",
                "exceptions-returns-table",
            )
            + _chart_pair(
                "exceptions-sale-settlement-mismatch-table",
                "exceptions-settlement-payment-mismatch-table",
            )
            + [_full_width(
                "exceptions-unmatched-ext-txn-table",
                _CHART_ROW_SPAN,
            )]
        ),
    )


def _build_payment_recon_sheet(cfg: Config) -> SheetDefinition:
    link_color = get_preset(cfg.theme_preset).accent
    return SheetDefinition(
        SheetId=SHEET_PAYMENT_RECON,
        Name="Payment Reconciliation",
        Title="Payment Reconciliation",
        Description=_PAYMENT_RECON_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_payment_recon_visuals(link_color),
        FilterControls=build_recon_controls(cfg),
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
        ] + _chart_pair_of_tables(
            "recon-ext-txn-table",
            "recon-payments-table",
        )),
    )


def _chart_pair_of_tables(id_left: str, id_right: str) -> list[GridLayoutElement]:
    """Side-by-side table pair — taller row span than the chart pair so the
    tables surface more rows without scrolling."""
    return [
        GridLayoutElement(
            ElementId=id_left, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_TABLE_ROW_SPAN,
            ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId=id_right, ElementType="VISUAL",
            ColumnSpan=_HALF, RowSpan=_TABLE_ROW_SPAN,
            ColumnIndex=_HALF,
        ),
    ]


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical dataset identifiers to their ARNs.

    Order must match ``build_pipeline_datasets`` / ``build_recon_datasets``.
    """
    pipeline_datasets = build_pipeline_datasets(cfg)
    pipeline_names = [
        DS_MERCHANTS,
        DS_SALES,
        DS_SETTLEMENTS,
        DS_PAYMENTS,
        DS_SETTLEMENT_EXCEPTIONS,
        DS_PAYMENT_RETURNS,
        DS_SALE_SETTLEMENT_MISMATCH,
        DS_SETTLEMENT_PAYMENT_MISMATCH,
        DS_UNMATCHED_EXTERNAL_TXNS,
    ]

    recon_datasets = build_recon_datasets(cfg)
    recon_names = [
        DS_EXTERNAL_TRANSACTIONS,
        DS_PAYMENT_RECON,
    ]

    all_datasets = list(zip(pipeline_names, pipeline_datasets)) + list(
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


def _payment_id_parameter() -> ParameterDeclaration:
    """Declare the pPaymentId parameter — set by the Settlement Detail
    payment_id right-click menu to drill into the Payments sheet."""
    return ParameterDeclaration(
        StringParameterDeclaration=StringParameterDeclaration(
            ParameterValueType="SINGLE_VALUED",
            Name="pPaymentId",
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


def _payment_id_filter_group(
    filter_group_id: str,
    filter_id: str,
    ds_identifier: str,
    sheet_id: str,
) -> FilterGroup:
    """Filter Payments-sheet visuals to the pPaymentId parameter."""
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
                        ColumnName="payment_id",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        CustomFilterConfiguration={
                            "MatchOperator": "EQUALS",
                            "ParameterName": "pPaymentId",
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


def _build_payment_recon_definition(cfg: Config) -> AnalysisDefinition:
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
        _payment_id_filter_group(
            "fg-drill-payment-on-payments",
            "filter-drill-payment-on-payments",
            DS_PAYMENTS,
            SHEET_PAYMENTS,
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
            _build_getting_started_sheet(cfg),
            _build_sales_sheet(cfg),
            _build_settlements_sheet(cfg),
            _build_payments_sheet(cfg),
            _build_exceptions_sheet(cfg),
            _build_payment_recon_sheet(cfg),
        ],
        FilterGroups=(
            build_filter_groups(cfg)
            + drill_down_filters
            + build_recon_filter_groups(cfg)
            + recon_drill_down_filters
        ),
        ParameterDeclarations=[
            _settlement_id_parameter(),
            _payment_id_parameter(),
            _external_txn_id_parameter(),
        ],
    )


def _payment_recon_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Payment Reconciliation"
    return "Payment Reconciliation"


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
    analysis_id = cfg.prefixed("payment-recon-analysis")
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
        Name=_payment_recon_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_payment_recon_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
    )


def build_payment_recon_dashboard(cfg: Config) -> Dashboard:
    """Build a published Dashboard from the payment recon analysis definition."""
    dashboard_id = cfg.prefixed("payment-recon-dashboard")
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
        Name=_payment_recon_name(cfg),
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=_build_payment_recon_definition(cfg),
        Permissions=permissions,
        Tags=cfg.tags(),
        VersionDescription="Generated by quicksight-gen",
        DashboardPublishOptions=DashboardPublishOptions(
            AdHocFilteringOption={"AvailabilityStatus": "ENABLED"},
            ExportToCSVOption={"AvailabilityStatus": "ENABLED"},
            SheetControlsOption={"VisibilityState": "EXPANDED"},
        ),
    )
