"""Filter groups and controls for the analysis.

Defines the cross-visual filters with corresponding UI controls:
- Date range picker         -> all tabs
- Merchant dropdown         -> all tabs
- Location dropdown         -> all tabs
- Settlement status         -> Settlements + Exceptions tabs
- Payment status            -> Payments tab
- Payment method            -> Settlements + Payments tabs (SPEC 2.3)
- Show-Only-X toggles       -> Sales, Settlements, Payments
- Optional sale metadata    -> per-sheet controls derived from
                                OPTIONAL_SALE_METADATA (SPEC 2.2)
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.payment_recon.constants import (
    DS_PAYMENTS,
    DS_SALES,
    DS_SETTLEMENT_EXCEPTIONS,
    DS_SETTLEMENTS,
    SHEET_EXCEPTIONS,
    SHEET_PAYMENTS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
)
from quicksight_gen.payment_recon.datasets import OPTIONAL_SALE_METADATA
from quicksight_gen.common.models import (
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

# Per-sheet date-range filters. Each sheet's detail data lives in a
# different dataset with a different timestamp column, so `ALL_DATASETS`
# column-name propagation doesn't reach sheets that don't have
# `sale_timestamp`. Keep one filter group per sheet, bound to that
# sheet's own native timestamp column — predictable mental model:
# "the date control on this sheet filters this sheet's data."
_DATE_RANGE_BINDINGS = [
    ("sales", SHEET_SALES, DS_SALES, "sale_timestamp"),
    ("settlements", SHEET_SETTLEMENTS, DS_SETTLEMENTS, "settlement_date"),
    ("payments", SHEET_PAYMENTS, DS_PAYMENTS, "payment_date"),
    ("exceptions", SHEET_EXCEPTIONS, DS_SETTLEMENT_EXCEPTIONS, "sale_timestamp"),
]


def _date_range_filter_group(
    slug: str, sheet_id: str, dataset_id: str, column_name: str,
) -> FilterGroup:
    return FilterGroup(
        FilterGroupId=f"fg-{slug}-date-range",
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_selected_sheets_scope([sheet_id]),
        Status="ENABLED",
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId=f"filter-{slug}-date-range",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=dataset_id,
                        ColumnName=column_name,
                    ),
                    NullOption="NON_NULLS_ONLY",
                    TimeGranularity="DAY",
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


def _payment_method_filter_group() -> FilterGroup:
    """Payment method dropdown -- Settlements + Payments tabs.

    Filter column lives on the sales dataset; QuickSight propagates it to
    settlements and payments through their shared merchant_id joins.
    """
    return FilterGroup(
        FilterGroupId="fg-payment-method",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(
            [SHEET_SETTLEMENTS, SHEET_PAYMENTS]
        ),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-payment-method",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_SALES,
                        ColumnName="payment_method",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        }
                    ),
                    DefaultFilterControlConfiguration=DefaultFilterControlConfiguration(
                        Title="Payment Method",
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


# ---------------------------------------------------------------------------
# Show-Only-X toggles (replaces the days-outstanding slider on pipeline tabs)
# ---------------------------------------------------------------------------

def _state_toggle_filter_group(
    fg_id: str,
    filter_id: str,
    sheet_id: str,
    dataset_id: str,
    column_name: str,
) -> FilterGroup:
    """Backing filter for a Show-Only-X toggle — picking a single state
    value in the paired dropdown restricts rows to that state; clearing
    the selection falls back to FILTER_ALL_VALUES (no effect).
    """
    return FilterGroup(
        FilterGroupId=fg_id,
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_selected_sheets_scope([sheet_id]),
        Status="ENABLED",
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId=filter_id,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=dataset_id,
                        ColumnName=column_name,
                    ),
                    Configuration=CategoryFilterConfiguration(
                        FilterListConfiguration={
                            "MatchOperator": "CONTAINS",
                            "SelectAllOptions": "FILTER_ALL_VALUES",
                        },
                    ),
                ),
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Optional-metadata filter groups (SPEC 2.2)
# ---------------------------------------------------------------------------

def _optional_metadata_filter_group(
    col: str,
    ftype: str,
    label: str,
    sheet_ids: list[str],
) -> FilterGroup:
    """Build a filter group for one OPTIONAL_SALE_METADATA column.

    Numeric columns use a range slider (0 – 999); string columns use a
    multi-select dropdown.  Date/datetime columns are scoped out by type
    in OPTIONAL_SALE_METADATA today but reserved here for later additions.

    The sheet's direct FilterControls carry the widget configuration, so
    ``DefaultFilterControlConfiguration`` is intentionally not set here —
    AWS rejects it when a non-CrossSheet control already binds to the
    filter on a single sheet.
    """
    del label  # widget label lives on the direct FilterControl
    fg_id = f"fg-sales-meta-{col}"
    f_id = f"filter-sales-meta-{col}"
    column = ColumnIdentifier(DataSetIdentifier=DS_SALES, ColumnName=col)

    if ftype == "numeric":
        filter_obj = Filter(
            NumericRangeFilter=NumericRangeFilter(
                FilterId=f_id,
                Column=column,
                NullOption="ALL_VALUES",
                RangeMinimum=NumericRangeFilterValue(StaticValue=0),
                RangeMaximum=NumericRangeFilterValue(StaticValue=999),
                IncludeMinimum=True,
                IncludeMaximum=True,
            ),
        )
    elif ftype == "datetime":
        filter_obj = Filter(
            TimeRangeFilter=TimeRangeFilter(
                FilterId=f_id,
                Column=column,
                NullOption="NON_NULLS_ONLY",
                TimeGranularity="DAY",
            ),
        )
    else:
        filter_obj = Filter(
            CategoryFilter=CategoryFilter(
                FilterId=f_id,
                Column=column,
                Configuration=CategoryFilterConfiguration(
                    FilterListConfiguration={
                        "MatchOperator": "CONTAINS",
                        "SelectAllOptions": "FILTER_ALL_VALUES",
                    }
                ),
            ),
        )

    return FilterGroup(
        FilterGroupId=fg_id,
        CrossDataset="SINGLE_DATASET",
        ScopeConfiguration=_selected_sheets_scope(sheet_ids),
        Status="ENABLED",
        Filters=[filter_obj],
    )


def _optional_metadata_filter_groups() -> list[FilterGroup]:
    """Per-metadata-column filter groups (Sales tab only for now)."""
    return [
        _optional_metadata_filter_group(col, ftype, label, [SHEET_SALES])
        for col, _ddl, _qs, ftype, label in OPTIONAL_SALE_METADATA
    ]


def build_filter_groups(cfg: Config) -> list[FilterGroup]:
    """Return all filter groups for the analysis definition."""
    del cfg  # slider default is independent of late_default_days
    groups = [
        *[
            _date_range_filter_group(slug, sheet_id, ds, col)
            for slug, sheet_id, ds, col in _DATE_RANGE_BINDINGS
        ],
        _merchant_filter_group(),
        _location_filter_group(),
        _settlement_status_filter_group(),
        _payment_status_filter_group(),
        _payment_method_filter_group(),
        _state_toggle_filter_group(
            "fg-sales-unsettled",
            "filter-sales-unsettled",
            SHEET_SALES,
            DS_SALES,
            "settlement_state",
        ),
        _state_toggle_filter_group(
            "fg-settlements-unpaid",
            "filter-settlements-unpaid",
            SHEET_SETTLEMENTS,
            DS_SETTLEMENTS,
            "payment_state",
        ),
        _state_toggle_filter_group(
            "fg-payments-unmatched",
            "filter-payments-unmatched",
            SHEET_PAYMENTS,
            DS_PAYMENTS,
            "external_match_state",
        ),
    ]
    groups.extend(_optional_metadata_filter_groups())
    return groups


# ---------------------------------------------------------------------------
# Filter controls (UI widgets on sheets)
#
# Control IDs must be globally unique across all sheets in an analysis.
# Each builder takes a sheet prefix to ensure uniqueness.
# ---------------------------------------------------------------------------

def _date_range_control(sheet: str) -> FilterControl:
    """Native date-range picker bound to this sheet's own date filter."""
    return FilterControl(
        DateTimePicker=FilterDateTimePickerControl(
            FilterControlId=f"ctrl-{sheet}-date-range",
            Title="Date Range",
            SourceFilterId=f"filter-{sheet}-date-range",
            Type="DATE_RANGE",
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


def _payment_method_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-{sheet}-payment-method",
            SourceFilterId="filter-payment-method",
        ),
    )


def _state_toggle_control(
    ctrl_id: str,
    title: str,
    source_filter_id: str,
) -> FilterControl:
    """Single-select dropdown widget paired with ``_state_toggle_filter_group``.
    QuickSight lists both state values; the label frames the toggle intent.
    """
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId=ctrl_id,
            Title=title,
            SourceFilterId=source_filter_id,
            Type="SINGLE_SELECT",
        ),
    )


def _optional_metadata_controls(sheet: str) -> list[FilterControl]:
    """Return controls for every optional-metadata column on the sales sheet."""
    controls: list[FilterControl] = []
    for col, _ddl, _qs, ftype, label in OPTIONAL_SALE_METADATA:
        source_id = f"filter-sales-meta-{col}"
        ctrl_id = f"ctrl-{sheet}-meta-{col}"
        if ftype == "numeric":
            controls.append(FilterControl(
                Slider=FilterSliderControl(
                    FilterControlId=ctrl_id,
                    Title=label,
                    SourceFilterId=source_id,
                    MinimumValue=0,
                    MaximumValue=999,
                    StepSize=1,
                    Type="RANGE",
                ),
            ))
        elif ftype == "datetime":
            controls.append(FilterControl(
                DateTimePicker=FilterDateTimePickerControl(
                    FilterControlId=ctrl_id,
                    Title=label,
                    SourceFilterId=source_id,
                    Type="DATE_RANGE",
                ),
            ))
        else:
            controls.append(FilterControl(
                Dropdown=FilterDropDownControl(
                    FilterControlId=ctrl_id,
                    Title=label,
                    SourceFilterId=source_id,
                    Type="MULTI_SELECT",
                ),
            ))
    return controls


# ---------------------------------------------------------------------------
# Per-sheet control sets
# ---------------------------------------------------------------------------

def build_sales_controls(cfg: Config) -> list[FilterControl]:
    """Controls for the Sales Overview tab."""
    del cfg
    return [
        _date_range_control("sales"),
        _merchant_control("sales"),
        _location_control("sales"),
        _state_toggle_control(
            "ctrl-sales-unsettled",
            "Show Only Unsettled",
            "filter-sales-unsettled",
        ),
    ] + _optional_metadata_controls("sales")


def build_settlements_controls(cfg: Config) -> list[FilterControl]:
    """Controls for the Settlements tab."""
    del cfg
    return [
        _date_range_control("settlements"),
        _merchant_control("settlements"),
        _location_control("settlements"),
        _settlement_status_control("settlements"),
        _payment_method_control("settlements"),
        _state_toggle_control(
            "ctrl-settlements-unpaid",
            "Show Only Unpaid",
            "filter-settlements-unpaid",
        ),
    ]


def build_payments_controls(cfg: Config) -> list[FilterControl]:
    """Controls for the Payments tab."""
    del cfg
    return [
        _date_range_control("payments"),
        _merchant_control("payments"),
        _location_control("payments"),
        _payment_status_control("payments"),
        _payment_method_control("payments"),
        _state_toggle_control(
            "ctrl-payments-unmatched",
            "Show Only Unmatched Externally",
            "filter-payments-unmatched",
        ),
    ]


def build_exceptions_controls(cfg: Config) -> list[FilterControl]:
    """Controls for the Exceptions & Alerts tab."""
    del cfg
    return [
        _date_range_control("exceptions"),
        _merchant_control("exceptions"),
        _location_control("exceptions"),
        _settlement_status_control("exceptions"),
    ]
