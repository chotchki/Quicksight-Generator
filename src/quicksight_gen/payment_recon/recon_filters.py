"""Filter groups and controls for the Payment Reconciliation sheet.

Defines four single-dataset filters with corresponding UI controls:
- Date range picker        -> recon sheet
- Match status dropdown    -> recon sheet
- External system dropdown -> recon sheet
- Days outstanding slider  -> recon sheet

All filters use SINGLE_DATASET + single-sheet scope so that QuickSight
treats them as sheet-local controls (no DefaultFilterControlConfiguration
required, no CrossSheet control type needed).
"""

from __future__ import annotations

from quicksight_gen.payment_recon.constants import (
    DS_PAYMENT_RECON,
    SHEET_PAYMENT_RECON,
)
from quicksight_gen.common.models import (
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
    NumericRangeFilterValue,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
    TimeRangeFilter,
)


def _recon_scope() -> FilterScopeConfiguration:
    return FilterScopeConfiguration(
        SelectedSheets=SelectedSheetsFilterScopeConfiguration(
            SheetVisualScopingConfigurations=[
                SheetVisualScopingConfiguration(
                    SheetId=SHEET_PAYMENT_RECON,
                    Scope="ALL_VISUALS",
                ),
            ]
        ),
    )


# ---------------------------------------------------------------------------
# Filter groups
# ---------------------------------------------------------------------------

def _recon_date_range_filter_group() -> FilterGroup:
    """Date range filter on transaction_date."""
    return FilterGroup(
        FilterGroupId="fg-recon-date-range",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_recon_scope(),
        Status="ENABLED",
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId="filter-recon-date-range",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_PAYMENT_RECON,
                        ColumnName="transaction_date",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    TimeGranularity="DAY",
                ),
            ),
        ],
    )


def _recon_match_status_filter_group() -> FilterGroup:
    """Match status dropdown."""
    return FilterGroup(
        FilterGroupId="fg-recon-match-status",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_recon_scope(),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-recon-match-status",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_PAYMENT_RECON,
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


def _recon_external_system_filter_group() -> FilterGroup:
    """External system dropdown."""
    return FilterGroup(
        FilterGroupId="fg-recon-external-system",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_recon_scope(),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-recon-external-system",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_PAYMENT_RECON,
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


def _recon_days_outstanding_filter_group() -> FilterGroup:
    """Days outstanding numeric slider."""
    return FilterGroup(
        FilterGroupId="fg-recon-days-outstanding",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_recon_scope(),
        Status="ENABLED",
        Filters=[
            Filter(
                NumericRangeFilter=NumericRangeFilter(
                    FilterId="filter-recon-days-outstanding",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_PAYMENT_RECON,
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
    """Return all filter groups for the Payment Reconciliation sheet."""
    return [
        _recon_date_range_filter_group(),
        _recon_match_status_filter_group(),
        _recon_external_system_filter_group(),
        _recon_days_outstanding_filter_group(),
    ]


# ---------------------------------------------------------------------------
# Filter controls (UI widgets on the recon sheet)
# ---------------------------------------------------------------------------

def build_recon_controls() -> list[FilterControl]:
    """Controls for the Payment Reconciliation tab.

    Uses direct control types (DateTimePicker, Dropdown, Slider) rather than
    CrossSheet controls, since all filters are SINGLE_DATASET scoped to one sheet.
    """
    return [
        FilterControl(
            DateTimePicker=FilterDateTimePickerControl(
                FilterControlId="ctrl-recon-date-range",
                Title="Date Range",
                SourceFilterId="filter-recon-date-range",
                Type="DATE_RANGE",
            ),
        ),
        FilterControl(
            Dropdown=FilterDropDownControl(
                FilterControlId="ctrl-recon-match-status",
                Title="Match Status",
                SourceFilterId="filter-recon-match-status",
                Type="MULTI_SELECT",
            ),
        ),
        FilterControl(
            Dropdown=FilterDropDownControl(
                FilterControlId="ctrl-recon-external-system",
                Title="External System",
                SourceFilterId="filter-recon-external-system",
                Type="MULTI_SELECT",
            ),
        ),
        FilterControl(
            Slider=FilterSliderControl(
                FilterControlId="ctrl-recon-days-outstanding",
                Title="Minimum Days Outstanding",
                SourceFilterId="filter-recon-days-outstanding",
                MinimumValue=0,
                MaximumValue=365,
                StepSize=1,
                Type="RANGE",
            ),
        ),
    ]
