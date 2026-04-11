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
    DataSetIdentifierDeclaration,
    ResourcePermission,
    SheetDefinition,
)
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
# Top-level analysis
# ---------------------------------------------------------------------------

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
        Name="Reconciliation Analysis",
        ThemeArn=cfg.theme_arn(theme_id),
        Definition=AnalysisDefinition(
            DataSetIdentifierDeclarations=_build_recon_dataset_declarations(cfg),
            Sheets=[
                _build_recon_overview_sheet(),
                _build_sales_recon_sheet(),
                _build_settlement_recon_sheet(),
                _build_payment_recon_sheet(),
            ],
            FilterGroups=build_recon_filter_groups(),
        ),
        Permissions=permissions,
        Tags=cfg.tags(),
    )
