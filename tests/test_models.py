"""Unit tests for model serialization."""

import json

from quicksight_gen.models import (
    Analysis,
    AnalysisDefinition,
    BarChartAggregatedFieldWells,
    BarChartConfiguration,
    BarChartFieldWells,
    BarChartVisual,
    CategoryFilter,
    CategoryFilterConfiguration,
    CategoricalDimensionField,
    ColumnIdentifier,
    CustomSql,
    DataSet,
    DataSetIdentifierDeclaration,
    DimensionField,
    Filter,
    FilterGroup,
    FilterScopeConfiguration,
    InputColumn,
    KPIConfiguration,
    KPIFieldWells,
    KPIVisual,
    MeasureField,
    NumericalAggregationFunction,
    NumericalMeasureField,
    PhysicalTable,
    PieChartAggregatedFieldWells,
    PieChartConfiguration,
    PieChartFieldWells,
    PieChartVisual,
    SelectedSheetsFilterScopeConfiguration,
    SheetDefinition,
    SheetVisualScopingConfiguration,
    TableConfiguration,
    TableFieldWells,
    TableUnaggregatedFieldWells,
    TableVisual,
    Tag,
    Theme,
    ThemeConfiguration,
    DataColorPalette,
    UIColorPalette,
    Visual,
    VisualTitleLabelOptions,
)
from quicksight_gen.config import Config


class TestStripNones:
    def test_none_keys_removed(self):
        ds = DataSet(
            AwsAccountId="123",
            DataSetId="ds-1",
            Name="Test",
            PhysicalTableMap={},
            LogicalTableMap=None,
        )
        out = ds.to_aws_json()
        assert "LogicalTableMap" not in out

    def test_nested_none_keys_removed(self):
        kpi = KPIVisual(
            VisualId="kpi-1",
            Title=VisualTitleLabelOptions(FormatText={"PlainText": "X"}),
            Subtitle=None,
        )
        visual = Visual(KPIVisual=kpi)
        out = visual.to_aws_json() if hasattr(visual, "to_aws_json") else {}
        # Use the internal helper directly
        from quicksight_gen.models import _strip_nones, asdict
        out = _strip_nones(asdict(visual))
        assert "Subtitle" not in out["KPIVisual"]
        assert "BarChartVisual" not in out


class TestThemeSerialization:
    def test_roundtrip_json(self):
        theme = Theme(
            AwsAccountId="123456789012",
            ThemeId="test-theme",
            Name="Test",
            BaseThemeId="CLASSIC",
            Configuration=ThemeConfiguration(
                DataColorPalette=DataColorPalette(Colors=["#000", "#FFF"]),
                UIColorPalette=UIColorPalette(PrimaryBackground="#FFFFFF"),
            ),
        )
        raw = theme.to_json_string()
        parsed = json.loads(raw)
        assert parsed["ThemeId"] == "test-theme"
        assert parsed["Configuration"]["DataColorPalette"]["Colors"] == ["#000", "#FFF"]

    def test_required_fields_present(self):
        theme = Theme(
            AwsAccountId="123",
            ThemeId="t",
            Name="T",
            BaseThemeId="CLASSIC",
            Configuration=ThemeConfiguration(),
        )
        out = theme.to_aws_json()
        for key in ("AwsAccountId", "ThemeId", "Name", "BaseThemeId", "Configuration"):
            assert key in out


class TestDataSetSerialization:
    def test_custom_sql_structure(self):
        ds = DataSet(
            AwsAccountId="123",
            DataSetId="ds-1",
            Name="Test DS",
            PhysicalTableMap={
                "table1": PhysicalTable(
                    CustomSql=CustomSql(
                        Name="SQL",
                        DataSourceArn="arn:aws:quicksight:us-east-1:123:datasource/x",
                        SqlQuery="SELECT 1",
                        Columns=[InputColumn(Name="id", Type="INTEGER")],
                    )
                )
            },
        )
        out = ds.to_aws_json()
        sql = out["PhysicalTableMap"]["table1"]["CustomSql"]
        assert sql["SqlQuery"] == "SELECT 1"
        assert sql["Columns"][0]["Name"] == "id"
        assert sql["Columns"][0]["Type"] == "INTEGER"

    def test_import_mode_default(self):
        ds = DataSet(
            AwsAccountId="123",
            DataSetId="ds-1",
            Name="Test",
            PhysicalTableMap={},
        )
        assert ds.to_aws_json()["ImportMode"] == "DIRECT_QUERY"


class TestAnalysisSerialization:
    def test_minimal_analysis(self):
        analysis = Analysis(
            AwsAccountId="123",
            AnalysisId="a-1",
            Name="Test",
            Definition=AnalysisDefinition(
                DataSetIdentifierDeclarations=[
                    DataSetIdentifierDeclaration(Identifier="ds", DataSetArn="arn:x")
                ],
                Sheets=[SheetDefinition(SheetId="s1", Name="Sheet 1")],
            ),
        )
        out = analysis.to_aws_json()
        assert out["AnalysisId"] == "a-1"
        assert len(out["Definition"]["Sheets"]) == 1
        assert "ThemeArn" not in out  # None should be stripped


class TestVisualSerialization:
    def test_kpi_visual(self):
        from quicksight_gen.models import _strip_nones, asdict
        kpi = Visual(
            KPIVisual=KPIVisual(
                VisualId="kpi-1",
                Title=VisualTitleLabelOptions(FormatText={"PlainText": "Test KPI"}),
                ChartConfiguration=KPIConfiguration(
                    FieldWells=KPIFieldWells(
                        Values=[
                            MeasureField(
                                NumericalMeasureField=NumericalMeasureField(
                                    FieldId="f1",
                                    Column=ColumnIdentifier(
                                        DataSetIdentifier="ds",
                                        ColumnName="amount",
                                    ),
                                    AggregationFunction=NumericalAggregationFunction(
                                        SimpleNumericalAggregation="SUM"
                                    ),
                                )
                            )
                        ],
                    ),
                ),
            )
        )
        out = _strip_nones(asdict(kpi))
        assert "KPIVisual" in out
        vals = out["KPIVisual"]["ChartConfiguration"]["FieldWells"]["Values"]
        assert vals[0]["NumericalMeasureField"]["AggregationFunction"]["SimpleNumericalAggregation"] == "SUM"

    def test_bar_chart_visual(self):
        from quicksight_gen.models import _strip_nones, asdict
        bar = Visual(
            BarChartVisual=BarChartVisual(
                VisualId="bar-1",
                ChartConfiguration=BarChartConfiguration(
                    FieldWells=BarChartFieldWells(
                        BarChartAggregatedFieldWells=BarChartAggregatedFieldWells(
                            Category=[
                                DimensionField(
                                    CategoricalDimensionField=CategoricalDimensionField(
                                        FieldId="d1",
                                        Column=ColumnIdentifier(
                                            DataSetIdentifier="ds",
                                            ColumnName="merchant",
                                        ),
                                    )
                                )
                            ],
                        )
                    ),
                    Orientation="VERTICAL",
                ),
            )
        )
        out = _strip_nones(asdict(bar))
        cfg = out["BarChartVisual"]["ChartConfiguration"]
        assert cfg["Orientation"] == "VERTICAL"
        cat = cfg["FieldWells"]["BarChartAggregatedFieldWells"]["Category"][0]
        assert cat["CategoricalDimensionField"]["Column"]["ColumnName"] == "merchant"

    def test_pie_chart_visual(self):
        from quicksight_gen.models import _strip_nones, asdict
        pie = Visual(
            PieChartVisual=PieChartVisual(
                VisualId="pie-1",
                ChartConfiguration=PieChartConfiguration(
                    FieldWells=PieChartFieldWells(
                        PieChartAggregatedFieldWells=PieChartAggregatedFieldWells(
                            Category=[
                                DimensionField(
                                    CategoricalDimensionField=CategoricalDimensionField(
                                        FieldId="d1",
                                        Column=ColumnIdentifier(
                                            DataSetIdentifier="ds",
                                            ColumnName="status",
                                        ),
                                    )
                                )
                            ],
                        )
                    ),
                ),
            )
        )
        out = _strip_nones(asdict(pie))
        assert "PieChartVisual" in out

    def test_table_visual(self):
        from quicksight_gen.models import _strip_nones, asdict
        tbl = Visual(
            TableVisual=TableVisual(
                VisualId="tbl-1",
                ChartConfiguration=TableConfiguration(
                    FieldWells=TableFieldWells(
                        TableUnaggregatedFieldWells=TableUnaggregatedFieldWells(
                            Values=[
                                {
                                    "FieldId": "f1",
                                    "Column": {
                                        "DataSetIdentifier": "ds",
                                        "ColumnName": "id",
                                    },
                                }
                            ]
                        )
                    ),
                ),
            )
        )
        out = _strip_nones(asdict(tbl))
        vals = out["TableVisual"]["ChartConfiguration"]["FieldWells"]["TableUnaggregatedFieldWells"]["Values"]
        assert vals[0]["FieldId"] == "f1"

    def test_visual_union_only_one_set(self):
        from quicksight_gen.models import _strip_nones, asdict
        v = Visual(KPIVisual=KPIVisual(VisualId="kpi-1"))
        out = _strip_nones(asdict(v))
        assert len(out) == 1
        assert "KPIVisual" in out


class TestFilterSerialization:
    def test_category_filter(self):
        from quicksight_gen.models import _strip_nones, asdict
        fg = FilterGroup(
            FilterGroupId="fg-1",
            CrossDataset="SINGLE_DATASET",
            ScopeConfiguration=FilterScopeConfiguration(
                SelectedSheets=SelectedSheetsFilterScopeConfiguration(
                    SheetVisualScopingConfigurations=[
                        SheetVisualScopingConfiguration(
                            SheetId="s1", Scope="ALL_VISUALS"
                        )
                    ]
                )
            ),
            Filters=[
                Filter(
                    CategoryFilter=CategoryFilter(
                        FilterId="f1",
                        Column=ColumnIdentifier(
                            DataSetIdentifier="ds", ColumnName="status"
                        ),
                        Configuration=CategoryFilterConfiguration(
                            FilterListConfiguration={
                                "MatchOperator": "CONTAINS",
                                "SelectAllOptions": "FILTER_ALL_VALUES",
                            }
                        ),
                    )
                )
            ],
        )
        out = _strip_nones(asdict(fg))
        assert out["FilterGroupId"] == "fg-1"
        scope = out["ScopeConfiguration"]["SelectedSheets"]
        assert scope["SheetVisualScopingConfigurations"][0]["SheetId"] == "s1"
        cf = out["Filters"][0]["CategoryFilter"]
        assert cf["FilterId"] == "f1"
        assert cf["Configuration"]["FilterListConfiguration"]["MatchOperator"] == "CONTAINS"


class TestTagSerialization:
    def test_tag_in_theme(self):
        theme = Theme(
            AwsAccountId="123",
            ThemeId="t",
            Name="T",
            BaseThemeId="CLASSIC",
            Configuration=ThemeConfiguration(),
            Tags=[Tag(Key="ManagedBy", Value="quicksight-gen")],
        )
        out = theme.to_aws_json()
        assert out["Tags"] == [{"Key": "ManagedBy", "Value": "quicksight-gen"}]

    def test_tag_in_dataset(self):
        ds = DataSet(
            AwsAccountId="123",
            DataSetId="ds-1",
            Name="Test",
            PhysicalTableMap={},
            Tags=[Tag(Key="ManagedBy", Value="quicksight-gen"), Tag(Key="Env", Value="dev")],
        )
        out = ds.to_aws_json()
        assert len(out["Tags"]) == 2
        assert out["Tags"][0] == {"Key": "ManagedBy", "Value": "quicksight-gen"}
        assert out["Tags"][1] == {"Key": "Env", "Value": "dev"}

    def test_tag_in_analysis(self):
        analysis = Analysis(
            AwsAccountId="123",
            AnalysisId="a-1",
            Name="Test",
            Definition=AnalysisDefinition(
                DataSetIdentifierDeclarations=[
                    DataSetIdentifierDeclaration(Identifier="ds", DataSetArn="arn:x")
                ],
            ),
            Tags=[Tag(Key="ManagedBy", Value="quicksight-gen")],
        )
        out = analysis.to_aws_json()
        assert out["Tags"] == [{"Key": "ManagedBy", "Value": "quicksight-gen"}]

    def test_no_tags_stripped(self):
        ds = DataSet(
            AwsAccountId="123",
            DataSetId="ds-1",
            Name="Test",
            PhysicalTableMap={},
        )
        out = ds.to_aws_json()
        assert "Tags" not in out


class TestConfigTags:
    def test_default_common_tag(self):
        cfg = Config(
            aws_account_id="123",
            aws_region="us-east-1",
            datasource_arn="arn:aws:quicksight:us-east-1:123:datasource/x",
        )
        tags = cfg.tags()
        assert len(tags) == 1
        assert tags[0].Key == "ManagedBy"
        assert tags[0].Value == "quicksight-gen"

    def test_extra_tags_merged(self):
        cfg = Config(
            aws_account_id="123",
            aws_region="us-east-1",
            datasource_arn="arn:aws:quicksight:us-east-1:123:datasource/x",
            extra_tags={"Environment": "prod", "Team": "finance"},
        )
        tags = cfg.tags()
        assert len(tags) == 3
        keys = [t.Key for t in tags]
        assert "ManagedBy" in keys
        assert "Environment" in keys
        assert "Team" in keys

    def test_common_tag_always_first(self):
        cfg = Config(
            aws_account_id="123",
            aws_region="us-east-1",
            datasource_arn="arn:aws:quicksight:us-east-1:123:datasource/x",
            extra_tags={"Foo": "bar"},
        )
        tags = cfg.tags()
        assert tags[0].Key == "ManagedBy"
