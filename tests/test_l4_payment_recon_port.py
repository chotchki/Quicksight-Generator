"""L.4 byte-identity gate — tree-built PR sheets must emit JSON
identical to the imperative ``apps/payment_recon/analysis.py`` builders.

Each L.4.N sub-step adds a sheet to ``apps/payment_recon/app.py``;
the corresponding test here pins down that the new tree wiring emits
the same ``SheetDefinition`` shape (modulo intentional layout-DSL
diffs the test allows for).
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from quicksight_gen.apps.payment_recon.analysis import (
    _build_getting_started_sheet as _imperative_getting_started_sheet,
    _build_payments_sheet as _imperative_payments_sheet,
    _build_sales_sheet as _imperative_sales_sheet,
    _build_settlements_sheet as _imperative_settlements_sheet,
    build_analysis as _imperative_build_analysis,
)
from quicksight_gen.apps.payment_recon.app import build_payment_recon_app
from quicksight_gen.apps.payment_recon.constants import (
    PR_DRILL_BINDINGS,
    SHEET_EXCEPTIONS,
    SHEET_PAYMENT_RECON,
    SHEET_PAYMENTS,
    SHEET_SALES,
    SHEET_SETTLEMENTS,
)


from quicksight_gen.common.config import Config
from quicksight_gen.common.models import _strip_nones


_BASE_CFG_KWARGS = dict(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="default",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


def _normalize_sheet(sheet_json: dict) -> dict:
    """Strip layout-DSL-specific differences that don't change deploy
    behavior:

    - ``RowIndex`` on grid elements (the layout DSL emits the explicit
      row cursor; the imperative builder omits it).
    - Drop sheet-level fields the L.1 builder always emits but the
      Getting Started imperative path doesn't bother with (e.g. empty
      ``FilterControls`` lists). Both are accepted by QuickSight.
    """
    normalized = json.loads(json.dumps(sheet_json))
    layouts = normalized.get("Layouts") or []
    for layout in layouts:
        elements = (
            layout.get("Configuration", {})
            .get("GridLayout", {})
            .get("Elements", [])
        )
        for element in elements:
            element.pop("RowIndex", None)
    if normalized.get("Visuals") is None:
        normalized.pop("Visuals", None)
    if normalized.get("FilterControls") in (None, []):
        normalized.pop("FilterControls", None)
    if normalized.get("ParameterControls") in (None, []):
        normalized.pop("ParameterControls", None)
    return normalized


@pytest.mark.parametrize("preset, demo_url", [
    ("default", None),
    ("sasquatch-bank", "postgres://demo:demo@localhost/demo"),
])
def test_l4_1_getting_started_sheet_byte_identical(
    preset: str, demo_url: str | None,
) -> None:
    """The tree-built Getting Started sheet emits the same SheetDefinition
    JSON as the imperative builder, modulo layout-DSL RowIndex.

    Two parametrized cases cover both branches of the demo-flavor block:
    default (no demo URL → omits gs-demo-flavor) and demo-config (URL
    set → includes the flavor block)."""
    cfg_kwargs = dict(_BASE_CFG_KWARGS)
    cfg_kwargs["theme_preset"] = preset
    cfg_kwargs["demo_database_url"] = demo_url
    cfg = Config(**cfg_kwargs)

    imperative_sheet = _strip_nones(asdict(_imperative_getting_started_sheet(cfg)))

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    gs_sheet = next(
        s for s in analysis.Definition.Sheets if s.SheetId == "sheet-getting-started"
    )
    tree_sheet = _strip_nones(asdict(gs_sheet))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)


def test_l4_2_sales_overview_sheet_byte_identical() -> None:
    """Sales Overview: 2 KPIs + 2 horizontal bar charts (with same-sheet
    click filters narrowing the detail table) + unaggregated detail
    table with right-click drill into Settlements (writes pSettlementId,
    settlement_id cell carries the menu_link CF — accent text + tint
    background).

    FilterControls are deferred to L.4.7; comparing the rest of the
    sheet is the right granularity until that wiring lands."""
    cfg = Config(**_BASE_CFG_KWARGS)

    imperative_sheet = _strip_nones(asdict(_imperative_sales_sheet(cfg)))

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    sales_sheet = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_SALES
    )
    tree_sheet = _strip_nones(asdict(sales_sheet))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)


def test_l4_3_settlements_sheet_byte_identical() -> None:
    """Settlements: 2 KPIs (settled amount + pending count) + full-width
    vertical bar by settlement_type (with same-sheet click filter to
    detail table) + 8-column unaggregated detail table with two drills:
    left-click → Sales (writes pSettlementId), right-click → Payments
    (writes pPaymentId). Two CF entries — settlement_id link
    (accent text only), payment_id menu_link (accent text + tint)."""
    cfg = Config(**_BASE_CFG_KWARGS)

    imperative_sheet = _strip_nones(asdict(_imperative_settlements_sheet(cfg)))

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    stl_sheet = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_SETTLEMENTS
    )
    tree_sheet = _strip_nones(asdict(stl_sheet))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)


def _visual_ids(sheet: dict) -> list[str]:
    out: list[str] = []
    for v in sheet.get("Visuals") or []:
        for body in v.values():
            if isinstance(body, dict) and "VisualId" in body:
                out.append(body["VisualId"])
    return out


def _layout_visual_ids(sheet: dict) -> list[str]:
    layouts = sheet.get("Layouts") or []
    if not layouts:
        return []
    return [
        e["ElementId"]
        for e in layouts[0]["Configuration"]["GridLayout"]["Elements"]
    ]


def test_l4_5_exceptions_sheet_has_kpis_tables_and_aging_bars() -> None:
    """Exceptions & Alerts (post L.4.12a): 2 KPIs + 5 detail tables +
    5 aging bars (one per table) = 12 visuals, all placed in layout.

    L.4.12a wired the 5 aging bars the imperative
    `build_exceptions_visuals()` constructed but never placed (orphan
    UX intention surfaced during the L.4.5 port). Assertions are now
    positive structural ones — there's no imperative comparator to
    diff against once L.4.13 deletes the imperative builders."""
    cfg = Config(**_BASE_CFG_KWARGS)

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    exc_sheet = _strip_nones(asdict(next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_EXCEPTIONS
    )))

    visual_ids = set(_visual_ids(exc_sheet))
    expected = {
        "exceptions-kpi-unsettled",
        "exceptions-kpi-returns",
        "exceptions-unsettled-table",
        "exceptions-returns-table",
        "exceptions-sale-settlement-mismatch-table",
        "exceptions-settlement-payment-mismatch-table",
        "exceptions-unmatched-ext-txn-table",
        "exceptions-aging-unsettled",
        "exceptions-aging-returns",
        "exceptions-aging-sale-stl-mismatch",
        "exceptions-aging-stl-pay-mismatch",
        "exceptions-aging-unmatched-ext",
    }
    assert visual_ids == expected
    # Every visual is placed in the layout — no orphans remain.
    assert set(_layout_visual_ids(exc_sheet)) == expected


def test_l4_6_payment_recon_sheet_has_kpis_bar_tables_and_aging() -> None:
    """Payment Reconciliation (post L.4.12a): 3 KPIs + bar by system +
    side-by-side detail tables + 1 aging bar = 7 visuals all placed.

    L.4.12a wired the `recon-aging-bar` the imperative
    `build_payment_recon_visuals()` constructed but never placed."""
    cfg = Config(**_BASE_CFG_KWARGS)

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    recon_sheet = _strip_nones(asdict(next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == SHEET_PAYMENT_RECON
    )))

    visual_ids = set(_visual_ids(recon_sheet))
    expected = {
        "recon-kpi-matched-amount",
        "recon-kpi-unmatched-amount",
        "recon-kpi-late-count",
        "recon-bar-by-system",
        "recon-payments-table",
        "recon-ext-txn-table",
        "recon-aging-bar",
    }
    assert visual_ids == expected
    assert set(_layout_visual_ids(recon_sheet)) == expected


def _filter_group_by_id(definition: dict, fg_id: str) -> dict | None:
    for fg in definition.get("FilterGroups", []):
        if fg.get("FilterGroupId") == fg_id:
            return fg
    return None


def test_l4_7a_parameters_and_drill_filter_groups_byte_identical() -> None:
    """3 string parameters (`pSettlementId`, `pPaymentId`,
    `pExternalTransactionId`) + 5 drill PASS filter groups (one per
    `PR_DRILL_BINDINGS` entry). The filter groups bind each drill
    parameter to the destination sheet's relevant id column via
    `CustomFilterConfiguration` (EQUALS + ParameterName +
    NullOption=ALL_VALUES) — simpler than AR's K.2 calc-field PASS
    pattern because PR drills are always single-parameter writes."""
    cfg = Config(**_BASE_CFG_KWARGS)

    imperative = _imperative_build_analysis(cfg).to_aws_json()["Definition"]
    tree = build_payment_recon_app(cfg).emit_analysis().to_aws_json()["Definition"]

    assert imperative["ParameterDeclarations"] == tree["ParameterDeclarations"]

    for binding in PR_DRILL_BINDINGS:
        imp_fg = _filter_group_by_id(imperative, binding.fg_id)
        tree_fg = _filter_group_by_id(tree, binding.fg_id)
        assert imp_fg is not None, (
            f"imperative missing drill FG {binding.fg_id!r}"
        )
        assert tree_fg is not None, f"tree missing drill FG {binding.fg_id!r}"
        assert imp_fg == tree_fg, (
            f"drill filter group {binding.fg_id!r} diverged"
        )


def test_l4_7b_filter_groups_byte_identical() -> None:
    """All 29 PR FilterGroups (18 pipeline + 3 pipeline drills + 6 recon
    + 2 recon drills) — full FilterGroups list compared in order."""
    cfg = Config(**_BASE_CFG_KWARGS)

    imperative = _imperative_build_analysis(cfg).to_aws_json()["Definition"]
    tree = build_payment_recon_app(cfg).emit_analysis().to_aws_json()["Definition"]

    assert imperative["FilterGroups"] == tree["FilterGroups"]


# L.4.7d full-app byte-identity tests retired in L.4.12a — adding the
# 6 aging bars to the tree's layout makes per-sheet equality with the
# imperative inherently false on the Exceptions + Payment Recon sheets,
# and the byte-identity gates already proved port-correctness up to
# that commit (git history is the receipt). The remaining structural
# coverage:
# - Per-sheet structural assertions on Exceptions / Payment Recon
#   (visual count + visual ids + every visual is placed).
# - Per-sheet byte-identity tests for the unchanged sheets (Getting
#   Started / Sales / Settlements / Payments) until L.4.13.
# - L.4.7a parameter + drill PASS filter group equality.
# - L.4.7b full FilterGroups list equality.


def test_l4_4_payments_sheet_byte_identical() -> None:
    """Payments: 2 KPIs (paid amount + returned count) + full-width
    vertical bar by payment_status (with same-sheet click filter to
    detail table) + 9-column unaggregated detail table with two drills:
    left-click → Settlements (writes pSettlementId), right-click →
    Payment Reconciliation (writes pExternalTransactionId). Two CF
    entries — settlement_id link, external_transaction_id menu_link."""
    cfg = Config(**_BASE_CFG_KWARGS)

    imperative_sheet = _strip_nones(asdict(_imperative_payments_sheet(cfg)))

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    pay_sheet = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_PAYMENTS
    )
    tree_sheet = _strip_nones(asdict(pay_sheet))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)
