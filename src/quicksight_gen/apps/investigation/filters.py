"""Investigation filter groups + sheet controls.

K.4.3 ships the Recipient Fanout sheet's filter groups: a date-range
window on ``posted_at`` and a fanout threshold on the analysis-level
``recipient_distinct_sender_count`` calc field. The threshold is
parameter-bound so the sheet ships with a slider control rather than a
typed number — analysts triage by dragging.

K.4.4 ships the Volume Anomalies sheet's filter groups: a date-range
window on ``window_end`` and a σ threshold on ``z_score``. The sigma
filter is scoped SELECTED_VISUALS to exclude the distribution bar
chart — the chart's job is to show the full population so analysts can
see where the threshold cutoff lies in the shape.

K.4.5 will add the Money Trail sheet's controls.
"""

from __future__ import annotations

from quicksight_gen.apps.investigation.constants import (
    CF_INV_FANOUT_DISTINCT_SENDERS,
    DS_INV_RECIPIENT_FANOUT,
    DS_INV_VOLUME_ANOMALIES,
    FG_INV_ANOMALIES_SIGMA,
    FG_INV_ANOMALIES_WINDOW,
    FG_INV_FANOUT_THRESHOLD,
    FG_INV_FANOUT_WINDOW,
    P_INV_ANOMALIES_SIGMA,
    P_INV_FANOUT_THRESHOLD,
    SHEET_INV_ANOMALIES,
    SHEET_INV_FANOUT,
    V_INV_ANOMALIES_KPI_FLAGGED,
    V_INV_ANOMALIES_TABLE,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.ids import SheetId
from quicksight_gen.common.models import (
    ColumnIdentifier,
    Filter,
    FilterControl,
    FilterDateTimePickerControl,
    FilterGroup,
    FilterScopeConfiguration,
    IntegerParameterDeclaration,
    NumericRangeFilter,
    NumericRangeFilterValue,
    ParameterControl,
    ParameterDeclaration,
    ParameterSliderControl,
    SelectedSheetsFilterScopeConfiguration,
    SheetVisualScopingConfiguration,
    TimeRangeFilter,
)


# Default fanout threshold — chosen so the demo seed in K.4.6 surfaces a
# handful of accounts. Analysts drag the slider up to narrow the table
# to the genuinely-interesting tail.
DEFAULT_FANOUT_THRESHOLD = 5

# Slider bounds. Anything below 2 isn't a fanout (one sender = a single
# bilateral relationship, not a funnel); anything above 20 is so far
# into the tail that aggregation collapses it to a handful of rows
# regardless of the seed.
SLIDER_MIN = 1
SLIDER_MAX = 20

# Default σ threshold for Volume Anomalies — 2σ matches the analyst
# convention for "worth a second look". Anything below 1 floods the
# table with normal traffic; above 4 hides genuinely large spikes.
DEFAULT_ANOMALIES_SIGMA = 2
SIGMA_SLIDER_MIN = 1
SIGMA_SLIDER_MAX = 4

# Filter / control IDs — kept as module-level constants so analysis.py
# can wire parameter declarations against the same names.
FILTER_INV_FANOUT_WINDOW = "filter-inv-fanout-window"
FILTER_INV_FANOUT_THRESHOLD = "filter-inv-fanout-threshold"
CTRL_INV_FANOUT_WINDOW = "ctrl-inv-fanout-window"
CTRL_INV_FANOUT_THRESHOLD = "ctrl-inv-fanout-threshold"

FILTER_INV_ANOMALIES_WINDOW = "filter-inv-anomalies-window"
FILTER_INV_ANOMALIES_SIGMA = "filter-inv-anomalies-sigma"
CTRL_INV_ANOMALIES_WINDOW = "ctrl-inv-anomalies-window"
CTRL_INV_ANOMALIES_SIGMA = "ctrl-inv-anomalies-sigma"


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


def _selected_visuals_scope(
    sheet_id: SheetId, visual_ids: list[str],
) -> FilterScopeConfiguration:
    """Scope a filter to a specific subset of visuals on one sheet.

    Used by K.4.4's σ threshold so the distribution chart sees the full
    population while the KPI + flagged table see only the cutoff tail.
    """
    return FilterScopeConfiguration(
        SelectedSheets=SelectedSheetsFilterScopeConfiguration(
            SheetVisualScopingConfigurations=[
                SheetVisualScopingConfiguration(
                    SheetId=sheet_id,
                    Scope=SheetVisualScopingConfiguration.SELECTED_VISUALS,
                    VisualIds=visual_ids,
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Filter groups
# ---------------------------------------------------------------------------

def _fanout_window_filter_group() -> FilterGroup:
    """Date-range window on ``posted_at`` for the Recipient Fanout sheet.

    Single-sheet scope, so the filter must NOT carry
    DefaultFilterControlConfiguration — the sheet's direct
    FilterControls list provides the widget directly. (Same rule as AR's
    single-sheet category filters.)
    """
    return FilterGroup(
        FilterGroupId=FG_INV_FANOUT_WINDOW,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_selected_sheets_scope([SHEET_INV_FANOUT]),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId=FILTER_INV_FANOUT_WINDOW,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_INV_RECIPIENT_FANOUT,
                        ColumnName="posted_at",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    TimeGranularity="DAY",
                ),
            ),
        ],
    )


def _fanout_threshold_filter_group() -> FilterGroup:
    """Threshold filter on the distinct-sender calc field.

    Bound to the integer parameter ``pInvFanoutThreshold``: only rows
    whose recipient's distinct-sender count is at least the threshold
    survive. Calc field is declared at the analysis level (see
    analysis.py); the filter references it by name on the same dataset.

    Min-only — there is no upper bound on "interesting" fanout.
    IncludeMinimum=True so the slider value matches the visible cutoff
    (drag to 5 → 5+ senders survive).
    """
    return FilterGroup(
        FilterGroupId=FG_INV_FANOUT_THRESHOLD,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_selected_sheets_scope([SHEET_INV_FANOUT]),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                NumericRangeFilter=NumericRangeFilter(
                    FilterId=FILTER_INV_FANOUT_THRESHOLD,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_INV_RECIPIENT_FANOUT,
                        ColumnName=CF_INV_FANOUT_DISTINCT_SENDERS,
                    ),
                    NullOption="NON_NULLS_ONLY",
                    RangeMinimum=NumericRangeFilterValue(
                        Parameter=P_INV_FANOUT_THRESHOLD,
                    ),
                    IncludeMinimum=True,
                ),
            ),
        ],
    )


def _anomalies_window_filter_group() -> FilterGroup:
    """Date-range window on ``window_end`` for the Volume Anomalies sheet.

    Scoped ALL_VISUALS — both the distribution chart and the flagged
    table should respect the date range. Otherwise the chart's shape
    would float free of what the analyst is investigating.
    """
    return FilterGroup(
        FilterGroupId=FG_INV_ANOMALIES_WINDOW,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_selected_sheets_scope([SHEET_INV_ANOMALIES]),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                TimeRangeFilter=TimeRangeFilter(
                    FilterId=FILTER_INV_ANOMALIES_WINDOW,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_INV_VOLUME_ANOMALIES,
                        ColumnName="window_end",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    TimeGranularity="DAY",
                ),
            ),
        ],
    )


def _anomalies_sigma_filter_group() -> FilterGroup:
    """σ threshold on ``z_score`` — KPI + flagged table only.

    Scope is SELECTED_VISUALS, intentionally leaving the distribution
    bar chart unfiltered. The chart has to render the full population
    so the analyst can see where the slider's cutoff lies in the shape;
    if the chart respected the threshold the bars would always show only
    the tail and the analyst would lose the reference frame.

    Min-only filter, IncludeMinimum=True so a slider value of 2 means
    "z_score ≥ 2σ survives".
    """
    return FilterGroup(
        FilterGroupId=FG_INV_ANOMALIES_SIGMA,
        CrossDataset=FilterGroup.SINGLE_DATASET,
        ScopeConfiguration=_selected_visuals_scope(
            SHEET_INV_ANOMALIES,
            [V_INV_ANOMALIES_KPI_FLAGGED, V_INV_ANOMALIES_TABLE],
        ),
        Status=FilterGroup.ENABLED,
        Filters=[
            Filter(
                NumericRangeFilter=NumericRangeFilter(
                    FilterId=FILTER_INV_ANOMALIES_SIGMA,
                    Column=ColumnIdentifier(
                        DataSetIdentifier=DS_INV_VOLUME_ANOMALIES,
                        ColumnName="z_score",
                    ),
                    NullOption="NON_NULLS_ONLY",
                    RangeMinimum=NumericRangeFilterValue(
                        Parameter=P_INV_ANOMALIES_SIGMA,
                    ),
                    IncludeMinimum=True,
                ),
            ),
        ],
    )


def build_filter_groups(cfg: Config) -> list[FilterGroup]:
    del cfg
    return [
        _fanout_window_filter_group(),
        _fanout_threshold_filter_group(),
        _anomalies_window_filter_group(),
        _anomalies_sigma_filter_group(),
    ]


# ---------------------------------------------------------------------------
# Parameter declarations
# ---------------------------------------------------------------------------

def build_parameter_declarations(cfg: Config) -> list[ParameterDeclaration]:
    del cfg
    return [
        ParameterDeclaration(
            IntegerParameterDeclaration=IntegerParameterDeclaration(
                ParameterValueType="SINGLE_VALUED",
                Name=P_INV_FANOUT_THRESHOLD,
                DefaultValues={"StaticValues": [DEFAULT_FANOUT_THRESHOLD]},
            ),
        ),
        ParameterDeclaration(
            IntegerParameterDeclaration=IntegerParameterDeclaration(
                ParameterValueType="SINGLE_VALUED",
                Name=P_INV_ANOMALIES_SIGMA,
                DefaultValues={"StaticValues": [DEFAULT_ANOMALIES_SIGMA]},
            ),
        ),
    ]


# ---------------------------------------------------------------------------
# Sheet controls
# ---------------------------------------------------------------------------

def _date_range_control() -> FilterControl:
    """DATE_RANGE picker for the window filter.

    Single-sheet filter without DefaultFilterControlConfiguration — the
    widget has to be a direct DateTimePicker, not a CrossSheet control.
    """
    return FilterControl(
        DateTimePicker=FilterDateTimePickerControl(
            FilterControlId=CTRL_INV_FANOUT_WINDOW,
            Title="Date Range",
            SourceFilterId=FILTER_INV_FANOUT_WINDOW,
            Type="DATE_RANGE",
        ),
    )


def _threshold_slider_control() -> ParameterControl:
    return ParameterControl(
        Slider=ParameterSliderControl(
            ParameterControlId=CTRL_INV_FANOUT_THRESHOLD,
            Title="Min distinct senders",
            SourceParameterName=P_INV_FANOUT_THRESHOLD,
            MinimumValue=SLIDER_MIN,
            MaximumValue=SLIDER_MAX,
            StepSize=1,
        ),
    )


def build_fanout_filter_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [_date_range_control()]


def build_fanout_parameter_controls(cfg: Config) -> list[ParameterControl]:
    del cfg
    return [_threshold_slider_control()]


def _anomalies_date_range_control() -> FilterControl:
    return FilterControl(
        DateTimePicker=FilterDateTimePickerControl(
            FilterControlId=CTRL_INV_ANOMALIES_WINDOW,
            Title="Window End Date",
            SourceFilterId=FILTER_INV_ANOMALIES_WINDOW,
            Type="DATE_RANGE",
        ),
    )


def _sigma_slider_control() -> ParameterControl:
    return ParameterControl(
        Slider=ParameterSliderControl(
            ParameterControlId=CTRL_INV_ANOMALIES_SIGMA,
            Title="Min sigma",
            SourceParameterName=P_INV_ANOMALIES_SIGMA,
            MinimumValue=SIGMA_SLIDER_MIN,
            MaximumValue=SIGMA_SLIDER_MAX,
            StepSize=1,
        ),
    )


def build_anomalies_filter_controls(cfg: Config) -> list[FilterControl]:
    del cfg
    return [_anomalies_date_range_control()]


def build_anomalies_parameter_controls(cfg: Config) -> list[ParameterControl]:
    del cfg
    return [_sigma_slider_control()]
