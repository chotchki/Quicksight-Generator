# Tree — Filters, Controls, Parameters

`FilterGroup` wraps one filter (typed `CategoryFilter` /
`NumericRangeFilter` / `TimeRangeFilter`) and its scope (sheet-wide,
visual-pinned, or all-sheets). `FilterControl` and `ParameterControl`
variants surface the filter / parameter to the analyst as a UI widget
on a sheet.

`ParameterDecl` subtypes (`StringParameter` / `IntegerParameter` /
`DecimalParameter` / `DatetimeParameter`) declare an analysis-level
parameter that filters can read from and drills can write to.

::: quicksight_gen.common.tree.filters

::: quicksight_gen.common.tree.controls

::: quicksight_gen.common.tree.parameters
