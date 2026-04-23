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
    _build_sales_sheet as _imperative_sales_sheet,
    _build_settlements_sheet as _imperative_settlements_sheet,
)
from quicksight_gen.apps.payment_recon.app import build_payment_recon_app
from quicksight_gen.apps.payment_recon.constants import (
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


def _strip_filter_controls(sheet_json: dict) -> dict:
    """L.4.2-style normalization for sheets whose FilterControls are
    deferred to L.4.7. The imperative builder emits per-sheet controls
    inline; the tree port lands them via app-level wiring later. Until
    then, comparing only Visuals + Layouts + descriptions is the right
    granularity."""
    out = dict(sheet_json)
    out.pop("FilterControls", None)
    return out


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

    imperative_sheet = _strip_filter_controls(
        _strip_nones(asdict(_imperative_sales_sheet(cfg)))
    )

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    sales_sheet = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_SALES
    )
    tree_sheet = _strip_filter_controls(_strip_nones(asdict(sales_sheet)))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)


def test_l4_3_settlements_sheet_byte_identical() -> None:
    """Settlements: 2 KPIs (settled amount + pending count) + full-width
    vertical bar by settlement_type (with same-sheet click filter to
    detail table) + 8-column unaggregated detail table with two drills:
    left-click → Sales (writes pSettlementId), right-click → Payments
    (writes pPaymentId). Two CF entries — settlement_id link
    (accent text only), payment_id menu_link (accent text + tint)."""
    cfg = Config(**_BASE_CFG_KWARGS)

    imperative_sheet = _strip_filter_controls(
        _strip_nones(asdict(_imperative_settlements_sheet(cfg)))
    )

    app = build_payment_recon_app(cfg)
    analysis = app.emit_analysis()
    stl_sheet = next(
        s for s in analysis.Definition.Sheets if s.SheetId == SHEET_SETTLEMENTS
    )
    tree_sheet = _strip_filter_controls(_strip_nones(asdict(stl_sheet)))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)
