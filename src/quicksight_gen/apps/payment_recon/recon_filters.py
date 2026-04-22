"""Filter groups and controls for the Payment Reconciliation sheet.

Defines three single-dataset filters with corresponding UI controls:
- Date range picker        -> recon sheet
- Match status dropdown    -> recon sheet
- External system dropdown -> recon sheet

All filters use SINGLE_DATASET + single-sheet scope so that QuickSight
treats them as sheet-local controls (no DefaultFilterControlConfiguration
required, no CrossSheet control type needed).
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.apps.payment_recon.constants import (
    DS_PAYMENT_RECON,
    FG_PR_RECON_DATE_RANGE,
    FG_PR_RECON_EXTERNAL_SYSTEM,
    FG_PR_RECON_KPI_LATE_ONLY,
    FG_PR_RECON_KPI_MATCHED_ONLY,
    FG_PR_RECON_KPI_UNMATCHED_ONLY,
    FG_PR_RECON_MATCH_STATUS,
    SHEET_PAYMENT_RECON,
    V_PR_RECON_KPI_LATE_COUNT,
    V_PR_RECON_KPI_MATCHED_AMOUNT,
    V_PR_RECON_KPI_UNMATCHED_AMOUNT,
)
from quicksight_gen.apps.payment_recon.filters import _visual_scoped_pinned_filter_group
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
                    Scope=SheetVisualScopingConfiguration.ALL_VISUALS,
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
        FilterGroupId=FG_PR_RECON_DATE_RANGE,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_recon_scope(),
        Status=FilterGroup.ENABLED,
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
        FilterGroupId=FG_PR_RECON_MATCH_STATUS,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_recon_scope(),
        Status=FilterGroup.ENABLED,
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
        FilterGroupId=FG_PR_RECON_EXTERNAL_SYSTEM,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_recon_scope(),
        Status=FilterGroup.ENABLED,
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


def build_recon_filter_groups(cfg: Config) -> list[FilterGroup]:
    """Return all filter groups for the Payment Reconciliation sheet."""
    del cfg
    return [
        _recon_date_range_filter_group(),
        _recon_match_status_filter_group(),
        _recon_external_system_filter_group(),
        # Visual-scoped pinned filters per KPI — the bar chart and
        # side-by-side tables on this sheet legitimately span all match
        # statuses, so the fix can't be sheet-wide.
        _visual_scoped_pinned_filter_group(
            FG_PR_RECON_KPI_LATE_ONLY,
            "filter-recon-kpi-late-only",
            SHEET_PAYMENT_RECON,
            [V_PR_RECON_KPI_LATE_COUNT],
            DS_PAYMENT_RECON,
            "match_status",
            ["late"],
        ),
        _visual_scoped_pinned_filter_group(
            FG_PR_RECON_KPI_MATCHED_ONLY,
            "filter-recon-kpi-matched-only",
            SHEET_PAYMENT_RECON,
            [V_PR_RECON_KPI_MATCHED_AMOUNT],
            DS_PAYMENT_RECON,
            "match_status",
            ["matched"],
        ),
        _visual_scoped_pinned_filter_group(
            FG_PR_RECON_KPI_UNMATCHED_ONLY,
            "filter-recon-kpi-unmatched-only",
            SHEET_PAYMENT_RECON,
            [V_PR_RECON_KPI_UNMATCHED_AMOUNT],
            DS_PAYMENT_RECON,
            "match_status",
            ["late", "not_yet_matched"],
        ),
    ]


# ---------------------------------------------------------------------------
# Filter controls (UI widgets on the recon sheet)
# ---------------------------------------------------------------------------

def build_recon_controls(cfg: Config) -> list[FilterControl]:
    """Controls for the Payment Reconciliation tab.

    Uses direct control types (DateTimePicker, Dropdown) rather than
    CrossSheet controls, since all filters are SINGLE_DATASET scoped to one sheet.
    """
    del cfg  # reserved for future per-config tuning
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
    ]
