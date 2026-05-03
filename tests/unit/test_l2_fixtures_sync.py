"""Bundled L2 fixtures must stay byte-identical to ``tests/l2/`` source.

The package ships ``src/quicksight_gen/_l2_fixtures/spec_example.yaml``
and ``sasquatch_pr.yaml`` so ``docs apply`` works from an installed
wheel without an operator's ``tests/`` checkout. ``tests/l2/`` remains
the source of truth (referenced by unit tests, harness, integration);
this test guards the copies from drifting.

If this test fails, copy the updated ``tests/l2/<name>.yaml`` to
``src/quicksight_gen/_l2_fixtures/<name>.yaml`` (the sync direction
is always tests/l2/ → bundled, never the reverse).
"""

from __future__ import annotations

from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TESTS_L2_DIR = _REPO_ROOT / "tests" / "l2"
_BUNDLED_L2_DIR = _REPO_ROOT / "src" / "quicksight_gen" / "_l2_fixtures"


@pytest.mark.parametrize("name", ["spec_example", "sasquatch_pr"])
def test_bundled_l2_fixture_matches_tests_l2_source(name: str) -> None:
    src = _TESTS_L2_DIR / f"{name}.yaml"
    bundled = _BUNDLED_L2_DIR / f"{name}.yaml"
    assert src.read_bytes() == bundled.read_bytes(), (
        f"{bundled} drifted from {src}. Re-sync: "
        f"`cp {src} {bundled}`."
    )
