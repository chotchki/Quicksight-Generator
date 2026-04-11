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
from quicksight_gen.datasets import build_all_datasets
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
    DataSetIdentifierDeclaration,
    ResourcePermission,
    SheetDefinition,
)
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
# Sheet builders
# ---------------------------------------------------------------------------

def _build_sales_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_SALES,
        Name="Sales Overview",
        Title="Sales Overview",
        Description="Sales volume and amounts across merchants and locations",
        ContentType="INTERACTIVE",
        Visuals=build_sales_visuals(),
        FilterControls=build_sales_controls(),
    )


def _build_settlements_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_SETTLEMENTS,
        Name="Settlements",
        Title="Settlements",
        Description="Settlement status, amounts, and breakdown by merchant type",
        ContentType="INTERACTIVE",
        Visuals=build_settlements_visuals(),
        FilterControls=build_settlements_controls(),
    )


def _build_payments_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_PAYMENTS,
        Name="Payments",
        Title="Payments",
        Description="Payment status, amounts, and returned payments",
        ContentType="INTERACTIVE",
        Visuals=build_payments_visuals(),
        FilterControls=build_payments_controls(),
    )


def _build_exceptions_sheet() -> SheetDefinition:
    return SheetDefinition(
        SheetId=SHEET_EXCEPTIONS,
        Name="Exceptions & Alerts",
        Title="Exceptions & Alerts",
        Description="Unsettled sales, returned payments, and anomalies",
        ContentType="INTERACTIVE",
        Visuals=build_exceptions_visuals(),
        FilterControls=build_exceptions_controls(),
    )


# ---------------------------------------------------------------------------
# Dataset identifier declarations
# ---------------------------------------------------------------------------

def _build_dataset_declarations(cfg: Config) -> list[DataSetIdentifierDeclaration]:
    """Map logical dataset identifiers to their ARNs."""
    datasets = build_all_datasets(cfg)
    # Order matches build_all_datasets: merchants, sales, settlements,
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
# Top-level analysis
# ---------------------------------------------------------------------------

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
        Name="Financial Reporting Analysis",
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=AnalysisDefinition(
            DataSetIdentifierDeclarations=_build_dataset_declarations(cfg),
            Sheets=[
                _build_sales_sheet(),
                _build_settlements_sheet(),
                _build_payments_sheet(),
                _build_exceptions_sheet(),
            ],
            FilterGroups=build_filter_groups(),
        ),
        Permissions=permissions,
    )
