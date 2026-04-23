"""L.2 byte-identity tests: tree-based Investigation App matches the
imperative builder's per-sheet output exactly.

One test per L.2.x sub-step. Each test extracts the relevant
SheetDefinition from both builders and diffs at the dataclass / dict
level so failures point at the exact field path that diverged.

Failure means either the typed primitives can't yet express what the
imperative builder produced (call-back into L.1 — surface as a
follow-up sub-step), or the tree port mis-uses the API.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from quicksight_gen.apps.investigation.analysis import (
    _build_getting_started_sheet as _imperative_getting_started,
    _build_recipient_fanout_sheet as _imperative_recipient_fanout,
)
from quicksight_gen.apps.investigation.app import build_investigation_app
from quicksight_gen.apps.investigation.constants import (
    SHEET_INV_FANOUT,
    SHEET_INV_GETTING_STARTED,
)
from quicksight_gen.common.config import Config
from quicksight_gen.common.models import _strip_nones


_TEST_CFG = Config(
    aws_account_id="111122223333",
    aws_region="us-west-2",
    theme_preset="sasquatch-bank-investigation",
    datasource_arn=(
        "arn:aws:quicksight:us-west-2:111122223333:datasource/test-ds"
    ),
)


def _sheet_to_json(sheet) -> dict:
    return _strip_nones(asdict(sheet))


def _diff_json(a: dict, b: dict, path: str = "") -> str:
    """Recursive JSON diff — same shape as the L.1.15 helper."""
    lines: list[str] = []
    if type(a) is not type(b):
        lines.append(
            f"  {path or '<root>'}: type mismatch — "
            f"{type(a).__name__} vs {type(b).__name__}"
        )
        return "\n".join(lines)
    if isinstance(a, dict):
        keys = set(a) | set(b)
        for k in sorted(keys):
            sub = f"{path}.{k}" if path else k
            if k not in a:
                lines.append(
                    f"  + {sub}: present only in tree-built "
                    f"({json.dumps(b[k])[:120]})"
                )
            elif k not in b:
                lines.append(
                    f"  - {sub}: present only in imperative "
                    f"({json.dumps(a[k])[:120]})"
                )
            else:
                lines.append(_diff_json(a[k], b[k], sub))
    elif isinstance(a, list):
        if len(a) != len(b):
            lines.append(
                f"  {path}: list length differs — "
                f"imperative={len(a)}, tree={len(b)}"
            )
        for i, (ea, eb) in enumerate(zip(a, b)):
            lines.append(_diff_json(ea, eb, f"{path}[{i}]"))
    else:
        if a != b:
            lines.append(
                f"  {path}: imperative={json.dumps(a)[:120]} | "
                f"tree={json.dumps(b)[:120]}"
            )
    return "\n".join(line for line in lines if line.strip())


def _assert_sheet_byte_identical(sub_step: str, sheet_id: str, imperative):
    """Build the tree, find the matching sheet by id, diff to imperative."""
    app = build_investigation_app(_TEST_CFG)
    analysis = app.emit_analysis()
    typed_sheet = next(
        (s for s in analysis.Definition.Sheets if s.SheetId == sheet_id),
        None,
    )
    assert typed_sheet is not None, (
        f"L.{sub_step}: tree-built app has no sheet with id {sheet_id!r}"
    )

    imperative_json = _sheet_to_json(imperative)
    typed_json = _sheet_to_json(typed_sheet)
    if imperative_json != typed_json:
        diff = _diff_json(imperative_json, typed_json)
        pytest.fail(
            f"L.{sub_step}: tree port diverges from imperative builder.\n\n"
            "If this is a regression, fix the tree port (or the typed "
            "primitive that's missing capability — surface back to L.1).\n"
            "If intentional, document the diff in PLAN.md L.2.9 and "
            "update the test.\n\n"
            f"Diff:\n{diff}"
        )


def test_l2_1_getting_started_sheet_byte_identical():
    """L.2.1 — Getting Started SheetDefinition matches the imperative
    builder exactly. Only text boxes + layout slots — no visuals,
    controls, filters."""
    _assert_sheet_byte_identical(
        "2.1",
        SHEET_INV_GETTING_STARTED,
        _imperative_getting_started(_TEST_CFG),
    )


def test_l2_2_recipient_fanout_sheet_byte_identical():
    """L.2.2 — Recipient Fanout SheetDefinition matches the imperative
    builder exactly. 3 KPIs + ranked table + threshold slider + date
    range filter; first sheet exercising typed Dataset / IntegerParam /
    CalcField / NumericRangeFilter / TimeRangeFilter / FilterDateTimePicker
    / ParameterSlider primitives."""
    _assert_sheet_byte_identical(
        "2.2",
        SHEET_INV_FANOUT,
        _imperative_recipient_fanout(_TEST_CFG),
    )
