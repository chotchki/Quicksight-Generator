"""Filter groups and controls for the analysis.

Defines five cross-visual filters with corresponding UI controls:
- Date range picker      -> all tabs
- Merchant dropdown      -> all tabs
- Location dropdown      -> all tabs
- Settlement status      -> Settlements + Exceptions tabs
- Payment status         -> Payments tab
"""

from __future__ import annotations

from quicksight_gen.constants import (
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
    FilterDateTimePickerControl,
    FilterDropDownControl,
    FilterGroup,
    FilterScopeConfiguration,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
    TimeRangeFilter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ALL_SHEET_IDS = [SHEET_SALES, SHEET_SETTLEMENTS, SHEET_PAYMENTS, SHEET_EXCEPTIONS]


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

def _date_range_filter_group() -> FilterGroup:
    """Date range filter applied to all sheets via the sale/settlement/payment
    timestamp columns. Uses a single TimeRangeFilter on the sales dataset;
    QuickSight propagates across linked datasets when scoped to all sheets."""
    return FilterGroup(
        FilterGroupId="fg-date-range",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_SHEET_IDS),
        Status="ENABLED",
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId="filter-date-range",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_SALES,
                        ColumnName="sale_timestamp",
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


def _merchant_filter_group() -> FilterGroup:
    """Merchant dropdown filter -- all sheets."""
    return FilterGroup(
        FilterGroupId="fg-merchant",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_SHEET_IDS),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-merchant",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_SALES,
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


def _location_filter_group() -> FilterGroup:
    """Location dropdown filter -- all sheets."""
    return FilterGroup(
        FilterGroupId="fg-location",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(ALL_SHEET_IDS),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-location",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_SALES,
                        ColumnName="location_id",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="Location",
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


def _settlement_status_filter_group() -> FilterGroup:
    """Settlement status dropdown -- Settlements + Exceptions tabs."""
    return FilterGroup(
        FilterGroupId="fg-settlement-status",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_selected_sheets_scope(
            [SHEET_SETTLEMENTS, SHEET_EXCEPTIONS]
        ),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-settlement-status",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_SETTLEMENTS,
                        ColumnName="settlement_status",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="Settlement Status",
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


def _payment_status_filter_group() -> FilterGroup:
    """Payment status dropdown -- Payments tab only."""
    return FilterGroup(
        FilterGroupId="fg-payment-status",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_selected_sheets_scope([SHEET_PAYMENTS]),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-payment-status",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_PAYMENTS,
                        ColumnName="payment_status",
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


def build_filter_groups() -> list[FilterGroup]:
    """Return all filter groups for the analysis definition."""
    return [
        _date_range_filter_group(),
        _merchant_filter_group(),
        _location_filter_group(),
        _settlement_status_filter_group(),
        _payment_status_filter_group(),
    ]


# ---------------------------------------------------------------------------
# Filter controls (UI widgets on sheets)
#
# Control IDs must be globally unique across all sheets in an analysis.
# Each builder takes a sheet prefix to ensure uniqueness.
# ---------------------------------------------------------------------------

def _date_range_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-date-range",
            SourceFilterId="filter-date-range",
        ),
    )


def _merchant_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-merchant",
            SourceFilterId="filter-merchant",
        ),
    )


def _location_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-location",
            SourceFilterId="filter-location",
        ),
    )


def _settlement_status_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-settlement-status",
            SourceFilterId="filter-settlement-status",
        ),
    )


def _payment_status_control(sheet: str) -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId=f"ctrl-{sheet}-payment-status",
            Title="Payment Status",
            SourceFilterId="filter-payment-status",
            Type="MULTI_SELECT",
        ),
    )


# ---------------------------------------------------------------------------
# Per-sheet control sets
# ---------------------------------------------------------------------------

def build_sales_controls() -> list[FilterControl]:
    """Controls for the Sales Overview tab."""
    return [
        _date_range_control("sales"),
        _merchant_control("sales"),
        _location_control("sales"),
    ]


def build_settlements_controls() -> list[FilterControl]:
    """Controls for the Settlements tab."""
    return [
        _date_range_control("settlements"),
        _merchant_control("settlements"),
        _location_control("settlements"),
        _settlement_status_control("settlements"),
    ]


def build_payments_controls() -> list[FilterControl]:
    """Controls for the Payments tab."""
    return [
        _date_range_control("payments"),
        _merchant_control("payments"),
        _location_control("payments"),
        _payment_status_control("payments"),
    ]


def build_exceptions_controls() -> list[FilterControl]:
    """Controls for the Exceptions & Alerts tab."""
    return [
        _date_range_control("exceptions"),
        _merchant_control("exceptions"),
        _location_control("exceptions"),
        _settlement_status_control("exceptions"),
    ]
