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
    DefaultDateTimePickerControlOptions,
    DefaultDropdownControlOptions,
    DefaultFilterControlConfiguration,
    DefaultFilterControlOptions,
    Filter,
    FilterControl,
    FilterCrossSheetControl,
    FilterDropDownControl,
    FilterGroup,
    FilterScopeConfiguration,
    FilterSliderControl,
    NumericRangeFilter,
    NumericRangeFilterValue,
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
    """Date range filter on transaction_date -- all recon sheets."""
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
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="Date Range",
                        ControlOptions=DefaultFilterControlOptions(
                            DefaultDateTimePickerOptions=DefaultDateTimePickerControlOptions(
                                Type="DATE_RANGE",
                            ),
                        ),
                    ),
                ),
            ),
        ],
    )


def _recon_match_status_filter_group() -> FilterGroup:
    """Match status dropdown -- all recon sheets."""
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
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="Match Status",
                        ControlOptions=DefaultFilterControlOptions(
                            DefaultDropdownOptions=DefaultDropdownControlOptions(
                                Type="MULTI_SELECT",
                            ),
                        ),
                    ),
                ),
            ),
        ],
    )


def _recon_transaction_type_filter_group() -> FilterGroup:
    """Transaction type dropdown -- overview sheet only."""
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
    """External system dropdown -- all recon sheets."""
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
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="External System",
                        ControlOptions=DefaultFilterControlOptions(
                            DefaultDropdownOptions=DefaultDropdownControlOptions(
                                Type="MULTI_SELECT",
                            ),
                        ),
                    ),
                ),
            ),
        ],
    )


def _recon_merchant_filter_group() -> FilterGroup:
    """Merchant dropdown -- all recon sheets."""
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
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="Merchant",
                        ControlOptions=DefaultFilterControlOptions(
                            DefaultDropdownOptions=DefaultDropdownControlOptions(
                                Type="MULTI_SELECT",
                            ),
                        ),
                    ),
                ),
            ),
        ],
    )


def _recon_days_outstanding_filter_group(sheet_id: str, suffix: str) -> FilterGroup:
    """Days outstanding numeric filter -- scoped to a single sheet.

    One filter group per sheet avoids the need for DefaultFilterControlConfiguration
    on NumericRangeFilter (which QuickSight doesn't fully support for cross-sheet).
    """
    return FilterGroup(
        FilterGroupId=f"fg-recon-days-outstanding-{suffix}",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope([sheet_id]),
        Status="ENABLED",
        Filters=[
            Filter(
                NumericRangeFilter=NumericRangeFilter(
                    FilterId=f"filter-recon-days-outstanding-{suffix}",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_RECON_EXCEPTIONS,
                        ColumnName="days_outstanding",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    RangeMinimum=NumericRangeFilterValue(StaticValue=0),
                    RangeMaximum=NumericRangeFilterValue(StaticValue=365),
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
        _recon_days_outstanding_filter_group(SHEET_RECON_OVERVIEW, "overview"),
        _recon_days_outstanding_filter_group(SHEET_SALES_RECON, "sales"),
        _recon_days_outstanding_filter_group(SHEET_SETTLEMENT_RECON, "settlement"),
        _recon_days_outstanding_filter_group(SHEET_PAYMENT_RECON, "payment"),
    ]


# ---------------------------------------------------------------------------
# Filter controls (UI widgets on sheets)
#
# Control IDs must be globally unique across all sheets in an analysis.
# Each builder takes a sheet prefix to ensure uniqueness.
# ---------------------------------------------------------------------------

def _recon_date_range_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-date-range",
            SourceFilterId="filter-recon-date-range",
        ),
    )


def _recon_match_status_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-match-status",
            SourceFilterId="filter-recon-match-status",
        ),
    )


def _recon_transaction_type_control(sheet: str) -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId=f"ctrl-{sheet}-transaction-type",
            Title="Transaction Type",
            SourceFilterId="filter-recon-transaction-type",
            Type="MULTI_SELECT",
        ),
    )


def _recon_external_system_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-external-system",
            SourceFilterId="filter-recon-external-system",
        ),
    )


def _recon_merchant_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-merchant",
            SourceFilterId="filter-recon-merchant",
        ),
    )


def _recon_days_outstanding_control(sheet: str, filter_suffix: str) -> FilterControl:
    return FilterControl(
        Slider=FilterSliderControl(
            FilterControlId=f"ctrl-{sheet}-days-outstanding",
            Title="Minimum Days Outstanding",
            SourceFilterId=f"filter-recon-days-outstanding-{filter_suffix}",
            MinimumValue=0,
            MaximumValue=365,
            StepSize=1,
            Type="RANGE",
        ),
    )


# ---------------------------------------------------------------------------
# Per-sheet control sets
# ---------------------------------------------------------------------------

def build_recon_overview_controls() -> list[FilterControl]:
    """Controls for the Reconciliation Overview tab."""
    return [
        _recon_date_range_control("recon-overview"),
        _recon_match_status_control("recon-overview"),
        _recon_transaction_type_control("recon-overview"),
        _recon_external_system_control("recon-overview"),
        _recon_merchant_control("recon-overview"),
        _recon_days_outstanding_control("recon-overview", "overview"),
    ]


def build_sales_recon_controls() -> list[FilterControl]:
    """Controls for the Sales Reconciliation tab."""
    return [
        _recon_date_range_control("sales-recon"),
        _recon_match_status_control("sales-recon"),
        _recon_external_system_control("sales-recon"),
        _recon_merchant_control("sales-recon"),
        _recon_days_outstanding_control("sales-recon", "sales"),
    ]


def build_settlement_recon_controls() -> list[FilterControl]:
    """Controls for the Settlement Reconciliation tab."""
    return [
        _recon_date_range_control("settlement-recon"),
        _recon_match_status_control("settlement-recon"),
        _recon_external_system_control("settlement-recon"),
        _recon_merchant_control("settlement-recon"),
        _recon_days_outstanding_control("settlement-recon", "settlement"),
    ]


def build_payment_recon_controls() -> list[FilterControl]:
    """Controls for the Payment Reconciliation tab."""
    return [
        _recon_date_range_control("payment-recon"),
        _recon_match_status_control("payment-recon"),
        _recon_external_system_control("payment-recon"),
        _recon_merchant_control("payment-recon"),
        _recon_days_outstanding_control("payment-recon", "payment"),
    ]
