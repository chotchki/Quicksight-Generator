"""Filter groups + controls for Account Recon.

Phase 3 keeps this minimal: a single date-range filter scoped to
Balances, Transfers, Transactions, and Exceptions. Account-level
multi-selects and drill-down parameters land in Phase 4.
"""

from __future__ import annotations

from quicksight_gen.account_recon.constants import (
    DS_AR_TRANSACTIONS,
    SHEET_AR_BALANCES,
    SHEET_AR_EXCEPTIONS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import (
    ColumnIdentifier,
    DefaultDateTimePickerControlOptions,
    DefaultFilterControlConfiguration,
    DefaultFilterControlOptions,
    Filter,
    FilterControl,
    FilterCrossSheetControl,
    FilterGroup,
    FilterScopeConfiguration,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
    TimeRangeFilter,
)


_ALL_SHEETS = [
    SHEET_AR_BALANCES,
    SHEET_AR_TRANSFERS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_EXCEPTIONS,
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


def _date_range_filter_group() -> FilterGroup:
    """Transactions-backed date range propagated across all AR sheets.

    Views that don't join ar_transactions directly (e.g. transfer_summary
    through first_posted_at, balance_drift through balance_date) still
    respect the filter because QuickSight scopes ALL_DATASETS across the
    selected sheets.
    """
    return FilterGroup(
        FilterGroupId="fg-ar-date-range",
        CrossDataset="ALL_DATASETS",
        ScopeConfiguration=_selected_sheets_scope(_ALL_SHEETS),
        Status="ENABLED",
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId="filter-ar-date-range",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_AR_TRANSACTIONS,
                        ColumnName="posted_at",
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


def build_filter_groups(cfg: Config) -> list[FilterGroup]:
    del cfg
    return [_date_range_filter_group()]


def _date_range_control(sheet: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-ar-{sheet}-date-range",
            SourceFilterId="filter-ar-date-range",
        ),
    )


def build_balances_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [_date_range_control("balances")]


def build_transfers_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [_date_range_control("transfers")]


def build_transactions_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [_date_range_control("transactions")]


def build_exceptions_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [_date_range_control("exceptions")]
