"""L.1.15 byte-identity test: typed-primitive Account Network port
matches the existing imperative builder's SheetDefinition output
exactly.

This is the gate for L.2 / L.3 / L.4. If a real, complex sheet
(directional Sankeys + table + 4 filter groups + 2 controls + 4 calc
fields + 3 drill actions + 2 datasets) round-trips byte-identical
through the typed primitives, the per-app ports are unblocked.

Failure here means the typed primitives can't yet express something
the existing builders can — surface that diff and iterate before any
per-app port starts.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from quicksight_gen.apps.investigation.analysis import (
    _build_account_network_sheet,
)
from quicksight_gen.common._account_network_full_port import (
    build_account_network_app_via_full_primitives,
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
    """Recursive JSON diff, bullet-listed by path. Mirrors the L.0
    spike's diff helper."""
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
                    f"  - {sub}: present only in existing "
                    f"({json.dumps(a[k])[:120]})"
                )
            else:
                lines.append(_diff_json(a[k], b[k], sub))
    elif isinstance(a, list):
        if len(a) != len(b):
            lines.append(
                f"  {path}: list length differs — "
                f"existing={len(a)}, tree={len(b)}"
            )
        for i, (ea, eb) in enumerate(zip(a, b)):
            lines.append(_diff_json(ea, eb, f"{path}[{i}]"))
    else:
        if a != b:
            lines.append(
                f"  {path}: existing={json.dumps(a)[:120]} | "
                f"tree={json.dumps(b)[:120]}"
            )
    return "\n".join(line for line in lines if line.strip())


def test_account_network_sheet_byte_identical_via_full_primitives():
    """The L.1.15 gate. Build the Account Network sheet two ways and
    diff at the SheetDefinition level."""
    existing = _sheet_to_json(_build_account_network_sheet(_TEST_CFG))

    # Build via typed primitives → emit through App.emit_analysis()
    # so auto-IDs resolve + validation runs. Then extract the
    # Account Network sheet from the emitted Analysis.
    app = build_account_network_app_via_full_primitives(_TEST_CFG)
    analysis = app.emit_analysis()
    typed_sheet = next(
        s for s in analysis.Definition.Sheets
        if s.SheetId == "inv-sheet-account-network"
    )
    typed = _sheet_to_json(typed_sheet)

    if existing != typed:
        diff = _diff_json(existing, typed)
        pytest.fail(
            "L.1.15: typed-primitive port diverges from imperative "
            "builder.\n\n"
            "If this is a regression, fix the typed primitive (or the "
            "L.1.15 port if it mis-uses the API).\n"
            "If this is an intentional improvement, document it in "
            "the test + PLAN.md L.1.15 entry.\n\n"
            f"Diff:\n{diff}"
        )
