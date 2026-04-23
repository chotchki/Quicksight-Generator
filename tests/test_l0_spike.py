"""L.0 spike validation: tree-built SheetDefinition is byte-identical
to the existing imperative builder.

This test is the spike's contract. It runs both builders for the
Investigation Account Network sheet, dumps each through ``to_aws_json``,
and asserts the dicts match exactly. Any divergence — different keys,
reordered lists, mis-typed values — fails loudly with a JSON-formatted
diff so the spike can iterate until empty.

If this test goes green, L.0's acceptance gate is met and the spike
findings get cherry-picked into L.1's full primitives. If it stays red
after iteration, the L1 API needs redesign before L.1 starts.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from quicksight_gen.apps.investigation.analysis import (
    _build_account_network_sheet,
)
from quicksight_gen.common._tree_spike import (
    build_account_network_sheet_via_tree,
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
    """SheetDefinition isn't a top-level model so it doesn't carry its
    own to_aws_json — we run the same _strip_nones(asdict(...)) shape
    the Analysis-level emission uses."""
    return _strip_nones(asdict(sheet))


def test_account_network_sheet_byte_identical_through_tree():
    """Tree spike builds the same SheetDefinition JSON as the existing
    imperative builder. The whole point of L.0 — anything else is a
    regression that needs explanation in L.0.6's findings."""
    existing = _sheet_to_json(_build_account_network_sheet(_TEST_CFG))
    tree = _sheet_to_json(build_account_network_sheet_via_tree())

    if existing != tree:
        diff = _diff_json(existing, tree)
        pytest.fail(
            "Tree-built SheetDefinition diverges from existing builder.\n"
            f"Diff:\n{diff}"
        )


def _diff_json(a: dict, b: dict, path: str = "") -> str:
    """Recursive JSON diff, bullet-listed by path. Cheap + readable;
    we don't need surgical precision because the spike's success
    state is empty diff."""
    lines: list[str] = []
    if type(a) is not type(b):
        lines.append(f"  {path or '<root>'}: type mismatch — {type(a).__name__} vs {type(b).__name__}")
        return "\n".join(lines)
    if isinstance(a, dict):
        keys = set(a) | set(b)
        for k in sorted(keys):
            sub = f"{path}.{k}" if path else k
            if k not in a:
                lines.append(f"  + {sub}: present only in tree-built ({json.dumps(b[k])[:120]})")
            elif k not in b:
                lines.append(f"  - {sub}: present only in existing ({json.dumps(a[k])[:120]})")
            else:
                lines.append(_diff_json(a[k], b[k], sub))
    elif isinstance(a, list):
        if len(a) != len(b):
            lines.append(
                f"  {path}: list length differs — existing={len(a)}, tree={len(b)}"
            )
        for i, (ea, eb) in enumerate(zip(a, b)):
            lines.append(_diff_json(ea, eb, f"{path}[{i}]"))
    else:
        if a != b:
            lines.append(
                f"  {path}: existing={json.dumps(a)[:120]} | tree={json.dumps(b)[:120]}"
            )
    return "\n".join(line for line in lines if line.strip())
