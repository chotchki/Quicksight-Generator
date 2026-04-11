"""Dataclass models mapping to AWS QuickSight API JSON structures.

Each top-level model (Theme, DataSet, Analysis) has a `to_aws_json()` method
that returns the exact dict shape expected by the corresponding AWS CLI command
(create-theme, create-data-set, create-analysis).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


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


@dataclass
class BarChartVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: BarChartConfiguration | None = None


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


@dataclass
class PieChartVisual:
    VisualId: str
    Title: VisualTitleLabelOptions | None = None
    Subtitle: VisualSubtitleLabelOptions | None = None
    ChartConfiguration: PieChartConfiguration | None = None


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


# -- Visual union --

@dataclass
class Visual:
    """Union type — set exactly one."""
    BarChartVisual: BarChartVisual | None = None
    PieChartVisual: PieChartVisual | None = None
    KPIVisual: KPIVisual | None = None
    TableVisual: TableVisual | None = None


# ---------------------------------------------------------------------------
# Analysis models — Filters
# ---------------------------------------------------------------------------

@dataclass
class CategoryFilterConfiguration:
    FilterListConfiguration: dict[str, Any] | None = None
    # FilterListConfiguration: {MatchOperator, CategoryValues, SelectAllOptions}


@dataclass
class CategoryFilter:
    FilterId: str
    Column: ColumnIdentifier
    Configuration: CategoryFilterConfiguration


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


@dataclass
class Filter:
    """Union type — set exactly one."""
    CategoryFilter: CategoryFilter | None = None
    TimeRangeFilter: TimeRangeFilter | None = None


@dataclass
class SheetVisualScopingConfiguration:
    SheetId: str
    Scope: str  # ALL_VISUALS|SELECTED_VISUALS
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
    FilterGroupId: str
    Filters: list[Filter]
    ScopeConfiguration: FilterScopeConfiguration
    CrossDataset: str = "SINGLE_DATASET"  # ALL_DATASETS|SINGLE_DATASET
    Status: str | None = None  # ENABLED|DISABLED


# ---------------------------------------------------------------------------
# Analysis models — Filter controls
# ---------------------------------------------------------------------------

@dataclass
class FilterDropDownControl:
    FilterControlId: str
    Title: str
    SourceFilterId: str
    Type: str | None = None  # MULTI_SELECT|SINGLE_SELECT


@dataclass
class FilterDateTimePickerControl:
    FilterControlId: str
    Title: str
    SourceFilterId: str
    Type: str | None = None  # SINGLE_VALUED|DATE_RANGE


@dataclass
class FilterControl:
    """Union type — set exactly one."""
    Dropdown: FilterDropDownControl | None = None
    DateTimePicker: FilterDateTimePickerControl | None = None


# ---------------------------------------------------------------------------
# Analysis models — Sheet & Layout
# ---------------------------------------------------------------------------

@dataclass
class FreeFormLayoutElement:
    ElementId: str
    ElementType: str  # VISUAL|FILTER_CONTROL|PARAMETER_CONTROL|TEXT_BOX|IMAGE
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
    ElementId: str
    ElementType: str  # VISUAL|FILTER_CONTROL|PARAMETER_CONTROL
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
class SheetDefinition:
    SheetId: str
    Name: str | None = None
    Title: str | None = None
    Description: str | None = None
    ContentType: str = "INTERACTIVE"  # INTERACTIVE|PAGINATED
    Visuals: list[Visual] | None = None
    FilterControls: list[FilterControl] | None = None
    Layouts: list[Layout] | None = None


# ---------------------------------------------------------------------------
# Analysis models — Top-level
# ---------------------------------------------------------------------------

@dataclass
class DataSetIdentifierDeclaration:
    Identifier: str
    DataSetArn: str


@dataclass
class AnalysisDefinition:
    DataSetIdentifierDeclarations: list[DataSetIdentifierDeclaration]
    Sheets: list[SheetDefinition] | None = None
    FilterGroups: list[FilterGroup] | None = None
    ParameterDeclarations: list[dict[str, Any]] | None = None
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
