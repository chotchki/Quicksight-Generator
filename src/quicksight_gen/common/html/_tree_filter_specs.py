"""Y.2.app2.cde.l2ft-wiring.b — derive App2 filter-form specs from a tree
``Sheet``'s parameter-control nodes.

App2's filter form (``render._render_filter_form``) renders the universal
date pickers plus an explicit ``FilterSpec`` list. Until now every tree app
passed ``filter_specs=()``, so a sheet's QuickSight ``ParameterDropdown``
controls (e.g. L2FT's Rail / Status / Bundle multi-selects) rendered as
nothing in App2 — the dataset SQL still applied the declared-value default
(Y.2.app2.cde.core), so visuals showed every row, but the analyst couldn't
narrow.

This walk closes that gap for the **MULTI_SELECT + StaticValues** case: a
``ParameterDropdown(type="MULTI_SELECT", selectable_values=StaticValues(...))``
node becomes a ``ParameterMultiSelectSpec`` → a ``<select multiple
name="param_<name>">``. The selected options serialise as repeated
``?param_<name>=A&param_<name>=B`` query keys, which is exactly the shape
``_sql_executor.expand_multivalued_dataset_params`` consumes (it reads
``url_params.get(f"param_{name}")`` as a list and expands ``<<$name>>`` to
``:param_name_0, :param_name_1, …``). Nothing selected → no key → the
executor's static-default fallback kicks in (= no narrowing), mirroring
QuickSight's "empty the dropdown reverts to default" behaviour.

Out of scope (for now): SINGLE_SELECT dropdowns (L2FT's metadata-cascade
key dropdowns — App2 can't replicate the QS cascade-refresh-options
behaviour, so a static single-select would be a half-truth); ``LinkedValues``
dropdowns (App2 would have to query the linked dataset to enumerate options
— deferred); sliders / number / text-field parameter controls (a different
shape; investigation's sigma/threshold sliders, if any reach App2, would
want a ``NumericRangeSpec``-ish primitive — not this sub-task). Those
controls are silently skipped — the form just won't carry a widget for them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from quicksight_gen.common.html.render import FilterSpec, ParameterMultiSelectSpec
from quicksight_gen.common.tree import ParameterDropdown, StaticValues

if TYPE_CHECKING:
    from quicksight_gen.common.tree import Sheet


def make_filter_specs_for_sheet(sheet: "Sheet") -> list[FilterSpec]:
    """Return the App2 filter-form specs auto-derived from ``sheet``'s
    parameter-control nodes.

    Today that's one ``ParameterMultiSelectSpec`` per MULTI_SELECT
    ``ParameterDropdown`` whose ``selectable_values`` is a ``StaticValues``
    (the only kind App2 can render without querying). Order follows the
    sheet's ``parameter_controls`` order so the filter bar matches the
    QuickSight control layout. Sheets with no such control return ``[]``
    (the form is then date-pickers-only, and is suppressed entirely for
    text-box-only sheets per ``render``'s existing logic).
    """
    specs: list[FilterSpec] = []
    for ctrl in sheet.parameter_controls:
        if not isinstance(ctrl, ParameterDropdown):
            continue
        if ctrl.type != "MULTI_SELECT":
            continue
        if not isinstance(ctrl.selectable_values, StaticValues):
            continue
        specs.append(ParameterMultiSelectSpec(
            name=str(ctrl.parameter.name),
            label=ctrl.title,
            options=tuple(ctrl.selectable_values.values),
        ))
    return specs
