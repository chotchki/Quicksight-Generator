"""Project-wide pytest fixtures and session hooks.

L.1.20 — pytest_sessionstart runs pyright strict on ``common/tree/``
before any tests execute. Types are validated as early as possible: a
type-check error fails the pytest session immediately rather than
letting tests run against broken types. Same gate the CI workflow
runs, just shifted into the local dev loop so you don't need to
remember to run ``.venv/bin/pyright`` separately.

Set ``QS_GEN_SKIP_PYRIGHT=1`` to opt out (e.g. when iterating fast on a
non-tree change and you don't want the ~1s overhead).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _find_pyright() -> str | None:
    """Locate the pyright binary.

    Prefer the venv next to the running interpreter (``sys.executable``'s
    sibling) so the gate works whether pytest was launched via the venv's
    pytest script or via a system pytest with the venv bin not on PATH.
    Fall back to ``shutil.which`` for a system-installed pyright.
    """
    venv_pyright = Path(sys.executable).parent / "pyright"
    if venv_pyright.exists():
        return str(venv_pyright)
    return shutil.which("pyright")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Run pyright strict before any test executes. Fail-fast on type errors."""
    if os.environ.get("QS_GEN_SKIP_PYRIGHT"):
        return
    pyright = _find_pyright()
    if pyright is None:
        # Dev install without pyright — skip the gate rather than failing
        # tests for a missing tool. CI installs the dev extras so pyright
        # is always present there.
        return
    result = subprocess.run(
        [pyright],
        capture_output=True,
        text=True,
        cwd=str(session.config.rootpath),
    )
    if result.returncode != 0:
        output = (result.stdout or "") + (result.stderr or "")
        # pytest captures stdout/stderr from sessionstart; write directly
        # to the original stderr so the operator sees the failure context.
        sys.__stderr__.write(
            "\npyright strict failed — fix type errors before tests run.\n"
            "Set QS_GEN_SKIP_PYRIGHT=1 to bypass.\n\n"
            + output + "\n"
        )
        sys.__stderr__.flush()
        pytest.exit(
            "pyright strict failed; see stderr for details.",
            returncode=2,
        )
