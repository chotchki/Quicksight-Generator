"""Filter groups and controls for the Reconciliation analysis.

Defines six cross-visual filters with corresponding UI controls:
- Date range picker        -> all recon sheets
- Match status dropdown    -> all recon sheets
- Transaction type dropdown -> overview sheet
- External system dropdown -> all recon sheets
- Merchant dropdown        -> all recon sheets
- Days outstanding slider  -> all recon sheets
"""

from __future__ import annotations

from quicksight_gen.constants import (
    DS_RECON_EXCEPTIONS,
    DS_SALES_RECON,
    SHEET_PAYMENT_RECON,
    SHEET_RECON_OVERVIEW,
    SHEET_SALES_RECON,
    SHEET_SETTLEMENT_RECON,
)
from quicksight_gen.models import (
    CategoryFilter,
    CategoryFilterConfiguration,
    ColumnIdentifier,
    Filter,
    FilterControl,
    FilterDateTimePickerControl,
    FilterDropDownControl,
    FilterGroup,
    FilterScopeConfiguration,
    FilterSliderControl,
    NumericRangeFilter,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
    TimeRangeFilter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_RECON_SHEETS = [
    SHEET_RECON_OVERVIEW,
    SHEET_SALES_RECON,
    SHEET_SETTLEMENT_RECON,
    SHEET_PAYMENT_RECON,
]


def _selected_sheets_scope(sheet_ids: list[str]) -> FilterScopeConfiguration:
    return FilterScopeConfiguration(
        SelectedSheets=SelectedSheetsFilterScopeConfiguration(
            SheetVisualScopingConfigurations=[
                SheetVisualScopingConfiguration(
                    SheetId=sid,
                    Scope="ALL_VISUALS",
                )
                for sid in sheet_ids
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Filter groups
# ---------------------------------------------------------------------------

def _recon_date_range_filter_group() -> FilterGroup:
    """Date range filter on transaction_date — all recon sheets."""
    return FilterGroup(
        FilterGroupId="fg-recon-date-range",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_RECON_SHEETS),
        Status="ENABLED",
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId="filter-recon-date-range",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_SALES_RECON,
                        ColumnName="transaction_date",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    TimeGranularity="DAY",
                    IncludeMinimum=True,
                    IncludeMaximum=True,
                ),
            ),
        ],
    )


def _recon_match_status_filter_group() -> FilterGroup:
    """Match status dropdown — all recon sheets."""
    return FilterGroup(
        FilterGroupId="fg-recon-match-status",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_RECON_SHEETS),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-recon-match-status",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_RECON_EXCEPTIONS,
                        ColumnName="match_status",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                ),
            ),
        ],
    )


def _recon_transaction_type_filter_group() -> FilterGroup:
    """Transaction type dropdown — overview sheet only."""
    return FilterGroup(
        FilterGroupId="fg-recon-transaction-type",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_selected_sheets_scope([SHEET_RECON_OVERVIEW]),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-recon-transaction-type",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_RECON_EXCEPTIONS,
                        ColumnName="transaction_type",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                ),
            ),
        ],
    )


def _recon_external_system_filter_group() -> FilterGroup:
    """External system dropdown — all recon sheets."""
    return FilterGroup(
        FilterGroupId="fg-recon-external-system",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_RECON_SHEETS),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-recon-external-system",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_RECON_EXCEPTIONS,
                        ColumnName="external_system",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                ),
            ),
        ],
    )


def _recon_merchant_filter_group() -> FilterGroup:
    """Merchant dropdown — all recon sheets."""
    return FilterGroup(
        FilterGroupId="fg-recon-merchant",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_RECON_SHEETS),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-recon-merchant",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_RECON_EXCEPTIONS,
                        ColumnName="merchant_id",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                ),
            ),
        ],
    )


def _recon_days_outstanding_filter_group() -> FilterGroup:
    """Days outstanding numeric filter — all recon sheets.

    Lets users filter to items that are at least X days overdue.
    """
    return FilterGroup(
        FilterGroupId="fg-recon-days-outstanding",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_RECON_SHEETS),
        Status="ENABLED",
        Filters=[
            Filter(
                NumericRangeFilter=NumericRangeFilter(
                    FilterId="filter-recon-days-outstanding",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_RECON_EXCEPTIONS,
                        ColumnName="days_outstanding",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    IncludeMinimum=True,
                    IncludeMaximum=True,
                ),
            ),
        ],
    )


def build_recon_filter_groups() -> list[FilterGroup]:
    """Return all filter groups for the reconciliation analysis."""
    return [
        _recon_date_range_filter_group(),
        _recon_match_status_filter_group(),
        _recon_transaction_type_filter_group(),
        _recon_external_system_filter_group(),
        _recon_merchant_filter_group(),
        _recon_days_outstanding_filter_group(),
    ]


# ---------------------------------------------------------------------------
# Filter controls (UI widgets on sheets)
# ---------------------------------------------------------------------------

def _recon_date_range_control() -> FilterControl:
    return FilterControl(
        DateTimePicker=FilterDateTimePickerControl(
            FilterControlId="ctrl-recon-date-range",
            Title="Date Range",
            SourceFilterId="filter-recon-date-range",
            Type="DATE_RANGE",
        ),
    )


def _recon_match_status_control() -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId="ctrl-recon-match-status",
            Title="Match Status",
            SourceFilterId="filter-recon-match-status",
            Type="MULTI_SELECT",
        ),
    )


def _recon_transaction_type_control() -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId="ctrl-recon-transaction-type",
            Title="Transaction Type",
            SourceFilterId="filter-recon-transaction-type",
            Type="MULTI_SELECT",
        ),
    )


def _recon_external_system_control() -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId="ctrl-recon-external-system",
            Title="External System",
            SourceFilterId="filter-recon-external-system",
            Type="MULTI_SELECT",
        ),
    )


def _recon_merchant_control() -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId="ctrl-recon-merchant",
            Title="Merchant",
            SourceFilterId="filter-recon-merchant",
            Type="MULTI_SELECT",
        ),
    )


def _recon_days_outstanding_control() -> FilterControl:
    return FilterControl(
        Slider=FilterSliderControl(
            FilterControlId="ctrl-recon-days-outstanding",
            Title="Minimum Days Outstanding",
            SourceFilterId="filter-recon-days-outstanding",
            MinimumValue=0,
            MaximumValue=365,
            StepSize=1,
            Type="SINGLE_POINT",
        ),
    )


# ---------------------------------------------------------------------------
# Per-sheet control sets
# ---------------------------------------------------------------------------

def build_recon_overview_controls() -> list[FilterControl]:
    """Controls for the Reconciliation Overview tab."""
    return [
        _recon_date_range_control(),
        _recon_match_status_control(),
        _recon_transaction_type_control(),
        _recon_external_system_control(),
        _recon_merchant_control(),
        _recon_days_outstanding_control(),
    ]


def build_sales_recon_controls() -> list[FilterControl]:
    """Controls for the Sales Reconciliation tab."""
    return [
        _recon_date_range_control(),
        _recon_match_status_control(),
        _recon_external_system_control(),
        _recon_merchant_control(),
        _recon_days_outstanding_control(),
    ]


def build_settlement_recon_controls() -> list[FilterControl]:
    """Controls for the Settlement Reconciliation tab."""
    return [
        _recon_date_range_control(),
        _recon_match_status_control(),
        _recon_external_system_control(),
        _recon_merchant_control(),
        _recon_days_outstanding_control(),
    ]


def build_payment_recon_controls() -> list[FilterControl]:
    """Controls for the Payment Reconciliation tab."""
    return [
        _recon_date_range_control(),
        _recon_match_status_control(),
        _recon_external_system_control(),
        _recon_merchant_control(),
        _recon_days_outstanding_control(),
    ]
