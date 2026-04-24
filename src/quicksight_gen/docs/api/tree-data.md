# Tree — Data

`Dataset` is the tree node for one dataset registration on the App;
`Column` is a typed reference to a column on a `Dataset`. The chained
factories (`ds["col"].dim()` / `.sum()` / `.date()`) build typed
`Dim` / `Measure` slots that visuals consume directly.

`CalcField` is an analysis-level calculated field — bound to one
`Dataset`, available across visuals via the same typed-Dim shape.

::: quicksight_gen.common.tree.datasets

::: quicksight_gen.common.tree.fields

::: quicksight_gen.common.tree.calc_fields
