"""L.3 byte-identity gates — tree-built AR sheets must emit JSON
identical to the imperative ``apps/account_recon/analysis.py`` builders.

Each L.3.N sub-step adds a sheet populator to
``apps/account_recon/app.py``; the corresponding test here pins down
that the new tree wiring emits the same ``SheetDefinition`` shape
(modulo intentional layout-DSL diffs the test allows for).

The full-app byte-identity test lands at end-of-L.3 (after L.3.7);
each per-sheet test isolates its sheet by id so unported shells don't
pollute the comparison.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable

import pytest

from quicksight_gen.apps.account_recon.analysis import (
    _build_balances_sheet as _imperative_balances_sheet,
)
from quicksight_gen.apps.account_recon.analysis import (
    _build_getting_started_sheet as _imperative_getting_started_sheet,
)
from quicksight_gen.apps.account_recon.analysis import (
    _build_transactions_sheet as _imperative_transactions_sheet,
)
from quicksight_gen.apps.account_recon.analysis import (
    _build_transfers_sheet as _imperative_transfers_sheet,
)
from quicksight_gen.apps.account_recon.app import build_account_recon_app
from quicksight_gen.apps.account_recon.constants import (
    SHEET_AR_BALANCES,
    SHEET_AR_GETTING_STARTED,
    SHEET_AR_TRANSACTIONS,
    SHEET_AR_TRANSFERS,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import _strip_nones
from quicksight_gen.common.theme import get_preset


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
    behavior.

    - ``RowIndex`` on grid elements (the layout DSL emits the explicit
      row cursor; the imperative builder omits it).
    - Empty-list / None forms of FilterControls / ParameterControls /
      Visuals fields are normalized to absent.
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


def _strip_filter_controls(sheet: dict) -> dict:
    """For incremental L.3.N tests: drop FilterControls before
    comparison. Tree-side controls land in L.3.8 wiring; until then
    the imperative side has them and the tree side doesn't."""
    sheet = json.loads(json.dumps(sheet))
    sheet.pop("FilterControls", None)
    sheet.pop("ParameterControls", None)
    return sheet


def _tree_sheet_by_id(cfg: Config, sheet_id: str) -> dict:
    app = build_account_recon_app(cfg)
    analysis = app.emit_analysis()
    for s in analysis.Definition.Sheets:
        if s.SheetId == sheet_id:
            return _strip_nones(asdict(s))
    raise AssertionError(f"Sheet {sheet_id!r} not registered on the tree")


@pytest.mark.parametrize("preset, demo_url", [
    ("default", None),
    ("sasquatch-bank-ar", "postgres://demo:demo@localhost/demo"),
])
def test_l3_1_getting_started_sheet_byte_identical(
    preset: str, demo_url: str | None,
) -> None:
    """The tree-built Getting Started sheet emits the same SheetDefinition
    JSON as the imperative builder, modulo layout-DSL RowIndex.

    Two parametrized cases cover both branches of the demo-flavor block:
    default (no demo URL → omits ar-gs-demo-flavor) and demo-config (URL
    set → includes the flavor block)."""
    cfg_kwargs = dict(_BASE_CFG_KWARGS)
    cfg_kwargs["theme_preset"] = preset
    cfg_kwargs["demo_database_url"] = demo_url
    cfg = Config(**cfg_kwargs)

    imperative_sheet = _strip_nones(asdict(_imperative_getting_started_sheet(cfg)))
    tree_sheet = _tree_sheet_by_id(cfg, SHEET_AR_GETTING_STARTED)

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)


def test_l3_2_balances_sheet_byte_identical() -> None:
    """Balances sheet: 2 KPIs + 2 unaggregated drift tables with drill
    actions + conditional formatting.

    FilterControls are stripped for now — they land in L.3.8 once the
    AR filter groups are declared on the tree's analysis. The visual
    bodies + drill actions + conditional formatting are the load-bearing
    surface of L.3.2 and the test pins those down byte-for-byte against
    the imperative output.
    """
    cfg_kwargs = dict(_BASE_CFG_KWARGS)
    cfg_kwargs["theme_preset"] = "sasquatch-bank-ar"
    cfg = Config(**cfg_kwargs)
    preset = get_preset("sasquatch-bank-ar")

    imperative_sheet = _strip_nones(asdict(
        _imperative_balances_sheet(cfg, preset.accent, preset.link_tint),
    ))
    tree_sheet = _tree_sheet_by_id(cfg, SHEET_AR_BALANCES)

    imperative_norm = _strip_filter_controls(_normalize_sheet(imperative_sheet))
    tree_norm = _strip_filter_controls(_normalize_sheet(tree_sheet))

    assert tree_norm == imperative_norm


def test_l3_3_transfers_sheet_byte_identical() -> None:
    """Transfers sheet: 2 KPIs + status bar (with same-sheet click-to-
    filter on the summary table) + transfer summary unaggregated table
    (with cross-sheet drill into Transactions + left-click conditional
    formatting)."""
    cfg_kwargs = dict(_BASE_CFG_KWARGS)
    cfg_kwargs["theme_preset"] = "sasquatch-bank-ar"
    cfg = Config(**cfg_kwargs)
    preset = get_preset("sasquatch-bank-ar")

    imperative_sheet = _strip_nones(asdict(
        _imperative_transfers_sheet(cfg, preset.accent),
    ))
    tree_sheet = _tree_sheet_by_id(cfg, SHEET_AR_TRANSFERS)

    imperative_norm = _strip_filter_controls(_normalize_sheet(imperative_sheet))
    tree_norm = _strip_filter_controls(_normalize_sheet(tree_sheet))

    assert tree_norm == imperative_norm


def test_l3_4_transactions_sheet_byte_identical() -> None:
    """Transactions sheet: 2 KPIs + 2 bar charts (status horizontal
    cluster + day vertical stacked-by-status) each with same-sheet
    click filter targeting the detail table + 11-column unaggregated
    detail table (no actions — Transactions is the destination of every
    other sheet's drill)."""
    cfg_kwargs = dict(_BASE_CFG_KWARGS)
    cfg_kwargs["theme_preset"] = "sasquatch-bank-ar"
    cfg = Config(**cfg_kwargs)

    imperative_sheet = _strip_nones(asdict(
        _imperative_transactions_sheet(cfg),
    ))
    tree_sheet = _tree_sheet_by_id(cfg, SHEET_AR_TRANSACTIONS)

    imperative_norm = _strip_filter_controls(_normalize_sheet(imperative_sheet))
    tree_norm = _strip_filter_controls(_normalize_sheet(tree_sheet))

    assert tree_norm == imperative_norm
