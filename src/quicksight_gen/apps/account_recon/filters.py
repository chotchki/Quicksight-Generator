"""Filter groups + controls for Account Recon.

Phase 5 adds two more filters on top of Phase 4:

Multi-selects (MULTI_SELECT dropdowns):
  - ledger-account, subledger-account — scoped to Balances / Transactions / Exceptions
  - transfer-status                    — scoped to Transfers
  - transaction-status                 — scoped to Transactions
  - transfer-type                      — scoped to Transfers / Transactions / Exceptions
                                         (Phase 5.5 — covers ach/wire/internal/cash)

Show-Only-X toggles (SINGLE_SELECT dropdowns, same pattern as PR's Phase 2
pivot — the date-range filter already covers "recency"; these narrow the
rows to "the problematic ones" with a single click):
  - Balances ledger table    → "Show Only Drift"
  - Balances sub-ledger table → "Show Only Drift"
  - Balances sub-ledger table → "Show Only Overdraft" (Phase 5.5 — stored_balance < 0)
  - Transactions              → "Show Only Failed"

Drill-down parameter filters live in ``analysis.py`` alongside the
parameter declarations, same as payment_recon.
"""

from __future__ import annotations

from typing import Literal

from quicksight_gen.apps.account_recon.constants import (
    DS_AR_DAILY_STATEMENT_SUMMARY,
    DS_AR_LEDGER_ACCOUNTS,
    DS_AR_LEDGER_BALANCE_DRIFT,
    DS_AR_SUBLEDGER_ACCOUNTS,
    DS_AR_SUBLEDGER_BALANCE_DRIFT,
    DS_AR_TRANSACTIONS,
    DS_AR_TRANSFER_SUMMARY,
    DS_AR_UNIFIED_EXCEPTIONS,
    FG_AR_BALANCES_LEDGER_DRIFT,
    FG_AR_BALANCES_OVERDRAFT,
    FG_AR_BALANCES_SUBLEDGER_DRIFT,
    FG_AR_DATE_RANGE,
    FG_AR_DS_ACCOUNT,
    FG_AR_DS_BALANCE_DATE,
    FG_AR_LEDGER_ACCOUNT,
    FG_AR_ORIGIN,
    FG_AR_POSTING_LEVEL,
    FG_AR_SUBLEDGER_ACCOUNT,
    FG_AR_TODAYS_EXC_ACCOUNT,
    FG_AR_TODAYS_EXC_AGING,
    FG_AR_TODAYS_EXC_CHECK_TYPE,
    FG_AR_TODAYS_EXC_IS_LATE,
    FG_AR_TRANSACTION_STATUS,
    FG_AR_TRANSACTIONS_FAILED,
    FG_AR_TRANSFER_STATUS,
    FG_AR_TRANSFER_TYPE,
    P_AR_DS_ACCOUNT,
    P_AR_DS_BALANCE_DATE,
    SHEET_AR_BALANCES,
    SHEET_AR_DAILY_STATEMENT,
    SHEET_AR_EXCEPTIONS_TRENDS,
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import FilterGroupId, SheetId
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
    ParameterControl,
    ParameterDateTimePickerControl,
    ParameterDropDownControl,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
    TimeEqualityFilter,
    TimeRangeFilter,
)


_ALL_SHEETS = [
    SHEET_AR_BALANCES,
    SHEET_AR_TRANSFERS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_EXCEPTIONS_TRENDS,
]

_ACCOUNT_SCOPED_SHEETS = [
    SHEET_AR_BALANCES,
    SHEET_AR_TRANSACTIONS,
]

_TRANSFER_TYPE_SCOPED_SHEETS = [
    SHEET_AR_TRANSFERS,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_EXCEPTIONS_TRENDS,
]


def _selected_sheets_scope(sheet_ids: list[SheetId]) -> FilterScopeConfiguration:
    return FilterScopeConfiguration(
        SelectedSheets=SelectedSheetsFilterScopeConfiguration(
            SheetVisualScopingConfigurations=[
                SheetVisualScopingConfiguration(
                    SheetId=sid,
                    Scope=SheetVisualScopingConfiguration.ALL_VISUALS,
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

    Views that don't join the posting table directly (e.g. transfer_summary
    through first_posted_at, balance_drift through balance_date) still
    respect the filter because QuickSight scopes ALL_DATASETS across the
    selected sheets.
    """
    return FilterGroup(
        FilterGroupId=FG_AR_DATE_RANGE,
        CrossDataset=FilterGroup.ALL_DATASETS,
        ScopeConfiguration=_selected_sheets_scope(_ALL_SHEETS),
        Status=FilterGroup.ENABLED,
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
    cross_dataset: Literal["SINGLE_DATASET", "ALL_DATASETS"] = FilterGroup.ALL_DATASETS,
) -> FilterGroup:
    # AWS rule: multi-sheet filters MUST carry
    # DefaultFilterControlConfiguration (so CrossSheet controls on the
    # other sheets have widget specs to inherit). Single-sheet filters
    # MUST NOT carry it — the sheet's direct FilterControls list provides
    # the widget. cross_dataset doesn't change either rule.
    default_control = None
    if len(sheet_ids) > 1:
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
        Status=FilterGroup.ENABLED,
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


def _ledger_account_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_LEDGER_ACCOUNT,
        filter_id="filter-ar-ledger-account",
        title="Ledger Account",
        dataset_id=DS_AR_LEDGER_ACCOUNTS,
        column_name="ledger_account_id",
        sheet_ids=_ACCOUNT_SCOPED_SHEETS,
    )


def _subledger_account_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_SUBLEDGER_ACCOUNT,
        filter_id="filter-ar-subledger-account",
        title="Sub-Ledger Account",
        dataset_id=DS_AR_SUBLEDGER_ACCOUNTS,
        column_name="subledger_account_id",
        sheet_ids=_ACCOUNT_SCOPED_SHEETS,
    )


def _transfer_status_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_TRANSFER_STATUS,
        filter_id="filter-ar-transfer-status",
        title="Transfer Status",
        dataset_id=DS_AR_TRANSFER_SUMMARY,
        column_name="net_zero_status",
        sheet_ids=[SHEET_AR_TRANSFERS],
        cross_dataset="SINGLE_DATASET",
    )


def _transaction_status_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_TRANSACTION_STATUS,
        filter_id="filter-ar-transaction-status",
        title="Transaction Status",
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="status",
        sheet_ids=[SHEET_AR_TRANSACTIONS],
        cross_dataset="SINGLE_DATASET",
    )


def _transfer_type_filter_group() -> FilterGroup:
    """Cross-tab transfer-type multi-select (Phase 5.5).

    Column exists on transactions, transfer_summary, and limit_breach
    datasets; QuickSight applies the filter to any visual whose dataset
    carries the same column name. Balances-only datasets don't have
    transfer_type so the filter naturally skips them.
    """
    return _multi_select_filter_group(
        fg_id=FG_AR_TRANSFER_TYPE,
        filter_id="filter-ar-transfer-type",
        title="Transfer Type",
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="transfer_type",
        sheet_ids=_TRANSFER_TYPE_SCOPED_SHEETS,
    )


def _posting_level_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_POSTING_LEVEL,
        filter_id="filter-ar-posting-level",
        title="Posting Level",
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="posting_level",
        sheet_ids=[SHEET_AR_TRANSACTIONS],
        cross_dataset="SINGLE_DATASET",
    )


_ORIGIN_SCOPED_SHEETS = [
    SHEET_AR_TRANSACTIONS,
]


def _origin_filter_group() -> FilterGroup:
    """Cross-tab origin multi-select (Phase D.1).

    Column exists on transactions, transfer_summary, and non_zero_transfers
    datasets; QuickSight applies the filter to any visual whose dataset
    carries the same column name.
    """
    return _multi_select_filter_group(
        fg_id=FG_AR_ORIGIN,
        filter_id="filter-ar-origin",
        title="Origin",
        dataset_id=DS_AR_TRANSACTIONS,
        column_name="origin",
        sheet_ids=_ORIGIN_SCOPED_SHEETS,
    )


# ---------------------------------------------------------------------------
# Show-Only-X SINGLE_SELECT toggles (Phase 4.2)
# ---------------------------------------------------------------------------

def _state_toggle_filter_group(
    fg_id: FilterGroupId,
    filter_id: str,
    sheet_id: SheetId,
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
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_selected_sheets_scope([sheet_id]),
        Status=FilterGroup.ENABLED,
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

# ---------------------------------------------------------------------------
# Today's Exceptions (Phase K.1.2) — sheet-scoped pickers on the unified
# exceptions dataset. SINGLE_DATASET so QuickSight accepts the per-sheet
# Dropdown control wired in build_todays_exceptions_controls.
# ---------------------------------------------------------------------------

_UNIFIED_EXCEPTIONS_SHEETS = [
    SHEET_AR_TODAYS_EXCEPTIONS,
    SHEET_AR_EXCEPTIONS_TRENDS,
]


def _todays_exceptions_check_type_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_TODAYS_EXC_CHECK_TYPE,
        filter_id="filter-ar-todays-exc-check-type",
        title="Check Type",
        dataset_id=DS_AR_UNIFIED_EXCEPTIONS,
        column_name="check_type",
        sheet_ids=_UNIFIED_EXCEPTIONS_SHEETS,
        cross_dataset="SINGLE_DATASET",
    )


def _todays_exceptions_account_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_TODAYS_EXC_ACCOUNT,
        filter_id="filter-ar-todays-exc-account",
        title="Account",
        dataset_id=DS_AR_UNIFIED_EXCEPTIONS,
        column_name="account_id",
        sheet_ids=_UNIFIED_EXCEPTIONS_SHEETS,
        cross_dataset="SINGLE_DATASET",
    )


def _todays_exceptions_aging_filter_group() -> FilterGroup:
    return _multi_select_filter_group(
        fg_id=FG_AR_TODAYS_EXC_AGING,
        filter_id="filter-ar-todays-exc-aging",
        title="Aging Bucket",
        dataset_id=DS_AR_UNIFIED_EXCEPTIONS,
        column_name="aging_bucket",
        sheet_ids=_UNIFIED_EXCEPTIONS_SHEETS,
        cross_dataset="SINGLE_DATASET",
    )


def _todays_exceptions_is_late_filter_group() -> FilterGroup:
    # K.3.3: surfaces the data-driven is_late predicate as a sheet-scoped
    # picker (Late / On Time). Lets ops triage by lateness without
    # eyeballing days_outstanding against a mental threshold — the
    # `expected_complete_at` ETL column tells the answer per row.
    return _multi_select_filter_group(
        fg_id=FG_AR_TODAYS_EXC_IS_LATE,
        filter_id="filter-ar-todays-exc-is-late",
        title="Lateness",
        dataset_id=DS_AR_UNIFIED_EXCEPTIONS,
        column_name="is_late",
        sheet_ids=_UNIFIED_EXCEPTIONS_SHEETS,
        cross_dataset="SINGLE_DATASET",
    )


def build_filter_groups(cfg: Config) -> list[FilterGroup]:
    del cfg
    return [
        _date_range_filter_group(),
        _ledger_account_filter_group(),
        _subledger_account_filter_group(),
        _transfer_status_filter_group(),
        _transaction_status_filter_group(),
        _transfer_type_filter_group(),
        _posting_level_filter_group(),
        _origin_filter_group(),
        # Show-Only toggles — one filter group per toggle.
        _state_toggle_filter_group(
            FG_AR_BALANCES_LEDGER_DRIFT,
            "filter-ar-balances-ledger-drift",
            SHEET_AR_BALANCES,
            DS_AR_LEDGER_BALANCE_DRIFT,
            "drift_status",
        ),
        _state_toggle_filter_group(
            FG_AR_BALANCES_SUBLEDGER_DRIFT,
            "filter-ar-balances-subledger-drift",
            SHEET_AR_BALANCES,
            DS_AR_SUBLEDGER_BALANCE_DRIFT,
            "drift_status",
        ),
        _state_toggle_filter_group(
            FG_AR_BALANCES_OVERDRAFT,
            "filter-ar-balances-overdraft",
            SHEET_AR_BALANCES,
            DS_AR_SUBLEDGER_BALANCE_DRIFT,
            "overdraft_status",
        ),
        _state_toggle_filter_group(
            FG_AR_TRANSACTIONS_FAILED,
            "filter-ar-transactions-failed",
            SHEET_AR_TRANSACTIONS,
            DS_AR_TRANSACTIONS,
            "is_failed",
        ),
        # Phase I.2 — Daily Statement sheet pickers (account + date)
        _daily_statement_account_filter_group(),
        _daily_statement_date_filter_group(),
        # Phase K.1.2 — Today's Exceptions sheet pickers
        _todays_exceptions_check_type_filter_group(),
        _todays_exceptions_account_filter_group(),
        _todays_exceptions_aging_filter_group(),
        # Phase K.3.3 — data-driven Lateness picker (Late / On Time)
        _todays_exceptions_is_late_filter_group(),
    ]


# ---------------------------------------------------------------------------
# Per-sheet filter controls
# ---------------------------------------------------------------------------

def _cross_sheet_control(sheet: SheetId, name: str, source_filter_id: str) -> FilterControl:
    return FilterControl(
        CrossSheet=FilterCrossSheetControl(
            FilterControlId=f"ctrl-ar-{sheet}-{name}",
            SourceFilterId=source_filter_id,
        ),
    )


def _date_range_control(sheet: SheetId) -> FilterControl:
    return _cross_sheet_control(sheet, "date-range", "filter-ar-date-range")


def _ledger_account_control(sheet: SheetId) -> FilterControl:
    return _cross_sheet_control(sheet, "ledger-account", "filter-ar-ledger-account")


def _subledger_account_control(sheet: SheetId) -> FilterControl:
    return _cross_sheet_control(sheet, "subledger-account", "filter-ar-subledger-account")


def _transfer_type_control(sheet: SheetId) -> FilterControl:
    return _cross_sheet_control(sheet, "transfer-type", "filter-ar-transfer-type")


def _origin_control(sheet: SheetId) -> FilterControl:
    # Single-sheet filter (Transactions only after Phase K.1 dropped the
    # legacy Exceptions sheet) → use a direct Dropdown rather than a
    # CrossSheet control. AWS rejects CrossSheet controls bound to
    # filters whose scope is a single sheet without
    # DefaultFilterControlConfiguration on the filter, and it rejects
    # DefaultFilterControlConfiguration on a single-sheet filter — the
    # only consistent shape is a direct Dropdown.
    return FilterControl(
        Dropdown=FilterDropDownControl(
            FilterControlId=f"ctrl-ar-{sheet}-origin",
            Title="Origin",
            SourceFilterId="filter-ar-origin",
            Type="MULTI_SELECT",
        ),
    )


def build_balances_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("balances"),
        _ledger_account_control("balances"),
        _subledger_account_control("balances"),
        _state_toggle_control(
            "ctrl-ar-balances-ledger-drift",
            "Show Only Ledger Drift",
            "filter-ar-balances-ledger-drift",
        ),
        _state_toggle_control(
            "ctrl-ar-balances-subledger-drift",
            "Show Only Sub-Ledger Drift",
            "filter-ar-balances-subledger-drift",
        ),
        _state_toggle_control(
            "ctrl-ar-balances-overdraft",
            "Show Only Overdraft",
            "filter-ar-balances-overdraft",
        ),
    ]


def build_transfers_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("transfers"),
        _transfer_type_control("transfers"),
        FilterControl(
            Dropdown=FilterDropDownControl(
                FilterControlId="ctrl-ar-transfers-status",
                Title="Transfer Status",
                SourceFilterId="filter-ar-transfer-status",
                Type="MULTI_SELECT",
            ),
        ),
    ]


def build_transactions_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [
        _date_range_control("transactions"),
        _ledger_account_control("transactions"),
        _subledger_account_control("transactions"),
        _transfer_type_control("transactions"),
        _origin_control("transactions"),
        FilterControl(
            Dropdown=FilterDropDownControl(
                FilterControlId="ctrl-ar-transactions-posting-level",
                Title="Posting Level",
                SourceFilterId="filter-ar-posting-level",
                Type="MULTI_SELECT",
            ),
        ),
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


def build_todays_exceptions_controls(cfg: Config) -> list[FilterControl]:
    """Sheet-scoped pickers + cross-sheet date / transfer-type carryover.

    All five controls are CrossSheet — the underlying filter groups are
    scoped to both Today's Exceptions and Exceptions Trends, and AWS
    requires every control bound to a multi-sheet filter (with
    DefaultFilterControlConfiguration) to inherit that default rather
    than redefine its own widget.
    """
    del cfg
    return [
        _date_range_control("todays-exc"),
        _transfer_type_control("todays-exc"),
        _cross_sheet_control(
            "todays-exc", "check-type", "filter-ar-todays-exc-check-type",
        ),
        _cross_sheet_control(
            "todays-exc", "account", "filter-ar-todays-exc-account",
        ),
        _cross_sheet_control(
            "todays-exc", "aging", "filter-ar-todays-exc-aging",
        ),
        _cross_sheet_control(
            "todays-exc", "is-late", "filter-ar-todays-exc-is-late",
        ),
    ]


def build_exceptions_trends_controls(cfg: Config) -> list[FilterControl]:
    """Trend-sheet pickers — same set as Today's Exceptions but as
    CrossSheet controls, so a pick on either sheet propagates.

    Date range and transfer type are already CrossSheet (shared across
    all AR tabs); the three unified-dataset filters are also CrossSheet
    here because the underlying filter groups are scoped to both sheets.
    """
    del cfg
    return [
        _date_range_control("exc-trends"),
        _transfer_type_control("exc-trends"),
        _cross_sheet_control(
            "exc-trends", "check-type", "filter-ar-todays-exc-check-type",
        ),
        _cross_sheet_control(
            "exc-trends", "account", "filter-ar-todays-exc-account",
        ),
        _cross_sheet_control(
            "exc-trends", "aging", "filter-ar-todays-exc-aging",
        ),
        _cross_sheet_control(
            "exc-trends", "is-late", "filter-ar-todays-exc-is-late",
        ),
    ]


# ---------------------------------------------------------------------------
# Daily Statement (Phase I.2) — account + date pickers
# ---------------------------------------------------------------------------

def _daily_statement_account_filter_group() -> FilterGroup:
    """Account picker scoped to the Daily Statement sheet.

    Parameter-bound to ``pArDsAccountId`` so both the SINGLE_SELECT
    dropdown and the right-click drill from the Balances sub-ledger
    table route through the same parameter. CrossDataset=ALL_DATASETS
    so the filter applies to both the summary (KPIs) and transactions
    (detail table) datasets — both expose ``account_id``.

    NullOption is NON_NULLS_ONLY: there is no "all accounts" statement
    that makes sense (KPIs would aggregate across unrelated accounts).
    On first load, before the user picks an account or arrives via the
    right-click drill, every visual renders empty — the controls panel
    cues the next move.
    """
    return FilterGroup(
        FilterGroupId=FG_AR_DS_ACCOUNT,
        CrossDataset=FilterGroup.ALL_DATASETS,
        ScopeConfiguration=_selected_sheets_scope([SHEET_AR_DAILY_STATEMENT]),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                CategoryFilter=CategoryFilter(
                    FilterId="filter-ar-ds-account",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_AR_DAILY_STATEMENT_SUMMARY,
                        ColumnName="account_id",
                    ),
                    Configuration=CategoryFilterConfiguration(
                        CustomFilterConfiguration={
                            "MatchOperator": "EQUALS",
                            "ParameterName": P_AR_DS_ACCOUNT.name,
                            "NullOption": "NON_NULLS_ONLY",
                        },
                    ),
                ),
            ),
        ],
    )


def _daily_statement_date_filter_group() -> FilterGroup:
    """Single-day balance_date picker scoped to the Daily Statement sheet.

    Parameter-bound to ``pArDsBalanceDate`` so both the SINGLE_VALUED
    date picker and the right-click drill from Balances route through
    the same parameter. The parameter declares a RollingDate default of
    today, which the picker inherits on first load. SINGLE_VALUED date
    pickers must pair with TimeEqualityFilter (TimeRangeFilter renders
    broken in the UI).
    """
    return FilterGroup(
        FilterGroupId=FG_AR_DS_BALANCE_DATE,
        CrossDataset=FilterGroup.ALL_DATASETS,
        ScopeConfiguration=_selected_sheets_scope([SHEET_AR_DAILY_STATEMENT]),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                TimeEqualityFilter=TimeEqualityFilter(
                    FilterId="filter-ar-ds-balance-date",
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_AR_DAILY_STATEMENT_SUMMARY,
                        ColumnName="balance_date",
                    ),
                    ParameterName=P_AR_DS_BALANCE_DATE.name,
                    TimeGranularity="DAY",
                ),
            ),
        ],
    )


def build_daily_statement_parameter_controls(cfg: Config) -> list[ParameterControl]:
    """Daily Statement sheet pickers — bound to parameters, not filters.

    QuickSight disables a regular FilterControl whose backing filter is
    parameter-bound (the UI shows "this control was disabled because
    the filter is using parameters"). The right widget for a parameter-
    bound filter is a ParameterControl that writes the parameter
    directly; the filter then responds to the parameter value.

    Account dropdown values come from the daily-statement-summary
    dataset's ``account_id`` column. The link query bypasses the
    sheet's own parameter-bound filter, so users see every available
    account on first load — not the empty slice that would otherwise
    result from NullOption=NON_NULLS_ONLY.
    """
    del cfg
    return [
        ParameterControl(
            Dropdown=ParameterDropDownControl(
                ParameterControlId="ctrl-ar-ds-account",
                Title="Account",
                SourceParameterName=P_AR_DS_ACCOUNT.name,
                Type="SINGLE_SELECT",
                SelectableValues={
                    "LinkToDataSetColumn": {
                        "DataSetIdentifier": DS_AR_DAILY_STATEMENT_SUMMARY,
                        "ColumnName": "account_id",
                    },
                },
            ),
        ),
        ParameterControl(
            DateTimePicker=ParameterDateTimePickerControl(
                ParameterControlId="ctrl-ar-ds-balance-date",
                Title="Balance Date",
                SourceParameterName=P_AR_DS_BALANCE_DATE.name,
            ),
        ),
    ]
