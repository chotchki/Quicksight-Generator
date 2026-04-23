"""L.3 byte-identity gate — tree-built AR sheets must emit JSON
identical to the imperative ``apps/account_recon/analysis.py`` builders.

Each L.3.N sub-step adds a sheet to ``apps/account_recon/app.py``;
the corresponding test here pins down that the new tree wiring emits
the same ``SheetDefinition`` shape (modulo intentional layout-DSL
diffs the test allows for).
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from quicksight_gen.apps.account_recon.analysis import (
    _build_getting_started_sheet as _imperative_getting_started_sheet,
)
from quicksight_gen.apps.account_recon.app import build_account_recon_app
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
    # Sheet has no visuals — Visuals key may be absent on imperative,
    # explicit None / missing on tree. Normalize both to absent.
    if normalized.get("Visuals") is None:
        normalized.pop("Visuals", None)
    if normalized.get("FilterControls") in (None, []):
        normalized.pop("FilterControls", None)
    if normalized.get("ParameterControls") in (None, []):
        normalized.pop("ParameterControls", None)
    return normalized


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

    # Imperative side — emit just the Getting Started sheet.
    imperative_sheet = _strip_nones(asdict(_imperative_getting_started_sheet(cfg)))

    # Tree side — build the App and pull the Getting Started sheet
    # from the emitted Analysis.
    app = build_account_recon_app(cfg)
    analysis = app.emit_analysis()
    tree_sheet = _strip_nones(asdict(analysis.Definition.Sheets[0]))

    assert _normalize_sheet(tree_sheet) == _normalize_sheet(imperative_sheet)
