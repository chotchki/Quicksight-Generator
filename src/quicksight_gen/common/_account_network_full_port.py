"""L.1.15 — Re-port the Account Network sheet via the full L.1 typed
primitives.

This module rebuilds the Investigation Account Network sheet from
scratch using only the typed tree primitives (``KPI`` / ``Table`` /
``Sankey``, ``FilterGroup`` / ``CategoryFilter`` / ``NumericRangeFilter``,
``Drill``, ``Dataset``, ``CalcField``, ``ParameterDropdown`` /
``ParameterSlider``, etc.) — no factory wrappers.

The L.0 spike already proved the tree's composition shape works
end-to-end, but it delegated visual + control construction to the
existing ``apps/investigation`` private builders. L.1.15 is the
load-bearing test that the typed primitives THEMSELVES can express
the sheet — every cross-reference goes through the typed object-ref
APIs, not through factory callables.

**Contract:** byte-identical SheetDefinition output compared to
``apps.investigation.analysis._build_account_network_sheet(cfg)``.
The byte-identity check lives in ``tests/test_l1_15_port.py``.

If this passes, the L.1 typed primitives are unblocked for L.2 / L.3
/ L.4 (per-app ports). If it doesn't, the diff points at whatever the
typed primitives can't yet express and we iterate before any per-app
port starts.
"""

from __future__ import annotations

from quicksight_gen.common.config import Config
from quicksight_gen.common.dataset_contract import ColumnShape
from quicksight_gen.common.ids import (
    FilterGroupId,
    ParameterName,
    SheetId,
    VisualId,
)
from quicksight_gen.common.tree import (
    Analysis,
    App,
    CalcField,
    CategoryFilter,
    Dataset,
    Dim,
    Drill,
    DrillParam,
    DrillSourceField,
    FilterGroup,
    IntegerParam,
    LinkedValues,
    Measure,
    NumericRangeFilter,
    ParameterDropdown,
    ParameterSlider,
    Sankey,
    Sheet,
    StringParam,
    Table,
)


# Layout constants mirror apps/investigation/analysis.py.
_FULL = 36
_TABLE_ROW_SPAN = 18


def build_account_network_app_via_full_primitives(cfg: Config) -> App:
    """Build an investigation-shaped App whose Account Network sheet
    uses every L.1 typed primitive.

    Returns the App ready for ``app.emit_analysis()``. The
    byte-identity test extracts the Account Network SheetDefinition
    from the emitted Analysis and compares to the imperative builder's
    output.
    """
    # Imports inside the function to avoid load-time coupling between
    # common/ and apps/.
    from quicksight_gen.apps.investigation.analysis import (
        _ACCOUNT_NETWORK_DESCRIPTION,
    )

    app = App(name="investigation", cfg=cfg)

    # ----- Datasets -----------------------------------------------------
    # Two datasets back the Account Network sheet:
    #   - inv-account-network-ds: the matview wrapper (visuals + filters)
    #   - inv-anetwork-accounts-ds: the narrow accounts dataset for the
    #     anchor dropdown (K.4.8k optimization)
    ds_anet = app.add_dataset(Dataset(
        identifier="inv-account-network-ds",
        arn=cfg.dataset_arn(cfg.prefixed("inv-account-network-dataset")),
    ))
    ds_accounts = app.add_dataset(Dataset(
        identifier="inv-anetwork-accounts-ds",
        arn=cfg.dataset_arn(cfg.prefixed("inv-anetwork-accounts-dataset")),
    ))

    # ----- Analysis -----------------------------------------------------
    analysis = app.set_analysis(Analysis(
        analysis_id_suffix="investigation-analysis",
        name="Investigation",
    ))

    # ----- Parameters ---------------------------------------------------
    anchor_param = analysis.add_parameter(StringParam(
        name=ParameterName("pInvANetworkAnchor"),
        default=[],  # No default — SelectAll=HIDDEN forces dropdown to land
                     # on first available anchor on first paint.
    ))
    min_amount_param = analysis.add_parameter(IntegerParam(
        name=ParameterName("pInvANetworkMinAmount"),
        default=[0],  # DEFAULT_MONEY_TRAIL_MIN_AMOUNT
    ))

    # ----- Calc fields --------------------------------------------------
    # The four analysis-level calc fields the Account Network sheet uses.
    is_anchor_edge = analysis.add_calc_field(CalcField(
        name="is_anchor_edge",
        dataset=ds_anet,
        expression=(
            "ifelse({source_display} = ${pInvANetworkAnchor} "
            "OR {target_display} = ${pInvANetworkAnchor}, "
            "'yes', 'no')"
        ),
    ))
    is_inbound_edge = analysis.add_calc_field(CalcField(
        name="is_inbound_edge",
        dataset=ds_anet,
        expression=(
            "ifelse({target_display} = ${pInvANetworkAnchor}, "
            "'yes', 'no')"
        ),
    ))
    is_outbound_edge = analysis.add_calc_field(CalcField(
        name="is_outbound_edge",
        dataset=ds_anet,
        expression=(
            "ifelse({source_display} = ${pInvANetworkAnchor}, "
            "'yes', 'no')"
        ),
    ))
    counterparty_display = analysis.add_calc_field(CalcField(
        name="counterparty_display",
        dataset=ds_anet,
        expression=(
            "ifelse({source_display} = ${pInvANetworkAnchor}, "
            "{target_display}, {source_display})"
        ),
    ))

    # ----- Sheet --------------------------------------------------------
    sheet = analysis.add_sheet(Sheet(
        sheet_id=SheetId("inv-sheet-account-network"),
        name="Account Network",
        title="Account Network",
        description=_ACCOUNT_NETWORK_DESCRIPTION,
    ))

    # ----- Visuals ------------------------------------------------------
    # Inbound Sankey — counterparties → anchor (target=anchor side)
    inbound_sankey = sheet.add_visual(Sankey(
        visual_id=VisualId("inv-anetwork-sankey-inbound"),
        title="Inbound — counterparties → anchor",
        subtitle=(
            "Counterparties sending money INTO the anchor account. "
            "Ribbon thickness = SUM(hop_amount). Left-click any source "
            "node (or its ribbon) to walk the anchor over to that "
            "counterparty."
        ),
        source=Dim(
            dataset=ds_anet,
            field_id="inv-anetwork-sankey-in-source",
            column="source_display",
        ),
        target=Dim(
            dataset=ds_anet,
            field_id="inv-anetwork-sankey-in-target",
            column="target_display",
        ),
        weight=Measure.sum(
            ds_anet, "inv-anetwork-sankey-in-weight", "hop_amount",
        ),
        items_limit=50,  # _ANETWORK_NODE_CAP
        actions=[Drill(
            target_sheet=sheet,
            writes=[(
                DrillParam(
                    ParameterName("pInvANetworkAnchor"),
                    ColumnShape.ACCOUNT_DISPLAY,
                ),
                DrillSourceField(
                    field_id="inv-anetwork-sankey-in-source",
                    shape=ColumnShape.ACCOUNT_DISPLAY,
                ),
            )],
            name="Walk to this counterparty",
            trigger="DATA_POINT_CLICK",
            action_id="action-anetwork-sankey-inbound-walk",
        )],
    ))

    # Outbound Sankey — anchor → counterparties (source=anchor side)
    outbound_sankey = sheet.add_visual(Sankey(
        visual_id=VisualId("inv-anetwork-sankey-outbound"),
        title="Outbound — anchor → counterparties",
        subtitle=(
            "Counterparties receiving money FROM the anchor account. "
            "Ribbon thickness = SUM(hop_amount). Left-click any target "
            "node (or its ribbon) to walk the anchor over to that "
            "counterparty."
        ),
        source=Dim(
            dataset=ds_anet,
            field_id="inv-anetwork-sankey-out-source",
            column="source_display",
        ),
        target=Dim(
            dataset=ds_anet,
            field_id="inv-anetwork-sankey-out-target",
            column="target_display",
        ),
        weight=Measure.sum(
            ds_anet, "inv-anetwork-sankey-out-weight", "hop_amount",
        ),
        items_limit=50,
        actions=[Drill(
            target_sheet=sheet,
            writes=[(
                DrillParam(
                    ParameterName("pInvANetworkAnchor"),
                    ColumnShape.ACCOUNT_DISPLAY,
                ),
                DrillSourceField(
                    field_id="inv-anetwork-sankey-out-target",
                    shape=ColumnShape.ACCOUNT_DISPLAY,
                ),
            )],
            name="Walk to this counterparty",
            trigger="DATA_POINT_CLICK",
            action_id="action-anetwork-sankey-outbound-walk",
        )],
    ))

    # Touching-edges Table
    table = sheet.add_visual(Table(
        visual_id=VisualId("inv-anetwork-table"),
        title="Account Network — Touching Edges",
        subtitle=(
            "Every edge involving the anchor account in either "
            "direction, ordered by amount descending. The "
            "Counterparty column shows the side that isn't the "
            "current anchor — right-click any row and pick \"Walk "
            "to other account on this edge\" to make that "
            "counterparty the new anchor. The dropdown above may "
            "take a moment to catch up; trust the data, not the "
            "control text."
        ),
        group_by=[
            Dim(dataset=ds_anet, field_id="inv-anetwork-tbl-transfer-id",
                column="transfer_id"),
            Dim(dataset=ds_anet, field_id="inv-anetwork-tbl-transfer-type",
                column="transfer_type"),
            Dim(dataset=ds_anet, field_id="inv-anetwork-tbl-source-display",
                column="source_display"),
            Dim(dataset=ds_anet, field_id="inv-anetwork-tbl-target-display",
                column="target_display"),
            # Calc-field reference — the L.1.8 ColumnRef union accepts
            # the CalcField object ref directly; emit reads .name.
            Dim(dataset=ds_anet, field_id="inv-anetwork-tbl-counterparty",
                column=counterparty_display),
            Dim.numerical(dataset=ds_anet, field_id="inv-anetwork-tbl-depth",
                          column="depth"),
            Dim.date(dataset=ds_anet, field_id="inv-anetwork-tbl-posted-at",
                     column="posted_at"),
        ],
        values=[Measure.sum(
            ds_anet, "inv-anetwork-tbl-amount", "hop_amount",
        )],
        sort_by=("inv-anetwork-tbl-amount", "DESC"),
        actions=[Drill(
            target_sheet=sheet,
            writes=[(
                DrillParam(
                    ParameterName("pInvANetworkAnchor"),
                    ColumnShape.ACCOUNT_DISPLAY,
                ),
                DrillSourceField(
                    field_id="inv-anetwork-tbl-counterparty",
                    shape=ColumnShape.ACCOUNT_DISPLAY,
                ),
            )],
            name="Walk to other account on this edge",
            trigger="DATA_POINT_MENU",
            action_id="action-anetwork-table-walk-counterparty",
        )],
    ))

    # ----- Layout -------------------------------------------------------
    # Two Sankeys side-by-side on top, full-width table below.
    half_width = _FULL // 2
    sankey_height = _TABLE_ROW_SPAN
    sheet.place(
        inbound_sankey,
        col_span=half_width, row_span=sankey_height, col_index=0,
    )
    sheet.place(
        outbound_sankey,
        col_span=half_width, row_span=sankey_height, col_index=half_width,
    )
    sheet.place(
        table,
        col_span=_FULL, row_span=_TABLE_ROW_SPAN, col_index=0,
    )

    # ----- Filter groups ------------------------------------------------
    # Anchor filter — table only (broader scope).
    analysis.add_filter_group(FilterGroup(
        filter_group_id=FilterGroupId("fg-inv-anetwork-anchor"),
        filters=[CategoryFilter(
            filter_id="filter-inv-anetwork-anchor",
            dataset=ds_anet,
            column=is_anchor_edge,  # CalcField object ref
            values=["yes"],
            match_operator="CONTAINS",
        )],
    )).scope_visuals(sheet, [table])

    # Inbound direction filter — inbound sankey only.
    analysis.add_filter_group(FilterGroup(
        filter_group_id=FilterGroupId("fg-inv-anetwork-inbound"),
        filters=[CategoryFilter(
            filter_id="filter-inv-anetwork-inbound",
            dataset=ds_anet,
            column=is_inbound_edge,
            values=["yes"],
            match_operator="CONTAINS",
        )],
    )).scope_visuals(sheet, [inbound_sankey])

    # Outbound direction filter — outbound sankey only.
    analysis.add_filter_group(FilterGroup(
        filter_group_id=FilterGroupId("fg-inv-anetwork-outbound"),
        filters=[CategoryFilter(
            filter_id="filter-inv-anetwork-outbound",
            dataset=ds_anet,
            column=is_outbound_edge,
            values=["yes"],
            match_operator="CONTAINS",
        )],
    )).scope_visuals(sheet, [outbound_sankey])

    # Min-amount filter — all visuals on the sheet.
    analysis.add_filter_group(FilterGroup(
        filter_group_id=FilterGroupId("fg-inv-anetwork-amount"),
        filters=[NumericRangeFilter(
            filter_id="filter-inv-anetwork-amount",
            dataset=ds_anet,
            column="hop_amount",
            minimum_parameter=min_amount_param,
            null_option="NON_NULLS_ONLY",
            include_minimum=True,
        )],
    )).scope_sheet(sheet)

    # ----- Parameter controls ------------------------------------------
    sheet.add_parameter_control(ParameterDropdown(
        parameter=anchor_param,
        title="Anchor account",
        type="SINGLE_SELECT",
        selectable_values=LinkedValues(
            dataset=ds_accounts,
            column="source_display",
        ),
        hidden_select_all=True,
        control_id="ctrl-inv-anetwork-anchor",
    ))
    sheet.add_parameter_control(ParameterSlider(
        parameter=min_amount_param,
        title="Min hop amount ($)",
        minimum_value=0,    # AMOUNT_SLIDER_MIN
        maximum_value=1000, # AMOUNT_SLIDER_MAX
        step_size=10,
        control_id="ctrl-inv-anetwork-amount",
    ))

    return app
