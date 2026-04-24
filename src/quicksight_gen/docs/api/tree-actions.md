# Tree — Drill Actions

`Drill` is the typed action wrapper for click-driven navigation. Two
trigger flavors: `DATA_POINT_CLICK` (left-click) and `DATA_POINT_MENU`
(right-click context menu). Cross-sheet drills carry a `Sheet` object
ref as the target — never a string ID — so the tree validates the
destination at emit time.

::: quicksight_gen.common.tree.actions
