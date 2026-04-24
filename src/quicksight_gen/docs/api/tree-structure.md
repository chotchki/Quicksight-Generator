# Tree — App / Analysis / Dashboard / Sheet

Top-level tree nodes. `App` is the construction root; an app emits an
`Analysis` and (optionally) a `Dashboard` mirroring it. Each carries
a list of `Sheet` nodes; sheets carry visuals, filter groups, filter
controls, and parameter controls.

::: quicksight_gen.common.tree.structure
