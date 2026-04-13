"""QuickSight Analysis + Dashboard for Account Recon.

Phase 3 layout is intentionally simple: one Getting Started tab +
Balances / Transfers / Transactions / Exceptions. A single shared
date-range filter is the only interaction — drill-downs and the
account/parent multi-selects land in Phase 4.
"""

from __future__ import annotations

from xml.sax.saxutils import escape as _xml_escape

from quicksight_gen.account_recon.constants import (
    DS_AR_ACCOUNT_BALANCE_DRIFT,
    DS_AR_ACCOUNTS,
    DS_AR_NON_ZERO_TRANSFERS,
    DS_AR_PARENT_ACCOUNTS,
    DS_AR_PARENT_BALANCE_DRIFT,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    SHEET_AR_BALANCES,
    SHEET_AR_EXCEPTIONS,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.account_recon.datasets import build_all_datasets
from quicksight_gen.account_recon.filters import (
    build_balances_controls,
    build_exceptions_controls,
    build_filter_groups,
    build_transactions_controls,
    build_transfers_controls,
)
from quicksight_gen.account_recon.visuals import (
    build_balances_visuals,
    build_exceptions_visuals,
    build_transactions_visuals,
    build_transfers_visuals,
)
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


# ---------------------------------------------------------------------------
# Layout helpers — QuickSight grid is 36 columns wide
# ---------------------------------------------------------------------------

_KPI_ROW_SPAN = 6
_CHART_ROW_SPAN = 12
_TABLE_ROW_SPAN = 18
_HALF = 18
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


def _full_width_visual(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType="VISUAL",
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


def _full_width_text(element_id: str, row_span: int) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType="TEXT_BOX",
        ColumnSpan=_FULL, RowSpan=row_span,
        ColumnIndex=0,
    )


def _half_width_text(
    element_id: str, row_span: int, column_index: int,
) -> GridLayoutElement:
    return GridLayoutElement(
        ElementId=element_id, ElementType="TEXT_BOX",
        ColumnSpan=_HALF, RowSpan=row_span,
        ColumnIndex=column_index,
    )


# ---------------------------------------------------------------------------
# Sheet descriptions (shared with the Getting Started sheet)
# ---------------------------------------------------------------------------

_BALANCES_DESCRIPTION = (
    "Stored daily balances at both levels. Parent table compares stored "
    "parent balance to the sum of its children's stored balances; child "
    "table compares each child's stored balance to the running sum of "
    "posted transactions. Drift rows bubble up on the Exceptions tab."
)

_TRANSFERS_DESCRIPTION = (
    "Every transfer represented as a group of transactions sharing a "
    "transfer_id. Healthy transfers net to zero across non-failed legs; "
    "non-zero transfers indicate a keying error or a failed counter-leg."
)

_TRANSACTIONS_DESCRIPTION = (
    "Raw transaction ledger — one row per leg. Filter by date to narrow "
    "the window. Failed rows (status = failed) are the ones that never "
    "moved money and feed the non-zero transfer cases on Exceptions."
)

_EXCEPTIONS_DESCRIPTION = (
    "Three independent reconciliation problems side by side. Parent drift "
    "is stored parent vs Σ children's stored balances — fingers the "
    "parent-balance upstream feed. Child drift is stored child vs Σ "
    "posted transactions — fingers the child-balance feed or the ledger. "
    "Non-zero transfers are per-transfer imbalances. The timeline shows "
    "when child-level drift spiked."
)

_DEMO_SCENARIO_FLAVOR = (
    "<text-box>"
    "Demo scenario — Farmers Exchange Bank. Five parent accounts "
    "(Big Meadow Checking, Harvest Moon Savings, Orchard Lending Pool, "
    "Valley Grain Co-op, and Harvest Credit Exchange) move money between "
    "ten child accounts over a ~40 day window. A handful of transfers have "
    "a failed leg, another handful are keyed off by a few dollars. "
    "Parent and child stored balances are seeded independently — three "
    "parent-day cells and four child-day cells carry planted drift so "
    "each Exceptions table surfaces different rows."
    "<br/><br/>"
    "Data is deterministic — anchor date is the day the seed was generated. "
    "Explore the date-range filter to see how each tab responds."
    "</text-box>"
)


# ---------------------------------------------------------------------------
# Text boxes
# ---------------------------------------------------------------------------

def _text_box(box_id: str, title: str, body: str) -> SheetTextBox:
    return SheetTextBox(
        SheetTextBoxId=box_id,
        Content=(
            f"<text-box>{_xml_escape(title)}<br/><br/>"
            f"{_xml_escape(body)}</text-box>"
        ),
    )


# ---------------------------------------------------------------------------
# Getting Started sheet
# ---------------------------------------------------------------------------

def _build_getting_started_sheet(cfg: Config) -> SheetDefinition:
    is_demo = cfg.demo_database_url is not None

    welcome_box = SheetTextBox(
        SheetTextBoxId="ar-gs-welcome",
        Content=(
            "<text-box>"
            "Account Reconciliation Dashboard"
            "<br/><br/>"
            "This dashboard reconciles stored daily balances at both the "
            "parent- and child-account levels against their respective "
            "computations, plus transfer-level transactions for a bank's "
            "double-entry ledger. Use the tabs above to walk from aggregate "
            "balances down to individual transactions; the Exceptions tab "
            "pulls the problems together in one place."
            "</text-box>"
        ),
    )

    text_boxes: list[SheetTextBox] = [welcome_box]
    layout: list[GridLayoutElement] = [_full_width_text("ar-gs-welcome", 4)]

    if is_demo:
        text_boxes.append(SheetTextBox(
            SheetTextBoxId="ar-gs-demo-flavor",
            Content=_DEMO_SCENARIO_FLAVOR,
        ))
        layout.append(_full_width_text("ar-gs-demo-flavor", 6))

    sheet_blocks = [
        ("ar-gs-balances", "Balances", _BALANCES_DESCRIPTION),
        ("ar-gs-transfers", "Transfers", _TRANSFERS_DESCRIPTION),
        ("ar-gs-transactions", "Transactions", _TRANSACTIONS_DESCRIPTION),
        ("ar-gs-exceptions", "Exceptions", _EXCEPTIONS_DESCRIPTION),
    ]
    for i, (box_id, title, body) in enumerate(sheet_blocks):
        text_boxes.append(_text_box(box_id, title, body))
        col_index = 0 if i % 2 == 0 else _HALF
        layout.append(_half_width_text(box_id, row_span=5, column_index=col_index))

    return SheetDefinition(
        SheetId=SHEET_AR_GETTING_STARTED,
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


# ---------------------------------------------------------------------------
# Tab sheets
# ---------------------------------------------------------------------------

def _build_balances_sheet(cfg: Config) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_AR_BALANCES,
        Name="Balances",
        Title="Balances",
        Description=_BALANCES_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_balances_visuals(),
        FilterControls=build_balances_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("ar-balances-kpi-parents", "ar-balances-kpi-accounts")
            + [_full_width_visual("ar-balances-parent-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-balances-child-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_transfers_sheet(cfg: Config) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_AR_TRANSFERS,
        Name="Transfers",
        Title="Transfers",
        Description=_TRANSFERS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_transfers_visuals(),
        FilterControls=build_transfers_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("ar-transfers-kpi-count", "ar-transfers-kpi-unhealthy")
            + [_full_width_visual("ar-transfers-summary-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_transactions_sheet(cfg: Config) -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_AR_TRANSACTIONS,
        Name="Transactions",
        Title="Transactions",
        Description=_TRANSACTIONS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_transactions_visuals(),
        FilterControls=build_transactions_controls(cfg),
        Layouts=_grid_layout(
            _kpi_pair("ar-txn-kpi-count", "ar-txn-kpi-failed")
            + [_full_width_visual("ar-txn-bar-by-status", _CHART_ROW_SPAN)]
            + [_full_width_visual("ar-txn-detail-table", _TABLE_ROW_SPAN)]
        ),
    )


def _build_exceptions_sheet(cfg: Config) -> SheetDefinition:
    third = _FULL // 3  # 12-wide columns for the 3 KPI row
    kpi_row = [
        GridLayoutElement(
            ElementId="ar-exc-kpi-parent-drift", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=0,
        ),
        GridLayoutElement(
            ElementId="ar-exc-kpi-child-drift", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third,
        ),
        GridLayoutElement(
            ElementId="ar-exc-kpi-nonzero", ElementType="VISUAL",
            ColumnSpan=third, RowSpan=_KPI_ROW_SPAN, ColumnIndex=third * 2,
        ),
    ]
    return SheetDefinition(
        SheetId=SHEET_AR_EXCEPTIONS,
        Name="Exceptions",
        Title="Exceptions",
        Description=_EXCEPTIONS_DESCRIPTION,
        ContentType="INTERACTIVE",
        Visuals=build_exceptions_visuals(),
        FilterControls=build_exceptions_controls(cfg),
        Layouts=_grid_layout(
            kpi_row
            + [_full_width_visual("ar-exc-parent-drift-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-exc-child-drift-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-exc-nonzero-table", _TABLE_ROW_SPAN)]
            + [_full_width_visual("ar-exc-drift-timeline", _CHART_ROW_SPAN)]
        ),
    )


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical AR dataset identifiers to their ARNs.

    Order must match ``build_all_datasets`` so each ARN lines up with
    the intended logical identifier.
    """
    datasets = build_all_datasets(cfg)
    names = [
        DS_AR_PARENT_ACCOUNTS,
        DS_AR_ACCOUNTS,
        DS_AR_TRANSACTIONS,
        DS_AR_PARENT_BALANCE_DRIFT,
        DS_AR_ACCOUNT_BALANCE_DRIFT,
        DS_AR_TRANSFER_SUMMARY,
        DS_AR_NON_ZERO_TRANSFERS,
    ]
    return [
        DataSetIdentifierDeclaration(
            Identifier=name,
            DataSetArn=cfg.dataset_arn(ds.DataSetId),
        )
        for name, ds in zip(names, datasets)
    ]


# ---------------------------------------------------------------------------
# Top-level definition / Analysis / Dashboard
# ---------------------------------------------------------------------------

def _build_definition(cfg: Config) -> AnalysisDefinition:
    return AnalysisDefinition(
        DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
        Sheets=[
            _build_getting_started_sheet(cfg),
            _build_balances_sheet(cfg),
            _build_transfers_sheet(cfg),
            _build_transactions_sheet(cfg),
            _build_exceptions_sheet(cfg),
        ],
        FilterGroups=build_filter_groups(cfg),
    )


def _analysis_name(cfg: Config) -> str:
    preset = get_preset(cfg.theme_preset)
    if preset.analysis_name_prefix:
        return f"{preset.analysis_name_prefix} — Account Reconciliation"
    return "Account Reconciliation"


def build_analysis(cfg: Config) -> Analysis:
    """Build the complete Account Recon Analysis resource."""
    analysis_id = cfg.prefixed("account-recon-analysis")
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


def build_account_recon_dashboard(cfg: Config) -> Dashboard:
    """Build the Account Recon published Dashboard."""
    dashboard_id = cfg.prefixed("account-recon-dashboard")
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
