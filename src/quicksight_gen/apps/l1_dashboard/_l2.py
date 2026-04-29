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
"""

from __future__ import annotations

from pathlib import Path

from quicksight_gen.common.l2 import L2Instance, load_instance


# Path to the persona-neutral SPEC example L2 instance. Test fixture
# today; M.5/M.6 will publish to a permanent location.
_SPEC_EXAMPLE_YAML: Path = (
    Path(__file__).resolve().parents[4]
    / "tests" / "l2" / "spec_example.yaml"
)


def default_l2_instance() -> L2Instance:
    """Load + validate the persona-neutral default L2 instance.

    Used by ``build_l1_dashboard_app`` when the caller doesn't supply
    an ``l2_instance`` explicitly. Returns ``spec_example`` so
    production library code carries no implicit persona flavor; pass
    ``l2_instance=load_instance("...sasquatch_pr.yaml")`` explicitly
    to render the canonical Sasquatch demo.
    """
    return load_instance(_SPEC_EXAMPLE_YAML)
