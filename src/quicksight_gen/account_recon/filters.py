"""Filter groups + controls for Account Recon.

Phase 4 broadens what Phase 3 shipped (date-range only):

Multi-selects (MULTI_SELECT dropdowns):
  - parent-account, child-account — scoped to Balances / Transactions / Exceptions
  - transfer-status                — scoped to Transfers
  - transaction-status             — scoped to Transactions

Show-Only-X toggles (SINGLE_SELECT dropdowns, same pattern as PR's Phase 2
pivot — the date-range filter already covers "recency"; these narrow the
rows to "the problematic ones" with a single click):
  - Balances parent table → "Show Only Drift"
  - Balances child table  → "Show Only Drift"
  - Transfers             → "Show Only Unhealthy"
  - Transactions          → "Show Only Failed"

Drill-down parameter filters live in ``analysis.py`` alongside the
parameter declarations, same as payment_recon.
"""

from __future__ import annotations

from quicksight_gen.account_recon.constants import (
    DS_AR_ACCOUNT_BALANCE_DRIFT,
    DS_AR_ACCOUNTS,
    DS_AR_PARENT_ACCOUNTS,
    DS_AR_PARENT_BALANCE_DRIFT,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    SHEET_AR_BALANCES,
    SHEET_AR_EXCEPTIONS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.common.config import Config
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
    FilterDropDownControl,
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

_ACCOUNT_SCOPED_SHEETS = [
    SHEET_AR_BALANCES,
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


# ---------------------------------------------------------------------------
# Shared date range
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Multi-select category filters (Phase 4.1)
# ---------------------------------------------------------------------------

def _multi_select_filter_group(
    fg_id: str,
    filter_id: str,
    title: str,
    dataset_id: str,
    column_name: str,
    sheet_ids: list[str],
    cross_dataset: str = "ALL_DATASETS",
) -> FilterGroup:
    # AWS rejects DefaultFilterControlConfiguration on a CategoryFilter
    # that's SINGLE_DATASET + single-sheet and already has a direct
    # (non-CrossSheet) Dropdown control bound to it (same rule as
    # payment_recon). Those filters get their widget config from the
    # sheet's direct FilterControls list instead.
    default_control = None
    if cross_dataset != "SINGLE_DATASET":
        default_control = DefaultFilterControlConfiguration(
            Title=title,
            ControlOptions=DefaultFilterControlOptions(
                DefaultDropdownOptions=DefaultDropdownControlOptions(
                    Type="MULTI_SELECT",
                ),
            ),
        )
    return FilterGroup(
        FilterGroupId=fg_id,
        CrossDataset=cross_dataset,
        ScopeConfiguration=_selected_sheets_scope(sheet_ids),
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
                        }
                    ),
                    DefaultFilterControlConfiguration=default_control,
                ),
            ),
        ],
    )


def _parent_account_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id="fg-ar-parent-account",
        filter_id="filter-ar-parent-account",
        title="Parent Account",
        dataset_id=DS_AR_PARENT_ACCOUNTS,
        column_name="parent_account_id",
        sheet_ids=_ACCOUNT_SCOPED_SHEETS,
    )


def _child_account_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id="fg-ar-child-account",
        filter_id="filter-ar-child-account",
        title="Child Account",
        dataset_id=DS_AR_ACCOUNTS,
        column_name="account_id",
        sheet_ids=_ACCOUNT_SCOPED_SHEETS,
    )


def _transfer_status_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id="fg-ar-transfer-status",
        filter_id="filter-ar-transfer-status",
        title="Transfer Status",
        dataset_id=DS_AR_TRANSFER_SUMMARY,
        column_name="net_zero_status",
        sheet_ids=[SHEET_AR_TRANSFERS],
        cross_dataset="SINGLE_DATASET",
    )


def _transaction_status_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id="fg-ar-transaction-status",
        filter_id="filter-ar-transaction-status",
        title="Transaction Status",
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="status",
        sheet_ids=[SHEET_AR_TRANSACTIONS],
        cross_dataset="SINGLE_DATASET",
    )


# ---------------------------------------------------------------------------
# Show-Only-X SINGLE_SELECT toggles (Phase 4.2)
# ---------------------------------------------------------------------------

def _state_toggle_filter_group(
    fg_id: str,
    filter_id: str,
    sheet_id: str,
    dataset_id: str,
    column_name: str,
) -> FilterGroup:
    """Backing CategoryFilter for a Show-Only-X toggle.

    Same pattern as payment_recon: SINGLE_DATASET + SINGLE_SELECT
    dropdown. Clearing the selection falls back to FILTER_ALL_VALUES
    (no effect); selecting a value pins visuals to that value only.
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


def _state_toggle_control(
    ctrl_id: str,
    title: str,
    source_filter_id: str,
) -> FilterControl:
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId=ctrl_id,
            Title=title,
            SourceFilterId=source_filter_id,
            Type="SINGLE_SELECT",
        ),
    )


# ---------------------------------------------------------------------------
# Top-level assembly
# ---------------------------------------------------------------------------

def build_filter_groups(cfg: Config) -> list[FilterGroup]:
    del cfg
    return [
        _date_range_filter_group(),
        _parent_account_filter_group(),
        _child_account_filter_group(),
        _transfer_status_filter_group(),
        _transaction_status_filter_group(),
        # Show-Only toggles — one filter group per toggle.
        _state_toggle_filter_group(
            "fg-ar-balances-parent-drift",
            "filter-ar-balances-parent-drift",
            SHEET_AR_BALANCES,
            DS_AR_PARENT_BALANCE_DRIFT,
            "drift_status",
        ),
        _state_toggle_filter_group(
            "fg-ar-balances-child-drift",
            "filter-ar-balances-child-drift",
            SHEET_AR_BALANCES,
            DS_AR_ACCOUNT_BALANCE_DRIFT,
            "drift_status",
        ),
        _state_toggle_filter_group(
            "fg-ar-transfers-unhealthy",
            "filter-ar-transfers-unhealthy",
            SHEET_AR_TRANSFERS,
            DS_AR_TRANSFER_SUMMARY,
            "net_zero_status",
        ),
        _state_toggle_filter_group(
            "fg-ar-transactions-failed",
            "filter-ar-transactions-failed",
            SHEET_AR_TRANSACTIONS,
            DS_AR_TRANSACTIONS,
            "is_failed",
        ),
    ]


# ---------------------------------------------------------------------------
# Per-sheet filter controls
# ---------------------------------------------------------------------------

def _cross_sheet_control(sheet: str, name: str, source_filter_id: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-ar-{sheet}-{name}",
            SourceFilterId=source_filter_id,
        ),
    )


def _date_range_control(sheet: str) -> FilterControl:
    return _cross_sheet_control(sheet, "date-range", "filter-ar-date-range")


def _parent_account_control(sheet: str) -> FilterControl:
    return _cross_sheet_control(sheet, "parent-account", "filter-ar-parent-account")


def _child_account_control(sheet: str) -> FilterControl:
    return _cross_sheet_control(sheet, "child-account", "filter-ar-child-account")


def build_balances_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("balances"),
        _parent_account_control("balances"),
        _child_account_control("balances"),
        _state_toggle_control(
            "ctrl-ar-balances-parent-drift",
            "Show Only Parent Drift",
            "filter-ar-balances-parent-drift",
        ),
        _state_toggle_control(
            "ctrl-ar-balances-child-drift",
            "Show Only Child Drift",
            "filter-ar-balances-child-drift",
        ),
    ]


def build_transfers_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("transfers"),
        FilterControl(
            Dropdown=FilterDropDownControl(
                FilterControlId="ctrl-ar-transfers-status",
                Title="Transfer Status",
                SourceFilterId="filter-ar-transfer-status",
                Type="MULTI_SELECT",
            ),
        ),
        _state_toggle_control(
            "ctrl-ar-transfers-unhealthy",
            "Show Only Unhealthy",
            "filter-ar-transfers-unhealthy",
        ),
    ]


def build_transactions_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("transactions"),
        _parent_account_control("transactions"),
        _child_account_control("transactions"),
        FilterControl(
            Dropdown=FilterDropDownControl(
                FilterControlId="ctrl-ar-transactions-status",
                Title="Transaction Status",
                SourceFilterId="filter-ar-transaction-status",
                Type="MULTI_SELECT",
            ),
        ),
        _state_toggle_control(
            "ctrl-ar-transactions-failed",
            "Show Only Failed",
            "filter-ar-transactions-failed",
        ),
    ]


def build_exceptions_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("exceptions"),
        _parent_account_control("exceptions"),
        _child_account_control("exceptions"),
    ]
