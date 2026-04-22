"""Dataclass models mapping to AWS QuickSight API JSON structures.

Each top-level model (Theme, DataSet, Analysis) has a `to_aws_json()` method
that returns the exact dict shape expected by the corresponding AWS CLI command
(create-theme, create-data-set, create-analysis).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, ClassVar, Literal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_nones(obj: Any) -> Any:
    """Recursively remove keys with None values from dicts."""
    if isinstance(obj, dict):
        return {k: _strip_nones(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [_strip_nones(v) for v in obj]
    if isinstance(obj, Enum):
        return obj.value
    return obj


# ---------------------------------------------------------------------------
# Common / shared types
# ---------------------------------------------------------------------------

@dataclass
class ColumnIdentifier:
    DataSetIdentifier: str
    ColumnName: str


@dataclass
class CategoricalDimensionField:
    FieldId: str
    Column: ColumnIdentifier
    HierarchyId: str | None = None


@dataclass
class DateDimensionField:
    FieldId: str
    Column: ColumnIdentifier
    DateGranularity: str | None = None  # YEAR|QUARTER|MONTH|WEEK|DAY|HOUR|...
    HierarchyId: str | None = None


@dataclass
class NumericalDimensionField:
    FieldId: str
    Column: ColumnIdentifier
    HierarchyId: str | None = None


@dataclass
class DimensionField:
    """Union type — set exactly one."""
    CategoricalDimensionField: CategoricalDimensionField | None = None
    DateDimensionField: DateDimensionField | None = None
    NumericalDimensionField: NumericalDimensionField | None = None


@dataclass
class NumericalAggregationFunction:
    SimpleNumericalAggregation: str | None = None  # SUM|COUNT|AVG|MIN|MAX


@dataclass
class NumericalMeasureField:
    FieldId: str
    Column: ColumnIdentifier
    AggregationFunction: NumericalAggregationFunction | None = None


@dataclass
class CategoricalMeasureField:
    FieldId: str
    Column: ColumnIdentifier
    AggregationFunction: str | None = None  # COUNT|DISTINCT_COUNT


@dataclass
class DateMeasureField:
    FieldId: str
    Column: ColumnIdentifier
    AggregationFunction: str | None = None  # COUNT|DISTINCT_COUNT|MIN|MAX


@dataclass
class MeasureField:
    """Union type — set exactly one."""
    NumericalMeasureField: NumericalMeasureField | None = None
    CategoricalMeasureField: CategoricalMeasureField | None = None
    DateMeasureField: DateMeasureField | None = None


@dataclass
class VisualTitleLabelOptions:
    Visibility: str = "VISIBLE"  # VISIBLE|HIDDEN
    FormatText: dict[str, str] | None = None  # {"PlainText": "..."}


@dataclass
class VisualSubtitleLabelOptions:
    Visibility: str = "VISIBLE"
    FormatText: dict[str, str] | None = None


# ---------------------------------------------------------------------------
# Theme models
# ---------------------------------------------------------------------------

@dataclass
class DataColorPalette:
    Colors: list[str] | None = None
    EmptyFillColor: str | None = None
    MinMaxGradient: list[str] | None = None


@dataclass
class UIColorPalette:
    PrimaryBackground: str | None = None
    PrimaryForeground: str | None = None
    SecondaryBackground: str | None = None
    SecondaryForeground: str | None = None
    Accent: str | None = None
    AccentForeground: str | None = None
    Danger: str | None = None
    DangerForeground: str | None = None
    Warning: str | None = None
    WarningForeground: str | None = None
    Success: str | None = None
    SuccessForeground: str | None = None
    Dimension: str | None = None
    DimensionForeground: str | None = None
    Measure: str | None = None
    MeasureForeground: str | None = None


@dataclass
class TileBorder:
    Show: bool | None = None


@dataclass
class Tile:
    Border: TileBorder | None = None


@dataclass
class Gutter:
    Show: bool | None = None


@dataclass
class Margin:
    Show: bool | None = None


@dataclass
class TileLayout:
    Gutter: Gutter | None = None
    Margin: Margin | None = None


@dataclass
class SheetStyle:
    Tile: Tile | None = None
    TileLayout: TileLayout | None = None


@dataclass
class FontFamily:
    FontFamily: str


@dataclass
class Typography:
    FontFamilies: list[FontFamily] | None = None


@dataclass
class ThemeConfiguration:
    DataColorPalette: DataColorPalette | None = None
    UIColorPalette: UIColorPalette | None = None
    Sheet: SheetStyle | None = None
    Typography: Typography | None = None


@dataclass
class Tag:
    Key: str
    Value: str


@dataclass
class ResourcePermission:
    Principal: str
    Actions: list[str]


@dataclass
class Theme:
    AwsAccountId: str
    ThemeId: str
    Name: str
    BaseThemeId: str
    Configuration: ThemeConfiguration
    Permissions: list[ResourcePermission] | None = None
    Tags: list[Tag] | None = None
    VersionDescription: str | None = None

    def to_aws_json(self) -> dict[str, Any]:
        return _strip_nones(asdict(self))

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_aws_json(), indent=indent)


# ---------------------------------------------------------------------------
# DataSource models
# ---------------------------------------------------------------------------

@dataclass
class PostgreSqlParameters:
    Host: str
    Port: int
    Database: str


@dataclass
class DataSourceParameters:
    PostgreSqlParameters: PostgreSqlParameters | None = None


@dataclass
class CredentialPair:
    Username: str
    Password: str


@dataclass
class DataSourceCredentials:
    CredentialPair: CredentialPair | None = None


@dataclass
class SslProperties:
    DisableSsl: bool = False


@dataclass
class DataSource:
    AwsAccountId: str
    DataSourceId: str
    Name: str
    Type: str  # POSTGRESQL, MYSQL, etc.
    DataSourceParameters: DataSourceParameters
    Credentials: DataSourceCredentials | None = None
    SslProperties: SslProperties | None = None
    Permissions: list[ResourcePermission] | None = None
    Tags: list[Tag] | None = None

    def to_aws_json(self) -> dict[str, Any]:
        return _strip_nones(asdict(self))

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_aws_json(), indent=indent)


# ---------------------------------------------------------------------------
# DataSet models
# ---------------------------------------------------------------------------

@dataclass
class InputColumn:
    Name: str
    Type: str  # STRING|INTEGER|DECIMAL|DATETIME|BIT
    SubType: str | None = None


@dataclass
class CustomSql:
    Name: str
    DataSourceArn: str
    SqlQuery: str
    Columns: list[InputColumn]


@dataclass
class PhysicalTable:
    """Union type — set exactly one."""
    CustomSql: CustomSql | None = None


@dataclass
class LogicalTableSource:
    PhysicalTableId: str | None = None
    DataSetArn: str | None = None


@dataclass
class LogicalTable:
    Alias: str
    Source: LogicalTableSource
    DataTransforms: list[dict[str, Any]] | None = None


@dataclass
class DataSetUsageConfiguration:
    DisableUseAsDirectQuerySource: bool = False
    DisableUseAsImportedSource: bool = False


@dataclass
class DataSet:
    AwsAccountId: str
    DataSetId: str
    Name: str
    PhysicalTableMap: dict[str, PhysicalTable]
    ImportMode: str = "DIRECT_QUERY"  # DIRECT_QUERY|SPICE
    LogicalTableMap: dict[str, LogicalTable] | None = None
    DataSetUsageConfiguration: DataSetUsageConfiguration | None = None
    Permissions: list[ResourcePermission] | None = None
    Tags: list[Tag] | None = None

    def to_aws_json(self) -> dict[str, Any]:
        return _strip_nones(asdict(self))

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_aws_json(), indent=indent)


# ---------------------------------------------------------------------------
# Analysis models — Visuals
# ---------------------------------------------------------------------------

# -- Axis labels (shared by bar, pie, etc.) --

@dataclass
class AxisLabelOptions:
    """Label override for a single axis field."""
    CustomLabel: str | None = None


@dataclass
class ChartAxisLabelOptions:
    """Axis label options — list of per-field overrides plus visibility."""
    Visibility: str = "VISIBLE"  # VISIBLE|HIDDEN
    AxisLabelOptions: list[AxisLabelOptions] | None = None


# -- Bar chart --

@dataclass
class BarChartAggregatedFieldWells:
    Category: list[DimensionField] | None = None
    Values: list[MeasureField] | None = None
    Colors: list[DimensionField] | None = None


@dataclass
class BarChartFieldWells:
    BarChartAggregatedFieldWells: BarChartAggregatedFieldWells | None = None


@dataclass
class BarChartSortConfiguration:
    CategorySort: list[dict[str, Any]] | None = None


@dataclass
class BarChartConfiguration:
    FieldWells: BarChartFieldWells | None = None
    Orientation: str | None = None  # HORIZONTAL|VERTICAL
    BarsArrangement: str | None = None  # CLUSTERED|STACKED|STACKED_PERCENT
    SortConfiguration: BarChartSortConfiguration | None = None
    CategoryLabelOptions: ChartAxisLabelOptions | None = None
    ValueLabelOptions: ChartAxisLabelOptions | None = None
    ColorLabelOptions: ChartAxisLabelOptions | None = None


@dataclass
class BarChartVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: BarChartConfiguration | None = None
    Actions: list[VisualCustomAction] | None = None


# -- Pie chart --

@dataclass
class PieChartAggregatedFieldWells:
    Category: list[DimensionField] | None = None
    Values: list[MeasureField] | None = None


@dataclass
class PieChartFieldWells:
    PieChartAggregatedFieldWells: PieChartAggregatedFieldWells | None = None


@dataclass
class DonutOptions:
    ArcOptions: dict[str, str] | None = None  # {"ArcThickness": "MEDIUM"}


@dataclass
class PieChartConfiguration:
    FieldWells: PieChartFieldWells | None = None
    DonutOptions: DonutOptions | None = None
    CategoryLabelOptions: ChartAxisLabelOptions | None = None
    ValueLabelOptions: ChartAxisLabelOptions | None = None


@dataclass
class PieChartVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: PieChartConfiguration | None = None
    Actions: list[VisualCustomAction] | None = None


# -- KPI --

@dataclass
class KPIFieldWells:
    Values: list[MeasureField] | None = None
    TargetValues: list[MeasureField] | None = None
    TrendGroups: list[DimensionField] | None = None


@dataclass
class KPIOptions:
    PrimaryValueDisplayType: str | None = None  # HIDDEN|COMPARISON|ACTUAL


@dataclass
class KPIConfiguration:
    FieldWells: KPIFieldWells | None = None
    KPIOptions: KPIOptions | None = None


@dataclass
class KPIVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: KPIConfiguration | None = None


# -- Table --

@dataclass
class TableAggregatedFieldWells:
    GroupBy: list[DimensionField] | None = None
    Values: list[MeasureField] | None = None


@dataclass
class TableUnaggregatedFieldWells:
    Values: list[dict[str, Any]] | None = None  # UnaggregatedField list


@dataclass
class TableFieldWells:
    TableAggregatedFieldWells: TableAggregatedFieldWells | None = None
    TableUnaggregatedFieldWells: TableUnaggregatedFieldWells | None = None


@dataclass
class TableOptions:
    HeaderStyle: dict[str, Any] | None = None
    CellStyle: dict[str, Any] | None = None


@dataclass
class TableConfiguration:
    FieldWells: TableFieldWells | None = None
    SortConfiguration: dict[str, Any] | None = None
    TableOptions: TableOptions | None = None


@dataclass
class TableVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: TableConfiguration | None = None
    Actions: list[VisualCustomAction] | None = None
    ConditionalFormatting: dict[str, Any] | None = None


# -- Sankey diagram --

@dataclass
class SankeyDiagramAggregatedFieldWells:
    Source: list[DimensionField] | None = None
    Destination: list[DimensionField] | None = None
    Weight: list[MeasureField] | None = None


@dataclass
class SankeyDiagramFieldWells:
    SankeyDiagramAggregatedFieldWells: SankeyDiagramAggregatedFieldWells | None = None


@dataclass
class SankeyDiagramSortConfiguration:
    # ItemsLimitConfiguration shape: {"ItemsLimit": int, "OtherCategories": "INCLUDE"|"EXCLUDE"}.
    # Caps how many distinct source / destination nodes the diagram
    # renders; over-cap entries roll up into "Other" or get dropped.
    WeightSort: list[dict[str, Any]] | None = None
    SourceItemsLimit: dict[str, Any] | None = None
    DestinationItemsLimit: dict[str, Any] | None = None


@dataclass
class SankeyDiagramChartConfiguration:
    FieldWells: SankeyDiagramFieldWells | None = None
    SortConfiguration: SankeyDiagramSortConfiguration | None = None
    DataLabels: dict[str, Any] | None = None


@dataclass
class SankeyDiagramVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: SankeyDiagramChartConfiguration | None = None
    Actions: list[VisualCustomAction] | None = None


# -- Custom actions (drill-down navigation, filtering) --

@dataclass
class LocalNavigationConfiguration:
    TargetSheetId: str


@dataclass
class CustomActionNavigationOperation:
    LocalNavigationConfiguration: LocalNavigationConfiguration


@dataclass
class CustomActionSetParametersOperation:
    ParameterValueConfigurations: list[dict[str, Any]]


@dataclass
class SameSheetTargetVisualConfiguration:
    TargetVisualOptions: str | None = None  # ALL_VISUALS
    TargetVisuals: list[str] | None = None


@dataclass
class FilterOperationTargetVisualsConfiguration:
    SameSheetTargetVisualConfiguration: SameSheetTargetVisualConfiguration | None = None


@dataclass
class FilterOperationSelectedFieldsConfiguration:
    SelectedFieldOptions: str | None = None  # ALL_FIELDS
    SelectedFields: list[str] | None = None
    SelectedColumns: list[ColumnIdentifier] | None = None


@dataclass
class CustomActionFilterOperation:
    SelectedFieldsConfiguration: FilterOperationSelectedFieldsConfiguration
    TargetVisualsConfiguration: FilterOperationTargetVisualsConfiguration


@dataclass
class VisualCustomActionOperation:
    """Union type — set exactly one."""
    NavigationOperation: CustomActionNavigationOperation | None = None
    SetParametersOperation: CustomActionSetParametersOperation | None = None
    FilterOperation: CustomActionFilterOperation | None = None


@dataclass
class VisualCustomAction:
    # Trigger constants — prefer VisualCustomAction.DATA_POINT_CLICK
    # over the bare string literal at call sites.
    DATA_POINT_CLICK: ClassVar[Literal["DATA_POINT_CLICK"]] = "DATA_POINT_CLICK"
    DATA_POINT_MENU: ClassVar[Literal["DATA_POINT_MENU"]] = "DATA_POINT_MENU"
    # Status constants.
    ENABLED: ClassVar[Literal["ENABLED"]] = "ENABLED"
    DISABLED: ClassVar[Literal["DISABLED"]] = "DISABLED"

    CustomActionId: str
    Name: str
    Trigger: Literal["DATA_POINT_CLICK", "DATA_POINT_MENU"]
    ActionOperations: list[VisualCustomActionOperation]
    Status: Literal["ENABLED", "DISABLED"] = "ENABLED"


# -- Visual union --

@dataclass
class Visual:
    """Union type — set exactly one."""
    BarChartVisual: BarChartVisual | None = None
    PieChartVisual: PieChartVisual | None = None
    KPIVisual: KPIVisual | None = None
    TableVisual: TableVisual | None = None
    SankeyDiagramVisual: SankeyDiagramVisual | None = None


# ---------------------------------------------------------------------------
# Analysis models — Filters
# ---------------------------------------------------------------------------

@dataclass
class DefaultDateTimePickerControlOptions:
    Type: str = "DATE_RANGE"  # SINGLE_VALUED|DATE_RANGE
    CommitMode: str | None = None  # AUTO|MANUAL


@dataclass
class DefaultDropdownControlOptions:
    Type: str = "MULTI_SELECT"  # MULTI_SELECT|SINGLE_SELECT
    CommitMode: str | None = None  # AUTO|MANUAL


@dataclass
class DefaultSliderControlOptions:
    MaximumValue: float
    MinimumValue: float
    StepSize: float
    Type: str = "SINGLE_POINT"  # SINGLE_POINT|RANGE


@dataclass
class DefaultFilterControlOptions:
    """Union type — set exactly one."""
    DefaultDateTimePickerOptions: DefaultDateTimePickerControlOptions | None = None
    DefaultDropdownOptions: DefaultDropdownControlOptions | None = None
    DefaultSliderOptions: DefaultSliderControlOptions | None = None


@dataclass
class DefaultFilterControlConfiguration:
    Title: str
    ControlOptions: DefaultFilterControlOptions


@dataclass
class CategoryFilterConfiguration:
    FilterListConfiguration: dict[str, Any] | None = None
    CustomFilterListConfiguration: dict[str, Any] | None = None
    CustomFilterConfiguration: dict[str, Any] | None = None


@dataclass
class CategoryFilter:
    FilterId: str
    Column: ColumnIdentifier
    Configuration: CategoryFilterConfiguration
    DefaultFilterControlConfiguration: DefaultFilterControlConfiguration | None = None


@dataclass
class TimeRangeFilter:
    FilterId: str
    Column: ColumnIdentifier
    NullOption: str = "NON_NULLS_ONLY"  # ALL_VALUES|NULLS_ONLY|NON_NULLS_ONLY
    TimeGranularity: str | None = None
    RangeMinimumValue: dict[str, Any] | None = None
    RangeMaximumValue: dict[str, Any] | None = None
    IncludeMinimum: bool | None = None
    IncludeMaximum: bool | None = None
    DefaultFilterControlConfiguration: DefaultFilterControlConfiguration | None = None


@dataclass
class TimeEqualityFilter:
    FilterId: str
    Column: ColumnIdentifier
    Value: str | None = None  # ISO datetime; pair with TimeGranularity
    ParameterName: str | None = None
    TimeGranularity: str | None = None
    RollingDate: dict[str, Any] | None = None
    DefaultFilterControlConfiguration: DefaultFilterControlConfiguration | None = None


@dataclass
class NumericRangeFilterValue:
    """Set exactly one — a literal bound or a parameter binding."""
    StaticValue: float | None = None
    Parameter: str | None = None  # name of an IntegerParameter / DecimalParameter


@dataclass
class NumericRangeFilter:
    FilterId: str
    Column: ColumnIdentifier
    NullOption: str = "NON_NULLS_ONLY"
    RangeMinimum: NumericRangeFilterValue | None = None
    RangeMaximum: NumericRangeFilterValue | None = None
    IncludeMinimum: bool | None = None
    IncludeMaximum: bool | None = None
    DefaultFilterControlConfiguration: DefaultFilterControlConfiguration | None = None


@dataclass
class Filter:
    """Union type — set exactly one."""
    CategoryFilter: CategoryFilter | None = None
    TimeRangeFilter: TimeRangeFilter | None = None
    TimeEqualityFilter: TimeEqualityFilter | None = None
    NumericRangeFilter: NumericRangeFilter | None = None


@dataclass
class SheetVisualScopingConfiguration:
    # Scope constants — prefer SheetVisualScopingConfiguration.ALL_VISUALS
    # over the bare string literal at call sites.
    ALL_VISUALS: ClassVar[Literal["ALL_VISUALS"]] = "ALL_VISUALS"
    SELECTED_VISUALS: ClassVar[Literal["SELECTED_VISUALS"]] = "SELECTED_VISUALS"

    SheetId: str
    Scope: Literal["ALL_VISUALS", "SELECTED_VISUALS"]
    VisualIds: list[str] | None = None


@dataclass
class SelectedSheetsFilterScopeConfiguration:
    SheetVisualScopingConfigurations: list[SheetVisualScopingConfiguration] | None = None


@dataclass
class AllSheetsFilterScopeConfiguration:
    pass  # empty object — presence alone means "all sheets"


@dataclass
class FilterScopeConfiguration:
    """Union type — set exactly one."""
    AllSheets: AllSheetsFilterScopeConfiguration | None = None
    SelectedSheets: SelectedSheetsFilterScopeConfiguration | None = None


@dataclass
class FilterGroup:
    # CrossDataset constants — prefer FilterGroup.SINGLE_DATASET over the
    # bare string literal at call sites.
    SINGLE_DATASET: ClassVar[Literal["SINGLE_DATASET"]] = "SINGLE_DATASET"
    ALL_DATASETS: ClassVar[Literal["ALL_DATASETS"]] = "ALL_DATASETS"
    # Status constants.
    ENABLED: ClassVar[Literal["ENABLED"]] = "ENABLED"
    DISABLED: ClassVar[Literal["DISABLED"]] = "DISABLED"

    FilterGroupId: str
    Filters: list[Filter]
    ScopeConfiguration: FilterScopeConfiguration
    CrossDataset: Literal["SINGLE_DATASET", "ALL_DATASETS"] = "SINGLE_DATASET"
    Status: Literal["ENABLED", "DISABLED"] | None = None


# ---------------------------------------------------------------------------
# Analysis models — Filter controls
# ---------------------------------------------------------------------------

@dataclass
class FilterDropDownControl:
    FilterControlId: str
    Title: str
    SourceFilterId: str
    Type: str | None = None  # MULTI_SELECT|SINGLE_SELECT
    # FilterSelectableValues shape: {"Values": [str, ...]}. Restricts the
    # dropdown menu to a fixed list of options instead of auto-populating
    # from the column. Useful for toggle-like controls where only one
    # option (e.g. "Unsettled") should be pickable.
    SelectableValues: dict[str, Any] | None = None


@dataclass
class FilterDateTimePickerControl:
    FilterControlId: str
    Title: str
    SourceFilterId: str
    Type: str | None = None  # SINGLE_VALUED|DATE_RANGE


@dataclass
class FilterSliderControl:
    FilterControlId: str
    Title: str
    SourceFilterId: str
    MaximumValue: float
    MinimumValue: float
    StepSize: float
    Type: str | None = None  # SINGLE_POINT|RANGE


@dataclass
class FilterCrossSheetControl:
    FilterControlId: str
    SourceFilterId: str


@dataclass
class FilterControl:
    """Union type — set exactly one."""
    Dropdown: FilterDropDownControl | None = None
    DateTimePicker: FilterDateTimePickerControl | None = None
    Slider: FilterSliderControl | None = None
    CrossSheet: FilterCrossSheetControl | None = None


# ---------------------------------------------------------------------------
# Analysis models — Parameter controls
#
# QuickSight disables a regular FilterControl whose backing filter is
# parameter-bound (CustomFilterConfiguration with ParameterName) — the UI
# shows "this control was disabled because the filter is using
# parameters". The right widget for that case is a ParameterControl
# bound directly to the parameter; the parameter-bound filter then
# responds to the parameter value the control writes.
# ---------------------------------------------------------------------------

@dataclass
class ParameterDropDownControl:
    ParameterControlId: str
    Title: str
    SourceParameterName: str
    Type: str | None = None  # SINGLE_SELECT|MULTI_SELECT
    # ParameterSelectableValues shape: either {"Values": [str, ...]}
    # for a static list or {"LinkToDataSetColumn": {"DataSetIdentifier",
    # "ColumnName"}} for an auto-populated list. The link query bypasses
    # the sheet's parameter-bound filter so users see every available
    # option, not the filtered slice.
    SelectableValues: dict[str, Any] | None = None


@dataclass
class ParameterDateTimePickerControl:
    ParameterControlId: str
    Title: str
    SourceParameterName: str


@dataclass
class ParameterSliderControl:
    ParameterControlId: str
    Title: str
    SourceParameterName: str
    MinimumValue: float
    MaximumValue: float
    StepSize: float


@dataclass
class ParameterControl:
    """Union type — set exactly one."""
    Dropdown: ParameterDropDownControl | None = None
    DateTimePicker: ParameterDateTimePickerControl | None = None
    Slider: ParameterSliderControl | None = None


# ---------------------------------------------------------------------------
# Analysis models — Sheet & Layout
# ---------------------------------------------------------------------------

@dataclass
class FreeFormLayoutElement:
    # ElementType constants — prefer FreeFormLayoutElement.VISUAL over
    # the bare string literal at call sites.
    VISUAL: ClassVar[Literal["VISUAL"]] = "VISUAL"
    FILTER_CONTROL: ClassVar[Literal["FILTER_CONTROL"]] = "FILTER_CONTROL"
    PARAMETER_CONTROL: ClassVar[Literal["PARAMETER_CONTROL"]] = "PARAMETER_CONTROL"
    TEXT_BOX: ClassVar[Literal["TEXT_BOX"]] = "TEXT_BOX"
    IMAGE: ClassVar[Literal["IMAGE"]] = "IMAGE"

    ElementId: str
    ElementType: Literal[
        "VISUAL", "FILTER_CONTROL", "PARAMETER_CONTROL", "TEXT_BOX", "IMAGE"
    ]
    XAxisLocation: str  # pixels as string
    YAxisLocation: str
    Width: str
    Height: str
    Visibility: str = "VISIBLE"


@dataclass
class FreeFormLayoutConfiguration:
    Elements: list[FreeFormLayoutElement]


@dataclass
class GridLayoutElement:
    # ElementType constants — prefer GridLayoutElement.VISUAL over the
    # bare string literal at call sites.
    VISUAL: ClassVar[Literal["VISUAL"]] = "VISUAL"
    FILTER_CONTROL: ClassVar[Literal["FILTER_CONTROL"]] = "FILTER_CONTROL"
    PARAMETER_CONTROL: ClassVar[Literal["PARAMETER_CONTROL"]] = "PARAMETER_CONTROL"
    TEXT_BOX: ClassVar[Literal["TEXT_BOX"]] = "TEXT_BOX"
    IMAGE: ClassVar[Literal["IMAGE"]] = "IMAGE"

    ElementId: str
    ElementType: Literal[
        "VISUAL", "FILTER_CONTROL", "PARAMETER_CONTROL", "TEXT_BOX", "IMAGE"
    ]
    ColumnSpan: int
    RowSpan: int
    ColumnIndex: int | None = None
    RowIndex: int | None = None


@dataclass
class GridLayoutConfiguration:
    Elements: list[GridLayoutElement]


@dataclass
class LayoutConfiguration:
    """Union type — set exactly one."""
    GridLayout: GridLayoutConfiguration | None = None
    FreeFormLayout: FreeFormLayoutConfiguration | None = None


@dataclass
class Layout:
    Configuration: LayoutConfiguration


@dataclass
class SheetTextBox:
    SheetTextBoxId: str
    Content: str  # rich-text HTML


@dataclass
class SheetDefinition:
    SheetId: str
    Name: str | None = None
    Title: str | None = None
    Description: str | None = None
    ContentType: str = "INTERACTIVE"  # INTERACTIVE|PAGINATED
    Visuals: list[Visual] | None = None
    FilterControls: list[FilterControl] | None = None
    ParameterControls: list[ParameterControl] | None = None
    Layouts: list[Layout] | None = None
    TextBoxes: list[SheetTextBox] | None = None


# ---------------------------------------------------------------------------
# Analysis models — Top-level
# ---------------------------------------------------------------------------

@dataclass
class DataSetIdentifierDeclaration:
    Identifier: str
    DataSetArn: str


@dataclass
class StringParameterDeclaration:
    ParameterValueType: str  # SINGLE_VALUED|MULTI_VALUED
    Name: str
    DefaultValues: dict[str, Any]


@dataclass
class IntegerParameterDeclaration:
    ParameterValueType: str  # SINGLE_VALUED|MULTI_VALUED
    Name: str
    DefaultValues: dict[str, Any]  # {"StaticValues": [int]}


@dataclass
class DateTimeDefaultValues:
    StaticValues: list[str] | None = None
    DynamicValue: dict[str, Any] | None = None
    RollingDate: dict[str, Any] | None = None


@dataclass
class DateTimeParameterDeclaration:
    Name: str
    TimeGranularity: str | None = None
    DefaultValues: DateTimeDefaultValues | None = None
    ValueWhenUnset: dict[str, Any] | None = None


@dataclass
class ParameterDeclaration:
    """Union type — set exactly one."""
    StringParameterDeclaration: StringParameterDeclaration | None = None
    IntegerParameterDeclaration: IntegerParameterDeclaration | None = None
    DateTimeParameterDeclaration: DateTimeParameterDeclaration | None = None


@dataclass
class AnalysisDefinition:
    DataSetIdentifierDeclarations: list[DataSetIdentifierDeclaration]
    Sheets: list[SheetDefinition] | None = None
    FilterGroups: list[FilterGroup] | None = None
    ParameterDeclarations: list[ParameterDeclaration] | None = None
    CalculatedFields: list[dict[str, Any]] | None = None


@dataclass
class Analysis:
    AwsAccountId: str
    AnalysisId: str
    Name: str
    Definition: AnalysisDefinition
    ThemeArn: str | None = None
    Permissions: list[ResourcePermission] | None = None
    Tags: list[Tag] | None = None

    def to_aws_json(self) -> dict[str, Any]:
        return _strip_nones(asdict(self))

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_aws_json(), indent=indent)


# ---------------------------------------------------------------------------
# Dashboard models
# ---------------------------------------------------------------------------

@dataclass
class DashboardPublishOptions:
    AdHocFilteringOption: dict[str, str] | None = None
    ExportToCSVOption: dict[str, str] | None = None
    SheetControlsOption: dict[str, str] | None = None


@dataclass
class LinkSharingConfiguration:
    Permissions: list[ResourcePermission] | None = None


@dataclass
class Dashboard:
    AwsAccountId: str
    DashboardId: str
    Name: str
    Definition: AnalysisDefinition
    ThemeArn: str | None = None
    Permissions: list[ResourcePermission] | None = None
    Tags: list[Tag] | None = None
    VersionDescription: str | None = None
    DashboardPublishOptions: DashboardPublishOptions | None = None
    LinkSharingConfiguration: LinkSharingConfiguration | None = None

    def to_aws_json(self) -> dict[str, Any]:
        return _strip_nones(asdict(self))

    def to_json_string(self, indent: int = 2) -> str:
        return json.dumps(self.to_aws_json(), indent=indent)
