"""L2 instance loader + build-pipeline seam for the L1 dashboard app.

Migrated from ``apps/account_recon/_l2.py`` in M.4.3 — when AR was
deleted the function moved to its primary remaining caller. Returns
``spec_example`` (the persona-neutral fixture) so production library
code carries no implicit Sasquatch flavor; callers wanting the
canonical Sasquatch demo pass ``l2_instance=load_instance(
"...sasquatch_pr.yaml")`` explicitly.

Module-level helper (vs inlined into ``app.py``) so the CLI + tests +
scripts all import the same default without taking a circular
dependency on the L1 dashboard build itself.

The packaged copy of ``spec_example.yaml`` lives next to this module
(``_default_l2.yaml``) and ships with the wheel via importlib.resources
— v6.0.1 fix for the v6.0.0 packaging bug where the path resolved to
``tests/l2/`` (test fixture, NOT in the wheel) and any installed
``quicksight-gen generate`` invocation that fell back to the default
crashed with FileNotFoundError. The on-disk copy is kept byte-identical
to the test fixture via a unit test that hashes both.
"""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

from quicksight_gen.common.l2 import L2Instance, load_instance


def default_l2_instance() -> L2Instance:
    """Load + validate the persona-neutral default L2 instance.

    Used by ``build_l1_dashboard_app`` when the caller doesn't supply
    an ``l2_instance`` explicitly. Returns ``spec_example`` so
    production library code carries no implicit persona flavor; pass
    ``l2_instance=load_instance("...sasquatch_pr.yaml")`` explicitly
    to render the canonical Sasquatch demo.
    """
    pkg = files("quicksight_gen.apps.l1_dashboard")
    with as_file(pkg / "_default_l2.yaml") as path:
        return load_instance(Path(path))
